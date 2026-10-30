"""The Machine shop view: every machine that can run a machining operation, grouped by type, with
its free hours against planned load per day and the operations planned on it."""

from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.masters.machines import allowed_ids, machines_by_type
from apps.masters.models import OperationType, PartOperation
from apps.resources.models import Downtime, Resource
from planning.model import type_of

from .models import Plan, PlanAllocation, PlanOperation

DEFAULT_DAYS = 14


def machine_ids(company) -> set[int]:
    """Machines any machining step of any part may use (the types and machines it lists)."""
    by_type = machines_by_type(company)
    steps = (
        PartOperation.objects.for_company(company)
        .filter(op_type__multi_step=True, enabled=True)
        .prefetch_related("resources")
    )
    ids: set[int] = set()
    for step in steps:
        ids.update(allowed_ids(step, by_type))
    return ids


def build(company, plan: Plan | None, start: date | None, end: date | None) -> dict:
    ids = machine_ids(company)
    machines = list(
        Resource.objects.for_company(company)
        .filter(pk__in=ids)
        .select_related("resource_type")
        .order_by("resource_type__name", "code")
    )
    first = start or (max(plan.plan_from, timezone.localdate()) if plan else timezone.localdate())
    last = end or first + timedelta(days=DEFAULT_DAYS - 1)
    result: dict = {
        "plan": {"id": plan.pk, "version": plan.version, "status": plan.status} if plan else None,
        "from": first,
        "to": last,
        "days": [],
        "types": [],
        "operations": [],
    }

    downtime: dict[int, list[dict]] = defaultdict(list)
    for d in Downtime.objects.for_company(company).filter(
        resource_id__in=ids, end_at__date__gte=first, start_at__date__lte=last
    ):
        downtime[d.resource_id].append({"start": d.start_at, "end": d.end_at, "reason": d.reason})

    per_day: dict[tuple[int, date], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    on_machine: dict[int, dict[tuple[int, str], dict]] = defaultdict(dict)
    if plan is not None and ids:
        for rid, day, load, cap in plan.loads.filter(
            resource_id__in=ids, slot__slot_date__range=(first, last)
        ).values_list("resource_id", "slot__slot_date", "load", "capacity"):
            cell = per_day[(rid, day)]
            cell[0] += load
            cell[1] += cap
        for rid, day, setup in (
            PlanAllocation.objects.filter(
                plan=plan, resource_id__in=ids, slot__slot_date__range=(first, last)
            )
            .values_list("resource_id", "slot__slot_date")
            .annotate(s=Sum("setup_minutes"))
        ):
            per_day[(rid, day)][2] += setup

        multi = set(
            OperationType.objects.for_company(company)
            .filter(multi_step=True)
            .values_list("code", flat=True)
        )
        names = dict(
            PlanOperation.objects.filter(plan_line__plan=plan)
            .values_list("code", "name")
            .distinct()
        )
        lines = {pl.pk: pl for pl in plan.lines.all()}
        rows = (
            PlanAllocation.objects.filter(
                plan=plan, resource_id__in=ids, slot__slot_date__range=(first, last)
            )
            .values("resource_id", "plan_line_id", "op_code")
            .annotate(m=Sum("minutes"), q=Sum("qty"), s=Sum("setup_minutes"))
        )
        for row in rows:
            if type_of(row["op_code"]) not in multi:
                continue
            line = lines[row["plan_line_id"]]
            on_machine[row["resource_id"]][(row["plan_line_id"], row["op_code"])] = {
                "line_id": line.pk,
                "part_number": line.part_number,
                "customer_code": line.customer_code,
                "op_code": row["op_code"],
                "name": names.get(row["op_code"], row["op_code"]),
                "pieces": round(row["q"], 1),
                "minutes": round(row["m"], 1),
                "setup_minutes": round(row["s"], 1),
            }

        for op in PlanOperation.objects.filter(plan_line__plan=plan).select_related("plan_line"):
            if type_of(op.code) not in multi:
                continue
            line = op.plan_line
            result["operations"].append(
                {
                    "line_id": line.pk,
                    "part_number": line.part_number,
                    "customer_code": line.customer_code,
                    "qty": line.qty,
                    "status": line.status,
                    "op_code": op.code,
                    "name": op.name,
                    "machines": op.resource_codes,
                    "start_at": op.start_at,
                    "finish_at": op.finish_at,
                    "minutes": round(op.minutes, 1),
                    "complete": op.complete,
                }
            )
        result["operations"].sort(
            key=lambda o: (o["start_at"] is None, o["start_at"], o["line_id"], o["op_code"])
        )

    working = sorted({day for (_, day), cell in per_day.items() if cell[1] > 0})
    result["days"] = working

    by_type: dict[int, dict] = {}
    for machine in machines:
        group = by_type.setdefault(
            machine.resource_type_id,
            {"id": machine.resource_type_id, "name": machine.resource_type.name, "machines": []},
        )
        days = {}
        total_cap = total_load = total_setup = 0.0
        for day in working:
            load, cap, setup = per_day.get((machine.pk, day), [0.0, 0.0, 0.0])
            total_cap, total_load, total_setup = (
                total_cap + cap,
                total_load + load,
                total_setup + setup,
            )
            days[day.isoformat()] = {
                "capacity": round(cap, 1),
                "load": round(load, 1),
                "setup": round(setup, 1),
                "free": round(max(cap - load, 0.0), 1),
                "utilisation": round(load / cap, 4) if cap > 0 else None,
            }
        group["machines"].append(
            {
                "id": machine.pk,
                "code": machine.code,
                "name": machine.name,
                "status": machine.status,
                "units": machine.units,
                "efficiency_pct": float(machine.efficiency_pct),
                "days": days,
                "capacity": round(total_cap, 1),
                "load": round(total_load, 1),
                "setup": round(total_setup, 1),
                "free": round(max(total_cap - total_load, 0.0), 1),
                "utilisation": round(total_load / total_cap, 4) if total_cap > 0 else None,
                "downtime": downtime.get(machine.pk, []),
                "operations": sorted(
                    on_machine.get(machine.pk, {}).values(), key=lambda o: -o["minutes"]
                ),
            }
        )
    for group in by_type.values():
        cap = sum(m["capacity"] for m in group["machines"])
        load = sum(m["load"] for m in group["machines"])
        group.update(
            capacity=round(cap, 1),
            load=round(load, 1),
            free=round(max(cap - load, 0.0), 1),
            utilisation=round(load / cap, 4) if cap > 0 else None,
        )
    result["types"] = list(by_type.values())
    return result
