from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Prefetch, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.permissions import PlannerWrite
from apps.core.viewsets import CompanyScopedViewSet

from . import exports, reports, service
from .models import Plan, PlanAllocation, PlanOperation, PlanStatus
from .serializers import PlanLineDetailSerializer, PlanLineSerializer, PlanSerializer

SEVERITY = {"at_risk": 0, "unscheduled": 1, "tight": 2, "on_track": 3}


def _date(value, field: str, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({field: "Use a date like 2026-11-02."}) from exc


class PlanViewSet(CompanyScopedViewSet):
    queryset = Plan.objects.select_related("bottleneck_resource", "created_by")
    serializer_class = PlanSerializer
    permission_classes = [PlannerWrite]
    company_override_allowed = True
    http_method_names = ["get", "post", "delete", "head", "options"]

    # --- lifecycle ---------------------------------------------------------------------------------
    def create(self, request, *args, **kwargs):
        company = self.get_company()
        if company is None:
            raise ValidationError({"company": "No company selected for this request."})
        plan = service.create_plan(company, request.user)
        return Response(self.get_serializer(plan).data, status=http.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        if instance.status != PlanStatus.DRAFT:
            raise ValidationError({"detail": "A confirmed plan cannot be deleted."})
        instance.delete()

    @action(detail=True, methods=["post"])
    def recalculate(self, request, pk=None):
        plan = service.calculate(self.get_object())
        return Response(self.get_serializer(plan).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        plan = self.get_object()
        if plan.status == PlanStatus.CONFIRMED:
            raise ValidationError({"detail": "This plan is already confirmed."})
        if service.stale_reasons(plan):
            raise ValidationError(
                {"detail": "This plan is out of date. Recalculate it before confirming."}
            )
        plan.status, plan.confirmed_at = PlanStatus.CONFIRMED, timezone.now()
        plan.save()
        return Response(self.get_serializer(plan).data)

    @action(detail=False, methods=["get"])
    def latest(self, request):
        """The plan screens open on: the newest draft, else the newest confirmed plan."""
        qs = self.get_queryset()
        plan = qs.filter(status=PlanStatus.DRAFT).first() or qs.first()
        if plan is None:
            return Response(status=http.HTTP_204_NO_CONTENT)
        return Response(self.get_serializer(plan).data)

    # --- lines ---------------------------------------------------------------------------------------
    @action(detail=True, methods=["get"])
    def lines(self, request, pk=None):
        plan = self.get_object()
        p = request.query_params
        qs = plan.lines.all()
        if p.get("status") in SEVERITY:
            qs = qs.filter(status=p["status"])
        if p.get("customer"):
            qs = qs.filter(customer_code=p["customer"])
        if p.get("month"):
            try:
                year, month = (int(x) for x in p["month"].split("-"))
            except ValueError as exc:
                raise ValidationError({"month": "Use a month like 2026-11."}) from exc
            qs = qs.filter(internal_date__year=year, internal_date__month=month)
        if p.get("q"):
            qs = qs.filter(part_number__icontains=p["q"]) | qs.filter(part_name__icontains=p["q"])
        rows = sorted(
            qs,
            key=lambda r: (
                SEVERITY[r.status],
                r.slack_working_days if r.slack_working_days is not None else -9999,
                r.internal_date,
                r.id,
            ),
        )
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(PlanLineSerializer(page, many=True).data)

    @action(detail=True, methods=["get"], url_path=r"lines/(?P<line_id>\d+)")
    def line_detail(self, request, pk=None, line_id=None):
        plan = self.get_object()
        line = (
            plan.lines.filter(pk=line_id)
            .prefetch_related(
                "operations",
                Prefetch(
                    "allocations",
                    queryset=PlanAllocation.objects.select_related("slot", "resource"),
                ),
            )
            .first()
        )
        if line is None:
            return Response({"detail": "Not found."}, status=http.HTTP_404_NOT_FOUND)
        return Response(PlanLineDetailSerializer(line).data)

    # --- load and bottlenecks -------------------------------------------------------------------------
    @action(detail=True, methods=["get"])
    def load(self, request, pk=None):
        """Resource × day (or shift) grid of load, capacity and utilisation."""
        plan = self.get_object()
        start = _date(request.query_params.get("from"), "from", plan.plan_from)
        end = _date(request.query_params.get("to"), "to", start + timedelta(days=13))
        by_shift = request.query_params.get("by") == "shift"
        rows = list(
            plan.loads.filter(slot__slot_date__range=(start, end)).select_related(
                "slot", "resource", "resource__resource_type"
            )
        )

        columns: dict[tuple, dict] = {}
        cells: dict[int, dict[str, dict]] = defaultdict(dict)
        resources = {}
        for r in rows:
            s = r.slot
            col = (s.slot_date, s.idx) if by_shift else (s.slot_date,)
            key = f"{s.slot_date.isoformat()}|{s.shift_id}" if by_shift else s.slot_date.isoformat()
            columns.setdefault(
                col,
                {"key": key, "date": s.slot_date, "shift": s.shift_name if by_shift else None},
            )
            if r.resource_id:
                resources[r.resource_id] = r.resource
            cell = cells[r.resource_id].setdefault(
                key, {"load": 0.0, "capacity": 0.0, "required": 0.0}
            )
            cell["load"] += r.load
            cell["capacity"] += r.capacity
            cell["required"] += r.required
        for per_resource in cells.values():
            for cell in per_resource.values():
                cap = cell["capacity"]
                cell["utilisation"] = round(cell["load"] / cap, 4) if cap > 0 else None
                for k in ("load", "capacity", "required"):
                    cell[k] = round(cell[k], 2)
        return Response(
            {
                "columns": [v for _, v in sorted(columns.items(), key=lambda kv: kv[0])],
                "resources": [
                    {
                        "id": rid,
                        "code": res.code,
                        "name": res.name,
                        "kind": res.resource_type.kind,
                        "cells": cells.get(rid, {}),
                    }
                    for rid, res in sorted(
                        resources.items(), key=lambda kv: (kv[1].resource_type.kind, kv[1].code)
                    )
                ],
            }
        )

    @action(detail=True, methods=["get"], url_path="load/cell")
    def load_cell(self, request, pk=None):
        """Which lines put work on one resource on one day (optionally one shift)."""
        plan = self.get_object()
        day = _date(request.query_params.get("date"), "date", plan.plan_from)
        qs = PlanAllocation.objects.filter(
            plan=plan, slot__slot_date=day, resource_id=request.query_params.get("resource")
        )
        if request.query_params.get("shift"):
            qs = qs.filter(slot__shift_id=request.query_params["shift"])
        out: dict[tuple, dict] = {}
        for a in qs.select_related("plan_line"):
            key = (a.plan_line_id, a.op_code)
            row = out.setdefault(
                key,
                {
                    "line": a.plan_line_id,
                    "part": a.plan_line.part_number,
                    "customer": a.plan_line.customer_code,
                    "op_code": a.op_code,
                    "minutes": 0.0,
                    "qty": 0.0,
                },
            )
            row["minutes"] += a.minutes
            row["qty"] += a.qty
        rows = sorted(out.values(), key=lambda r: -r["minutes"])
        for r in rows:
            r["minutes"], r["qty"] = round(r["minutes"], 2), round(r["qty"], 2)
        return Response({"date": day, "lines": rows})

    @action(detail=True, methods=["get"])
    def bottlenecks(self, request, pk=None):
        """The busiest resource of each working day for the next N working days."""
        plan = self.get_object()
        raw = request.query_params.get("days", "14")
        days = min(int(raw) if raw.isdigit() else 14, 60)
        start = _date(
            request.query_params.get("from"), "from", max(plan.plan_from, timezone.localdate())
        )
        working = sorted(
            set(
                plan.loads.filter(capacity__gt=0, slot__slot_date__gte=start).values_list(
                    "slot__slot_date", flat=True
                )
            )
        )[:days]
        busy = {b["date"]: b for b in plan.summary.get("bottlenecks", [])}
        empty = {
            "resource_id": None,
            "resource_code": None,
            "utilisation": 0,
            "load": 0,
            "capacity": 0,
        }
        return Response([{**(busy.get(d.isoformat()) or empty), "date": d} for d in working])

    # --- day view and Gantt -----------------------------------------------------------------------------
    @action(detail=True, methods=["get"])
    def day(self, request, pk=None):
        """What the plant does on one day: load per resource and work per operation."""
        plan = self.get_object()
        day = _date(request.query_params.get("date"), "date", timezone.localdate())
        merged: dict[int, dict] = {}
        for r in plan.loads.filter(slot__slot_date=day).select_related("resource"):
            m = merged.setdefault(
                r.resource_id,
                {"id": r.resource_id, "code": r.resource.code, "load": 0.0, "capacity": 0.0},
            )
            m["load"] += r.load
            m["capacity"] += r.capacity
        for m in merged.values():
            m["utilisation"] = round(m["load"] / m["capacity"], 4) if m["capacity"] > 0 else None
            m["load"], m["capacity"] = round(m["load"], 2), round(m["capacity"], 2)
        names = dict(
            PlanOperation.objects.filter(plan_line__plan=plan)
            .values_list("code", "name")
            .distinct()
        )
        todays = PlanAllocation.objects.filter(plan=plan, slot__slot_date=day)
        work = todays.values("op_code").annotate(minutes=Sum("minutes"), qty=Sum("qty"))
        lines_per_op: dict[str, set] = defaultdict(set)
        for code, line_id in todays.values_list("op_code", "plan_line_id"):
            lines_per_op[code].add(line_id)
        return Response(
            {
                "date": day,
                "resources": sorted(merged.values(), key=lambda m: m["code"]),
                "work": [
                    {
                        "op_code": w["op_code"],
                        "name": names.get(w["op_code"], w["op_code"]),
                        "lines": len(lines_per_op[w["op_code"]]),
                        "minutes": round(w["minutes"], 2),
                        "qty": round(w["qty"], 2),
                    }
                    for w in sorted(work, key=lambda w: w["op_code"])
                ],
            }
        )

    @action(detail=True, methods=["get"])
    def gantt(self, request, pk=None):
        plan = self.get_object()
        start = _date(request.query_params.get("from"), "from", plan.plan_from)
        end = _date(request.query_params.get("to"), "to", start + timedelta(days=13))
        if (end - start).days > 60:
            raise ValidationError({"to": "Pick a window of up to 60 days."})
        if request.query_params.get("by") == "line":
            ops = PlanOperation.objects.filter(
                plan_line__plan=plan,
                start_at__isnull=False,
                finish_at__date__gte=start,
                start_at__date__lte=end,
            ).select_related("plan_line")
            bars = [
                {
                    "row": o.plan_line_id,
                    "row_label": f"{o.plan_line.part_number} · {o.plan_line.customer_code}",
                    "status": o.plan_line.status,
                    "code": o.code,
                    "name": o.name,
                    "start": o.start_at,
                    "end": o.finish_at,
                    "due": o.plan_line.internal_date,
                }
                for o in ops.order_by("plan_line__internal_date", "plan_line_id", "sequence")
            ]
            return Response({"by": "line", "from": start, "to": end, "bars": bars})
        allocs = (
            PlanAllocation.objects.filter(plan=plan, slot__slot_date__range=(start, end))
            .exclude(resource__isnull=True)
            .select_related("plan_line", "slot", "resource")
            .order_by("resource__code", "slot__start", "plan_line_id")
        )
        capacity = {
            (rid, sid): cap
            for rid, sid, cap in plan.loads.filter(slot__slot_date__range=(start, end)).values_list(
                "resource_id", "slot_id", "capacity"
            )
        }
        bars = [
            {
                "row": a.resource_id,
                "row_label": a.resource.code,
                "slot": a.slot_id,
                "slot_capacity": capacity.get((a.resource_id, a.slot_id)),
                "line": a.plan_line_id,
                "status": a.plan_line.status,
                "label": f"{a.plan_line.part_number} · {a.plan_line.customer_code}",
                "code": a.op_code,
                "start": a.slot.start,
                "end": a.slot.end,
                "minutes": a.minutes,
            }
            for a in allocs
        ]
        return Response({"by": "resource", "from": start, "to": end, "bars": bars})

    # --- printed outputs ----------------------------------------------------------------------------------
    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        """PDF or Excel: shift plan, day plan, dispatch vs estimate, or resource load."""
        plan = self.get_object()
        p = request.query_params
        kind = p.get("report", "shift_plan")
        fmt = p.get("output", "pdf")
        if fmt not in ("pdf", "xlsx"):
            raise ValidationError({"output": "Use pdf or xlsx."})
        today = max(plan.plan_from, timezone.localdate())
        if kind in ("shift_plan", "day_plan"):
            shift = p.get("shift", "")
            report = reports.shift_or_day_plan(
                plan, _date(p.get("date"), "date", today), p.get("department", "all"),
                int(shift) if shift.isdigit() else None, per_shift=kind == "shift_plan",
            )  # fmt: skip
        elif kind == "dispatch_vs_estimate":
            report = reports.dispatch_vs_estimate(plan, p.get("month", today.strftime("%Y-%m")))
        elif kind == "resource_load":
            start = _date(p.get("from"), "from", today)
            report = reports.resource_load(
                plan, start, _date(p.get("to"), "to", start + timedelta(days=13))
            )
        else:
            raise ValidationError(
                {"report": "Choose shift_plan, day_plan, dispatch_vs_estimate or resource_load."}
            )
        if fmt == "pdf":
            body, content_type = exports.to_pdf(plan, report), "application/pdf"
        else:
            body, content_type = (
                exports.to_xlsx(plan, report),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        response = HttpResponse(body, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{report.filename}.{fmt}"'
        return response
