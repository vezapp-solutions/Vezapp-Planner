"""More assistant tools: finding things by name, a customer's orders, the plan's overall state, one
day's plan, machine availability and data health. All read-only, like the rest."""

from collections import defaultdict
from typing import Any

from django.db.models import Sum
from django.utils import timezone

from apps.insights import collect
from apps.masters.models import Customer, Part
from apps.plans import machine_shop
from apps.plans import service as plan_service
from apps.plans.models import PlanAllocation
from apps.plans.reports import UNIT
from apps.resources.models import Resource
from insights import performance
from planning.model import type_of

EXTRA_SPECS: list[dict[str, Any]] = [
    {
        "name": "find",
        "description": "Look up a customer, part or machine by any part of its code or name (for example 'Aarav', 'valve', 'VMC'). Use it when the user names something loosely.",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    },
    {
        "name": "get_customer_status",
        "description": "One customer's lines in the latest plan (status, estimated dates, what holds each up) and that customer's dispatch record. customer is a code or part of the name.",
        "input_schema": {"type": "object", "properties": {"customer": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["customer"]},
    },
    {
        "name": "get_plan_overview",
        "description": "The state of the latest plan: version, whether it is confirmed or out of date, how many lines are on track, tight, at risk or not scheduled, and the overall bottleneck.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_day_plan",
        "description": "What the plant does on one day in the latest plan: work per operation, and how full the busiest resources are. date is optional (default today).",
        "input_schema": {"type": "object", "properties": {"date": {"type": "string"}}},
    },
    {
        "name": "get_machine_availability",
        "description": "Free hours and planned load of machining machines. machine is a code or name (VMC-1), machine_type a type name (VMC, CNC, HMC); give neither for all machines. Optional from_date and to_date (default the next two weeks). Includes blocked periods.",
        "input_schema": {"type": "object", "properties": {"machine": {"type": "string"}, "machine_type": {"type": "string"}, "from_date": {"type": "string"}, "to_date": {"type": "string"}}},
    },
    {
        "name": "get_data_health",
        "description": "Gaps in the masters and schedule that hurt the plan: parts without a route, steps missing a time or machine, lines past their date with no dispatch, doubtful values. Each with why it matters.",
        "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    },
]  # fmt: skip


def _hours(minutes: float) -> float:
    return round(minutes / 60, 1)


def _pct(share: float | None) -> int | None:
    return None if share is None else round(share * 100)


class MoreTools:
    """Mixed into Toolbox. Needs `company`, `_plan`, `_no_plan`, `_op_names` and `_day`-style helpers."""

    # --- finding things by name --------------------------------------------------------------------
    def _customers_matching(self, text: str) -> list[Customer]:
        text = str(text).strip()
        qs = Customer.objects.for_company(self.company)
        exact = list(qs.filter(code__iexact=text))
        if exact:
            return exact
        named = list(qs.filter(name__icontains=text))
        return named or list(qs.filter(code__icontains=text))

    def _customer(self, text: str) -> Customer:
        found = self._customers_matching(text)
        if len(found) == 1:
            return found[0]
        if not found:
            some = ", ".join(
                f"{c.code} {c.name}" for c in Customer.objects.for_company(self.company)[:8]
            )
            from .tools import ToolError

            raise ToolError(f"No customer matches '{text}'. The customers are: {some}.")
        from .tools import ToolError

        raise ToolError(
            f"Several customers match '{text}': "
            + ", ".join(f"{c.code} {c.name}" for c in found[:6])
            + ". Ask which one."
        )

    def _parts_matching(self, text: str) -> list[Part]:
        text = str(text).strip()
        qs = Part.objects.for_company(self.company)
        exact = list(qs.filter(part_number__iexact=text))
        if exact:
            return exact
        return list(qs.filter(name__icontains=text) or qs.filter(part_number__icontains=text))

    def _part(self, text: str) -> Part:
        from .tools import ToolError

        found = self._parts_matching(text)
        if len(found) == 1:
            return found[0]
        if not found:
            raise ToolError(f"There is no part matching '{text}'.")
        raise ToolError(
            f"Several parts match '{text}': "
            + ", ".join(f"{p.part_number} {p.name}" for p in found[:6])
            + ". Ask which one."
        )

    def tool_find(self, text: str):
        text = str(text).strip()
        if len(text) < 2:
            from .tools import ToolError

            raise ToolError("Give at least two characters to look for.")
        machines = Resource.objects.for_company(self.company).select_related("resource_type")
        found = {
            "customers": [
                {"code": c.code, "name": c.name} for c in self._customers_matching(text)[:5]
            ],
            "parts": [
                {"part_number": p.part_number, "name": p.name}
                for p in self._parts_matching(text)[:5]
            ],
            "machines": [
                {"code": r.code, "name": r.name, "type": r.resource_type.name}
                for r in (
                    machines.filter(code__icontains=text)
                    | machines.filter(name__icontains=text)
                    | machines.filter(resource_type__name__icontains=text)
                ).distinct()[:8]
            ],
        }
        if not any(found.values()):
            return {**found, "note": f"Nothing is called anything like '{text}'."}
        return found

    # --- a customer ------------------------------------------------------------------------------------
    def tool_get_customer_status(self, customer: str, limit: int = 10):
        from .tools import _limit

        c = self._customer(customer)
        plan = self._plan()
        record = performance.group_stats(
            [r for r in collect.dispatch_rows(self.company) if r.customer_code == c.code],
            lambda r: "all",
        )
        dispatch = (
            {
                "lines_dispatched": record[0]["lines"], "on_time": record[0]["on_time"], "late": record[0]["late"],
                "on_time_percent": _pct(record[0]["on_time_pct"]),
                "average_delay_days_of_late_lines": record[0]["avg_delay_days"],
            }
            if record
            else None
        )  # fmt: skip
        out: dict[str, Any] = {
            "customer": {"code": c.code, "name": c.name, "priority": c.priority},
            "dispatch_record": dispatch,
        }
        if plan is None:
            return {**out, **self._no_plan(), "lines": []}
        names = self._op_names(plan)
        rows = sorted(
            plan.lines.filter(customer_code=c.code), key=lambda r: (r.internal_date, r.pk)
        )
        counts: dict[str, int] = defaultdict(int)
        for r in rows:
            counts[r.status] += 1
        return {
            **out, "plan_version": plan.version, "lines_in_plan": len(rows), "by_status": dict(counts),
            "lines": [
                {
                    "part": r.part_number, "qty": r.qty, "status": r.status, "internal_date": r.internal_date,
                    "estimated_date": r.est_dispatch_date,
                    "working_days_late": -r.slack_working_days if r.slack_working_days is not None and r.slack_working_days < 0 else None,
                    "held_up_by": names.get(r.holding_op, r.holding_op) or None,
                }
                for r in rows[: _limit(limit, 10)]
            ],
        }  # fmt: skip

    # --- the plan as a whole -----------------------------------------------------------------------------
    def tool_get_plan_overview(self):
        plan = self._plan()
        if plan is None:
            return self._no_plan()
        stale = plan_service.stale_reasons(plan)
        return {
            "plan_version": plan.version, "status": plan.status, "calculated_at": plan.calculated_at,
            "planned_from": plan.plan_from, "lines": plan.summary.get("lines"),
            "by_status": plan.summary.get("by_status", {}),
            "overall_bottleneck": plan.bottleneck_resource.code if plan.bottleneck_resource else None,
            "out_of_date": bool(stale), "out_of_date_because": stale,
        }  # fmt: skip

    def tool_get_day_plan(self, date: str | None = None):
        from .tools import ToolError, _day

        plan = self._plan()
        if plan is None:
            return self._no_plan()
        when = _day(date, "date") or timezone.localdate()
        todays = PlanAllocation.objects.filter(plan=plan, slot__slot_date=when)
        names = self._op_names(plan)
        lines_per_op: dict[str, set] = defaultdict(set)
        for code, line_id in todays.values_list("op_code", "plan_line_id"):
            lines_per_op[code].add(line_id)
        work = todays.values("op_code").annotate(
            m=Sum("minutes"), q=Sum("qty"), s=Sum("setup_minutes")
        )
        per_resource: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for code, load, cap in plan.loads.filter(
            slot__slot_date=when, resource__isnull=False
        ).values_list("resource__code", "load", "capacity"):
            per_resource[code][0] += load
            per_resource[code][1] += cap
        working = any(cap > 0 for _, cap in per_resource.values())
        if not working and not work:
            raise ToolError(
                f"{when:%d-%m-%Y} is not a working day in the plan, or it is outside the planned period."
            )
        busiest = sorted(
            ((c, v) for c, v in per_resource.items() if v[1] > 0 and v[0] > 0),
            key=lambda kv: -(kv[1][0] / kv[1][1]),
        )[:6]
        return {
            "date": when, "weekday": when.strftime("%A"), "plan_version": plan.version,
            "work": [
                {
                    "operation": names.get(w["op_code"], w["op_code"]), "lines": len(lines_per_op[w["op_code"]]),
                    "quantity": round(w["q"], 1), "unit": UNIT.get(type_of(w["op_code"]), "pieces"),
                    "hours": _hours(w["m"]), "setup_hours": _hours(w["s"]) if w["s"] else None,
                }
                for w in sorted(work, key=lambda w: w["op_code"])
            ],
            "busiest_resources": [
                {"resource": c, "utilisation_percent": _pct(v[0] / v[1]), "free_hours": _hours(max(v[1] - v[0], 0))}
                for c, v in busiest
            ],
        }  # fmt: skip

    # --- machines --------------------------------------------------------------------------------------------
    def tool_get_machine_availability(self, machine: str | None = None, machine_type: str | None = None, from_date: str | None = None, to_date: str | None = None):  # fmt: skip
        from .tools import ToolError, _day

        plan = self._plan()
        if plan is None:
            return self._no_plan()
        data = machine_shop.build(
            self.company, plan, _day(from_date, "from_date"), _day(to_date, "to_date")
        )
        if not data["types"]:
            return {
                "plan_version": plan.version,
                "note": "No machine is used by a machining operation yet.",
            }
        wanted_type = str(machine_type).strip().lower() if machine_type else None
        wanted = str(machine).strip().lower() if machine else None
        types = []
        for t in data["types"]:
            if wanted_type and wanted_type not in t["name"].lower():
                continue
            machines = [
                m for m in t["machines"]
                if not wanted or wanted in m["code"].lower() or wanted in m["name"].lower()
            ]  # fmt: skip
            if not machines:
                continue
            show_days = len(machines) == 1 or bool(wanted)
            types.append(
                {
                    "type": t["name"],
                    "free_hours": _hours(sum(m["free"] for m in machines)),
                    "utilisation_percent": _pct(
                        sum(m["load"] for m in machines) / sum(m["capacity"] for m in machines)
                        if sum(m["capacity"] for m in machines) > 0
                        else None
                    ),
                    "machines": [
                        {
                            "machine": m["code"],
                            "name": m["name"],
                            "status": m["status"],
                            "free_hours": _hours(m["free"]),
                            "planned_hours": _hours(m["load"]),
                            "setup_hours": _hours(m["setup"]) if m["setup"] else None,
                            "utilisation_percent": _pct(m["utilisation"]),
                            "blocked": [
                                {"from": d["start"], "to": d["end"], "reason": d["reason"] or None}
                                for d in m["downtime"]
                            ],
                            "days": [
                                {
                                    "date": day,
                                    "free_hours": _hours(v["free"]),
                                    "utilisation_percent": _pct(v["utilisation"]),
                                }
                                for day, v in m["days"].items()
                            ][:14]
                            if show_days
                            else None,
                        }
                        for m in machines
                    ],
                }
            )
        if not types:
            codes = ", ".join(m["code"] for t in data["types"] for m in t["machines"])
            raise ToolError(f"No machine matches that. The machines are: {codes}.")
        return {
            "plan_version": plan.version,
            "from": data["from"],
            "to": data["to"],
            "working_days": len(data["days"]),
            "types": types,
        }

    # --- data health -----------------------------------------------------------------------------------------
    def tool_get_data_health(self, limit: int = 8):
        from .tools import _limit

        items = collect.health_items(self.company, timezone.localdate())
        if not items:
            return {"items": 0, "note": "No data problems found."}
        order = {"error": 0, "warning": 1, "info": 2}
        items.sort(key=lambda i: (order[i.severity], -i.lines_affected, i.subject))
        kinds: dict[str, int] = defaultdict(int)
        for i in items:
            kinds[i.kind] += 1
        return {
            "items": len(items), "by_kind": dict(kinds),
            "worst": [
                {"subject": i.subject, "problem": i.detail, "why_it_matters": i.why, "lines_affected": i.lines_affected or None}
                for i in items[: _limit(limit, 8)]
            ],
        }  # fmt: skip
