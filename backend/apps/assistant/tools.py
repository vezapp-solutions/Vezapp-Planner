"""The assistant's tools: read-only functions over one company's own data and engine outputs.

The company is fixed when the Toolbox is built, never taken from the model. Arguments are
validated here, nothing is raw SQL, and nothing a tool does changes data (the what-if tool only
plans twice in memory). Results are plain JSON, and are the only source of numbers in an answer.
"""

import json
from datetime import date, datetime, timedelta
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from apps.insights import collect, reports
from apps.insights import service as insight_service
from apps.insights.models import Insight
from apps.masters.machines import allowed_ids, machines_by_type, name_of
from apps.masters.models import Customer, Part
from apps.plans.inputs import build_input
from apps.plans.models import PlanLine
from apps.resources.models import Resource
from apps.scenarios.service import diff_payload
from insights import performance
from planning.whatif import BlockResource, ChangeDate, ChangeQty, Overtime, apply_changes

from .more_tools import EXTRA_SPECS, MoreTools

MAX_ITEMS = 25


class ToolError(Exception):
    """A request the tool cannot honour. Its message goes back to the model as the result."""


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _limit(value: Any, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolError("limit must be a whole number") from exc
    return max(1, min(n, MAX_ITEMS if default <= MAX_ITEMS else default))


def _day(value: Any, name: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ToolError(f"{name} must be a date like 2026-11-02") from exc


def _pct(share: float | None) -> int | None:
    return None if share is None else round(share * 100)


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_at_risk_lines",
        "description": "Dispatch lines in the latest plan whose estimated date is after the internal date (or that do not fit the planning window), worst first, with working days late and what holds each up. Optional customer filter (code or part of the name).",
        "input_schema": {"type": "object", "properties": {"customer": {"type": "string"}, "limit": {"type": "integer"}}},
    },
    {
        "name": "get_bottlenecks",
        "description": "The busiest resource of each of the next working days in the latest plan, with utilisation.",
        "input_schema": {"type": "object", "properties": {"days": {"type": "integer"}}},
    },
    {
        "name": "get_resource_load",
        "description": "Load, capacity and utilisation of one resource (by code, for example F1) for each working day between two dates.",
        "input_schema": {"type": "object", "properties": {"resource": {"type": "string"}, "from_date": {"type": "string"}, "to_date": {"type": "string"}}, "required": ["resource"]},
    },
    {
        "name": "get_capacity_gap",
        "description": "Resources whose required minutes exceed available minutes in a week, with the extra shifts needed, and resources with spare capacity.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_line_plan",
        "description": "How one planned line is estimated: status, dates, and each operation's start, finish and delay. line_id comes from other tools.",
        "input_schema": {"type": "object", "properties": {"line_id": {"type": "integer"}}, "required": ["line_id"]},
    },
    {
        "name": "get_dispatch_performance",
        "description": "On-time share and average delay of dispatched lines, overall and by month, optionally for one customer (code or name), one part (number or name), or a date range.",
        "input_schema": {"type": "object", "properties": {"customer": {"type": "string"}, "part_number": {"type": "string"}, "from_date": {"type": "string"}, "to_date": {"type": "string"}}},
    },
    {
        "name": "get_month_forecast",
        "description": "Forecast dispatch pieces, tonnes and value for the current month against plan, and the lines that slip into next month.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_part_status",
        "description": "A part's route and its lines in the latest plan with status and estimated dates.",
        "input_schema": {"type": "object", "properties": {"part_number": {"type": "string"}}, "required": ["part_number"]},
    },
    {
        "name": "get_insights",
        "description": "The current insight cards, most important first. Optional type (at_risk, bottleneck_forecast, capacity_gap, melting, load_balancing, dispatch_performance, month_forecast, concentration, data_health) and severity.",
        "input_schema": {"type": "object", "properties": {"type": {"type": "string"}, "severity": {"type": "string"}, "limit": {"type": "integer"}}},
    },
    {
        "name": "get_insight",
        "description": "One insight card by its key, with its calculation trace.",
        "input_schema": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
    },
    {
        "name": "run_what_if_dry_run",
        "description": "Try one change on a copy of the plan and report which lines move. Nothing is saved or applied. change is block_resource (resource, from_date, to_date), change_qty (line_id, qty), change_date (line_id, new_date) or overtime (resource, from_date, to_date, minutes).",
        "input_schema": {"type": "object", "properties": {"change": {"type": "string", "enum": ["block_resource", "change_qty", "change_date", "overtime"]}, "resource": {"type": "string"}, "line_id": {"type": "integer"}, "qty": {"type": "integer"}, "new_date": {"type": "string"}, "from_date": {"type": "string"}, "to_date": {"type": "string"}, "minutes": {"type": "integer"}}, "required": ["change"]},
    },
]  # fmt: skip


TOOL_SPECS += EXTRA_SPECS


class Toolbox(MoreTools):
    def __init__(self, company):
        self.company = company
        self.calls: list[dict[str, Any]] = []
        self.results: list[Any] = []

    # --- dispatch ---------------------------------------------------------------------------------
    def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = dict(args or {})
        fn = (
            getattr(self, f"tool_{name}", None) if name in {s["name"] for s in TOOL_SPECS} else None
        )
        if fn is None:
            result: dict[str, Any] = {"error": f"There is no tool called {name}."}
        else:
            try:
                result = _jsonable(fn(**args))
            except ToolError as exc:
                result = {"error": str(exc)}
            except TypeError:
                result = {"error": "The arguments for this tool were not valid."}
        self.calls.append({"name": name, "args": args})
        self.results.append(result)
        return result

    # --- helpers ------------------------------------------------------------------------------------
    def _plan(self):
        return insight_service.latest_plan(self.company)

    def _no_plan(self) -> dict[str, Any]:
        return {"plan_version": None, "note": "No plan has been calculated yet."}

    def _resource(self, code: str) -> Resource:
        """A resource by code, or by a name that matches only one."""
        text = str(code).strip()
        qs = Resource.objects.for_company(self.company)
        found = qs.filter(code__iexact=text).first()
        if found is not None:
            return found
        named = list(qs.filter(name__icontains=text)[:6]) if text else []
        if len(named) == 1:
            return named[0]
        if named:
            raise ToolError(
                f"Several resources match '{code}': {', '.join(r.code for r in named)}. Ask which one."
            )
        raise ToolError(f"There is no resource called {code}.")

    # --- tools ---------------------------------------------------------------------------------------
    def tool_get_at_risk_lines(self, customer: str | None = None, limit: int = 10):
        plan = self._plan()
        if plan is None:
            return {**self._no_plan(), "lines": []}
        qs = plan.lines.filter(status__in=["at_risk", "unscheduled"])
        if customer:
            qs = qs.filter(customer_code=self._customer(customer).code)
        total = qs.count()
        rows = sorted(
            qs,
            key=lambda r: (
                r.status != "unscheduled",
                r.slack_working_days if r.slack_working_days is not None else -9999,
                r.internal_date,
            ),
        )
        names = self._op_names(plan)
        return {
            "plan_version": plan.version, "total_at_risk": total,
            "lines": [
                {
                    "line_id": r.pk, "customer": r.customer_code, "part": r.part_number, "qty": r.qty,
                    "status": r.status, "internal_date": r.internal_date, "estimated_date": r.est_dispatch_date,
                    "working_days_late": -r.slack_working_days if r.slack_working_days is not None and r.slack_working_days < 0 else None,
                    "held_up_by": names.get(r.holding_op, r.holding_op) or None,
                }
                for r in rows[: _limit(limit, 10)]
            ],
        }  # fmt: skip

    def _op_names(self, plan) -> dict[str, str]:
        """Operation names by code, step codes included ("machining~10" is "Machining OP10 ...")."""
        from apps.masters.models import OperationType
        from apps.plans.models import PlanOperation

        names = {o.code: o.name for o in OperationType.objects.for_company(self.company)}
        names.update(
            PlanOperation.objects.filter(plan_line__plan=plan)
            .values_list("code", "name")
            .distinct()
        )
        return names

    def tool_get_bottlenecks(self, days: int = 14):
        plan = self._plan()
        if plan is None:
            return {**self._no_plan(), "days": []}
        rows = collect.load_rows(plan)
        window = collect.window_days(plan, rows, timezone.localdate())[: _limit(days, 14)]
        return {
            "plan_version": plan.version,
            "days": [
                {"date": d.day, "busiest_resource": d.resource_code, "utilisation_percent": _pct(d.utilisation) if d.resource_code else None}
                for d in collect.bottleneck_days(plan, window)
            ],
            "overall_bottleneck": plan.bottleneck_resource.code if plan.bottleneck_resource else None,
        }  # fmt: skip

    def tool_get_resource_load(
        self, resource: str, from_date: str | None = None, to_date: str | None = None
    ):
        plan = self._plan()
        res = self._resource(resource)
        if plan is None:
            return {**self._no_plan(), "days": []}
        start = _day(from_date, "from_date") or max(plan.plan_from, timezone.localdate())
        end = _day(to_date, "to_date") or start + timedelta(days=13)
        per: dict[date, list[float]] = {}
        for rid, _c, _n, _k, day, load, cap, _req in collect.load_rows(plan):
            if rid == res.pk and start <= day <= end:
                acc = per.setdefault(day, [0.0, 0.0])
                acc[0] += load
                acc[1] += cap
        return {
            "plan_version": plan.version, "resource": res.code, "from": start, "to": end,
            "days": [
                {"date": d, "load_hours": round(v[0] / 60, 1), "capacity_hours": round(v[1] / 60, 1),
                 "utilisation_percent": _pct(v[0] / v[1]) if v[1] > 0 else None}
                for d, v in sorted(per.items()) if v[1] > 0
            ],
        }  # fmt: skip

    def _cards(self, **filters) -> list[Insight]:
        run = insight_service.latest_run(self.company)
        if run is None:
            return []
        return list(run.cards.filter(**filters))

    @staticmethod
    def _card(c: Insight) -> dict[str, Any]:
        return {
            "key": c.key,
            "type": c.type,
            "severity": c.severity,
            "title": c.title,
            "message": c.message,
            "numbers": c.numbers,
            "action": c.action,
            "trend": c.trend,
        }

    def tool_get_capacity_gap(self):
        cards = self._cards(type="capacity_gap")
        if not cards:
            return {
                "cards": [],
                "note": "No capacity-gap insight is available. Calculate a plan first.",
            }
        return {"cards": [self._card(c) for c in cards]}

    def tool_get_line_plan(self, line_id: int):
        plan = self._plan()
        if plan is None:
            return self._no_plan()
        try:
            line = plan.lines.prefetch_related("operations").get(pk=int(line_id))
        except (PlanLine.DoesNotExist, TypeError, ValueError):
            raise ToolError(f"There is no line {line_id} in the latest plan.") from None
        return {
            "plan_version": plan.version, "line_id": line.pk, "customer": line.customer_code, "part": line.part_number,
            "qty": line.qty, "status": line.status, "internal_date": line.internal_date,
            "estimated_date": line.est_dispatch_date, "spare_working_days": line.slack_working_days,
            "held_up_by_text": line.holding_text or None,
            "operations": [
                {"operation": o.name, "start": o.start_at, "finish": o.finish_at, "delay_days": o.delay_days,
                 "resources": o.resource_codes or None}
                for o in line.operations.all()
            ],
        }  # fmt: skip

    def tool_get_dispatch_performance(
        self,
        customer: str | None = None,
        part_number: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ):
        rows = collect.dispatch_rows(self.company)
        start, end = _day(from_date, "from_date"), _day(to_date, "to_date")
        rows = reports._in_range(
            rows, start, end, self._customer(customer).code if customer else None
        )
        if part_number:
            wanted = self._part(part_number).part_number
            rows = [r for r in rows if r.part_number == wanted]
        overall = performance.group_stats(rows, lambda r: "All")
        if not overall:
            return {"lines": 0, "note": "No dispatched lines with an actual date match."}
        o = overall[0]
        return {
            "lines": o["lines"], "on_time": o["on_time"], "late": o["late"],
            "on_time_percent": _pct(o["on_time_pct"]), "average_delay_days_of_late_lines": o["avg_delay_days"],
            "worst_delay_days": o["max_delay_days"],
            "by_month": [{"month": m["group"], "lines": m["lines"], "on_time_percent": _pct(m["on_time_pct"])} for m in performance.by_month(rows)],
            "definition": "On time means the actual dispatch date is on or before the internal date.",
        }  # fmt: skip

    def tool_get_month_forecast(self):
        cards = self._cards(key="month_forecast")
        if not cards:
            return {
                "note": "No month forecast is available. Calculate a plan with lines due this month."
            }
        return self._card(cards[0])

    def tool_get_part_status(self, part_number: str):
        part = self._part(part_number)
        plan = self._plan()
        lines = list(plan.lines.filter(part_number=part.part_number)) if plan else []
        by_type = machines_by_type(self.company)
        codes = dict(Resource.objects.for_company(self.company).values_list("pk", "code"))
        route = [
            {
                "operation": name_of(o),
                "resources": ", ".join(codes[i] for i in allowed_ids(o, by_type) if i in codes)
                or None,
            }
            for o in part.operations.filter(enabled=True)
            .select_related("op_type")
            .prefetch_related("resources")
        ]
        return {
            "part": part.part_number, "name": part.name, "grade": part.grade.name if part.grade else None,
            "route": route, "plan_version": plan.version if plan else None,
            "lines": [
                {"line_id": ln.pk, "customer": ln.customer_code, "qty": ln.qty, "status": ln.status,
                 "internal_date": ln.internal_date, "estimated_date": ln.est_dispatch_date}
                for ln in lines[:MAX_ITEMS]
            ],
        }  # fmt: skip

    def tool_get_insights(
        self, type: str | None = None, severity: str | None = None, limit: int = 5
    ):
        filters = {k: v for k, v in (("type", type), ("severity", severity)) if v}
        cards = self._cards(**filters)[: _limit(limit, 5)]
        return (
            {"cards": [self._card(c) for c in cards]}
            if cards
            else {"cards": [], "note": "No insights match."}
        )

    def tool_get_insight(self, key: str):
        cards = self._cards(key=str(key))
        if not cards:
            raise ToolError(f"There is no insight with key {key}.")
        c = cards[0]
        return {**self._card(c), "why": c.why}

    def tool_run_what_if_dry_run(self, change: str, resource: str | None = None, line_id: int | None = None,
                                 qty: int | None = None, new_date: str | None = None, from_date: str | None = None,
                                 to_date: str | None = None, minutes: int | None = None):  # fmt: skip
        today = timezone.localdate()
        inp, lines_by_id = build_input(self.company, today)
        if change in ("block_resource", "overtime"):
            res = self._resource(resource or "")
            start, end = (
                _day(from_date, "from_date"),
                _day(to_date, "to_date") or _day(from_date, "from_date"),
            )
            if start is None or end is None or end < start:
                raise ToolError(
                    "from_date and to_date are needed, and to_date cannot be before from_date"
                )
            if change == "block_resource":
                changes = [
                    BlockResource(
                        res.pk,
                        datetime.combine(start, datetime.min.time()),
                        datetime.combine(end, datetime.max.time()).replace(microsecond=0),
                    )
                ]
            else:
                if not minutes or not 1 <= int(minutes) <= 480:
                    raise ToolError("minutes must be between 1 and 480")
                changes = [Overtime(start, end, int(minutes), None, frozenset({res.pk}))]
        elif change in ("change_qty", "change_date"):
            try:
                plan_line = PlanLine.objects.filter(company=self.company).get(pk=int(line_id))
            except (PlanLine.DoesNotExist, TypeError, ValueError):
                raise ToolError(f"There is no line {line_id}.") from None
            schedule_id = plan_line.schedule_line_id
            if schedule_id not in lines_by_id:
                raise ToolError("That line is no longer on the schedule.")
            if change == "change_qty":
                if not qty or int(qty) < 1:
                    raise ToolError("qty must be a positive whole number")
                changes = [ChangeQty(schedule_id, int(qty))]
            else:
                when = _day(new_date, "new_date")
                if when is None:
                    raise ToolError("new_date is needed")
                changes = [ChangeDate(schedule_id, when)]
        else:
            raise ToolError("change must be block_resource, change_qty, change_date or overtime")

        payload = diff_payload(inp, apply_changes(inp, changes), lines_by_id)
        diff = payload["diff"]
        names = {k: v["code"] for k, v in payload["resources"].items()}
        return {
            "applied": False, "note": "Nothing was changed. This is a trial on a copy.",
            "lines_that_change": diff["counts"]["total"], "moved_later": diff["counts"]["later"],
            "moved_earlier": diff["counts"]["earlier"], "newly_at_risk": diff["counts"]["newly_at_risk"],
            "bottleneck_before": names.get(str(diff["bottleneck_before"])), "bottleneck_after": names.get(str(diff["bottleneck_after"])),
            "lines": [
                {"part": ln["part_number"], "customer": ln["customer_code"], "estimated_before": ln["est_before"],
                 "estimated_after": ln["est_after"], "working_days_moved": ln["moved_working_days"],
                 "status_after": ln["status_after"]}
                for ln in diff["lines"][:10]
            ],
        }  # fmt: skip


def customer_codes(company) -> dict[str, str]:
    """Lower-case code and name to code, for spotting a customer in a question."""
    out: dict[str, str] = {}
    for c in Customer.objects.for_company(company):
        out[c.code.lower()] = c.code
        out[c.name.lower()] = c.code
    return out


def part_numbers(company) -> dict[str, str]:
    return {p.part_number.lower(): p.part_number for p in Part.objects.for_company(company)}
