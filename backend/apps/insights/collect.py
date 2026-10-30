"""Turn a company's rows into the plain facts the Insight Engine reads. All queries live here."""

from collections import Counter, defaultdict
from datetime import date

from django.db.models import Count, Q

from apps.masters.machines import allowed_ids, code_of, machines_by_type, name_of
from apps.masters.models import OperationType, Part, PartOperation
from apps.masters.route import describe_route
from apps.plans.models import Plan, PlanAllocation, PlanOperation
from apps.resources.models import Resource, Status
from apps.resources.serializers import resource_issues
from apps.scheduler.models import LineStatus, ScheduleLine
from insights import rules
from insights.model import (
    BalanceCandidate,
    DayBottleneck,
    DispatchRow,
    FurnaceDay,
    HealthItem,
    LineFact,
    LoadRow,
    MeltRow,
)
from planning.checks import RESOURCE_KIND_FOR, check_part

WINDOW_DAYS = 14


# --- plan facts ---------------------------------------------------------------------------------
def line_facts(plan: Plan) -> list[LineFact]:
    op_names = {o.code: o.name for o in OperationType.objects.for_company(plan.company)}
    # A step such as machining~10 is named as the plan names it: "Machining OP10 Rough milling".
    op_names.update(
        PlanOperation.objects.filter(plan_line__plan=plan).values_list("code", "name").distinct()
    )
    facts = []
    for pl in plan.lines.select_related("schedule_line__part__grade"):
        sl = pl.schedule_line
        part = sl.part if sl else None
        facts.append(
            LineFact(
                line_id=pl.pk, customer_code=pl.customer_code, customer_name=pl.customer_name,
                part_id=part.pk if part else 0, part_number=pl.part_number, part_name=pl.part_name,
                grade=part.grade.name if part and part.grade else "", qty=pl.qty,
                internal_date=pl.internal_date, status=pl.status, est_date=pl.est_dispatch_date,
                slack_working_days=pl.slack_working_days,
                holding=op_names.get(pl.holding_op, pl.holding_op) if pl.holding_op else "",
                holding_text=pl.holding_text,
                tonnes=float(part.casting_weight_kg) * pl.qty / 1000 if part else 0.0,
                price=float(part.selling_price) if part and part.selling_price is not None else None,
            )
        )  # fmt: skip
    return facts


def load_rows(plan: Plan) -> list[tuple]:
    """(resource id, code, name, kind, day, load, capacity, required) for every stored shift."""
    return list(
        plan.loads.filter(resource__isnull=False).values_list(
            "resource_id", "resource__code", "resource__name", "resource__resource_type__kind",
            "slot__slot_date", "load", "capacity", "required",
        )
    )  # fmt: skip


def window_days(plan: Plan, rows: list[tuple], today: date) -> list[date]:
    start = max(plan.plan_from, today)
    return sorted({r[4] for r in rows if r[6] > 0 and r[4] >= start})[:WINDOW_DAYS]


def bottleneck_days(plan: Plan, days: list[date]) -> list[DayBottleneck]:
    busy = {b["date"]: b for b in plan.summary.get("bottlenecks", [])}
    out = []
    for d in days:
        b = busy.get(d.isoformat())
        out.append(
            DayBottleneck(
                d, (b or {}).get("resource_code") or None, float((b or {}).get("utilisation", 0))
            )
        )
    return out


def capacity_inputs(rows: list[tuple]) -> tuple[list[LoadRow], dict[int, float]]:
    loads = [LoadRow(r[0], r[1], r[2], r[4], r[5], r[6], r[7]) for r in rows]
    caps: dict[int, list[float]] = defaultdict(list)
    for r in rows:
        if r[6] > 0:
            caps[r[0]].append(r[6])
    return loads, {rid: sum(v) / len(v) for rid, v in caps.items()}


def furnace_days(rows: list[tuple]) -> list[FurnaceDay]:
    return [FurnaceDay(r[1], r[4], r[5], r[6]) for r in rows if r[3] == "furnace"]


def melt_rows(plan: Plan) -> list[MeltRow]:
    """Each line's metal spread over the days its melting work is planned, in proportion to minutes."""
    codes = set(
        PlanOperation.objects.filter(plan_line__plan=plan, kind="melting").values_list(
            "code", flat=True
        )
    )
    if not codes:
        return []
    allocations: dict[int, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for line_id, day, minutes in PlanAllocation.objects.filter(
        plan=plan, op_code__in=codes
    ).values_list("plan_line_id", "slot__slot_date", "minutes"):
        allocations[line_id][day] += minutes
    rows = []
    for pl in plan.lines.select_related("schedule_line__part__grade"):
        kg = float((pl.requirement or {}).get("metal_kg") or 0)
        per_day = allocations.get(pl.pk)
        if kg <= 0 or not per_day:
            continue
        total = sum(per_day.values())
        part = pl.schedule_line.part if pl.schedule_line else None
        grade = part.grade.name if part and part.grade else ""
        rows += [MeltRow(day, grade, kg * m / total) for day, m in per_day.items() if m > 0]
    return rows


def _rated(resource: Resource) -> bool:
    kind = resource.resource_type.kind
    if kind == "furnace":
        return bool(resource.heat_kg and resource.heat_minutes)
    if kind == "moulding_line":
        return bool(resource.rate_per_hour)
    if kind == "core_machine":
        return bool(resource.rate_per_hour or (resource.cycle_seconds and resource.cores_per_shot))
    return True


def balance_candidates(plan: Plan, rows: list[tuple], days: list[date]) -> list[BalanceCandidate]:
    """Route steps allowed only on overloaded resources, with a quieter resource of the same kind."""
    if not days:
        return []
    inside = set(days)
    # Utilisation on the days a resource has work: a furnace that is full for five days and then
    # idle is overloaded, however long the window is.
    per_day: dict[tuple[int, date], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        if r[4] in inside:
            acc = per_day[(r[0], r[4])]
            acc[0] += r[5]
            acc[1] += r[6]
    load: dict[int, float] = defaultdict(float)
    cap: dict[int, float] = defaultdict(float)
    for (rid, _day), (day_load, day_cap) in per_day.items():
        if day_load > 0:
            load[rid] += day_load
            cap[rid] += day_cap
    util = {rid: load[rid] / cap[rid] for rid in cap if cap[rid] > 0}

    resources = list(
        Resource.objects.for_company(plan.company)
        .filter(status=Status.ACTIVE)
        .select_related("resource_type")
    )
    by_id = {r.pk: r for r in resources}
    by_type = machines_by_type(plan.company)
    pieces: Counter[int] = Counter()
    for pl in plan.lines.select_related("schedule_line"):
        if pl.schedule_line_id:
            pieces[pl.schedule_line.part_id] += pl.qty
    if not pieces:
        return []

    out = []
    ops = (
        PartOperation.objects.for_company(plan.company)
        .filter(part_id__in=list(pieces), enabled=True, outsourced=False)
        .select_related("part", "op_type")
        .prefetch_related("resources")
    )
    for op in ops:
        allowed = {i for i in allowed_ids(op, by_type) if i in by_id}
        if not allowed or any(util.get(rid, 0.0) < rules.HOT_UTIL for rid in allowed):
            continue
        worst = max(allowed, key=lambda rid: util.get(rid, 0.0))
        kind = by_id[worst].resource_type.kind
        if RESOURCE_KIND_FOR.get(op.op_type.kind) not in (None, kind):
            continue
        alternatives = [
            r for r in resources
            if r.pk not in allowed and r.resource_type.kind == kind and _rated(r)
        ]  # fmt: skip
        if not alternatives:
            continue
        best = min(alternatives, key=lambda r: (util.get(r.pk, 0.0), r.code))
        out.append(
            BalanceCandidate(
                part_id=op.part_id, part_number=op.part.part_number, op_code=code_of(op),
                op_name=name_of(op), from_id=worst, from_code=by_id[worst].code,
                from_util=util[worst], to_id=best.pk, to_code=best.code,
                to_util=util.get(best.pk, 0.0), pieces=pieces[op.part_id],
            )
        )  # fmt: skip
    return out


# --- schedule facts -----------------------------------------------------------------------------
def dispatch_rows(company) -> list[DispatchRow]:
    qs = (
        ScheduleLine.objects.for_company(company)
        .filter(actual_dispatch_date__isnull=False)
        .exclude(status=LineStatus.CANCELLED)
        .select_related("customer", "part")
    )
    return [
        DispatchRow(
            line_id=ln.pk, customer_code=ln.customer.code, customer_name=ln.customer.name,
            part_number=ln.part.part_number, internal_date=ln.internal_dispatch_date,
            actual_date=ln.actual_dispatch_date,
            qty=ln.actual_dispatched_qty or ln.dispatch_qty,
        )
        for ln in qs
    ]  # fmt: skip


def quantity_history(company) -> dict[int, list[int]]:
    """Quantities of every non-cancelled line by part, to judge what is unusually large."""
    out: dict[int, list[int]] = defaultdict(list)
    for part_id, qty in (
        ScheduleLine.objects.for_company(company)
        .exclude(status=LineStatus.CANCELLED)
        .values_list("part_id", "dispatch_qty")
    ):
        out[part_id].append(qty)
    return out


# --- data health ----------------------------------------------------------------------------------
NO_ROUTE_WHY = (
    "A part with no operations cannot be planned: its schedule lines get no meaningful date."
)
GAP_WHY = "A step with a missing time or resource is planned as taking no capacity, so the dates are too optimistic."
NO_CAPACITY_WHY = "A step with no resource has its duration counted but never takes capacity, so a bottleneck there stays hidden."
PAST_WHY = "A line whose internal date has passed and which has no actual dispatch date is planned from today and shows as late."


def health_items(company, today: date) -> list[HealthItem]:
    items: list[HealthItem] = []
    open_lines = Counter(
        ScheduleLine.objects.for_company(company)
        .filter(status__in=[LineStatus.PLANNED, LineStatus.IN_PROGRESS])
        .values_list("part_id", flat=True)
    )
    parts = (
        Part.objects.for_company(company)
        .filter(is_active=True)
        .annotate(n_ops=Count("operations", filter=Q(operations__enabled=True)))
    )
    for part in parts:
        lines = open_lines.get(part.pk, 0)
        link = f"/masters/parts/{part.pk}"
        if part.n_ops == 0:
            items.append(
                HealthItem(
                    "no_route",
                    part.part_number,
                    f"{part.name} has no enabled operations",
                    NO_ROUTE_WHY,
                    "error",
                    link,
                    lines,
                )
            )
        data = {
            "casting_weight_kg": part.casting_weight_kg, "finished_weight_kg": part.finished_weight_kg,
            "pouring_weight_per_mould_kg": part.pouring_weight_per_mould_kg,
            "cavities_per_mould": part.cavities_per_mould, "cores_per_mould": part.cores_per_mould,
            "rejection_pct": part.rejection_pct,
        }  # fmt: skip
        for issue in check_part(data):
            if issue.level != "error":
                items.append(
                    HealthItem(
                        "unrealistic",
                        part.part_number,
                        issue.message,
                        "A doubtful weight or count feeds straight into the metal and mould requirement.",
                        "warning",
                        link,
                        lines,
                    )
                )
        if lines and part.n_ops:
            for row in describe_route(part)["operations"]:
                if not (row["id"] and row["enabled"]):
                    continue
                where = f"{part.part_number} · {row['name']}"
                for issue in row["issues"]:
                    if issue["level"] == "error":
                        items.append(
                            HealthItem(
                                "route_gap", where, issue["message"], GAP_WHY, "error", link, lines
                            )
                        )
                    elif issue["level"] == "warning":
                        items.append(
                            HealthItem(
                                "unrealistic",
                                where,
                                issue["message"],
                                "A time far outside the typical range often means a unit slip, and it moves every date.",
                                "warning",
                                link,
                                lines,
                            )
                        )
                if not row["capacity_modelled"] and not row["outsourced"]:
                    items.append(
                        HealthItem(
                            "no_capacity",
                            where,
                            "no resource is chosen, so capacity is not modelled",
                            NO_CAPACITY_WHY,
                            "warning",
                            link,
                            lines,
                        )
                    )

    for resource in (
        Resource.objects.for_company(company)
        .filter(status=Status.ACTIVE)
        .select_related("resource_type")
    ):
        for issue in resource_issues(resource):
            if issue.level == "warning":
                items.append(
                    HealthItem(
                        "unrealistic",
                        resource.code,
                        issue.message,
                        "A doubtful rating or efficiency changes this resource's capacity in every plan.",
                        "warning",
                        "/masters/resources",
                    )
                )

    past = defaultdict(list)
    for ln in ScheduleLine.objects.for_company(company).filter(
        status__in=[LineStatus.PLANNED, LineStatus.IN_PROGRESS],
        internal_dispatch_date__lt=today, actual_dispatch_date__isnull=True,
    ).select_related("customer"):  # fmt: skip
        past[ln.customer.code].append(ln.internal_dispatch_date)
    for code, dates in past.items():
        items.append(
            HealthItem("past_due", code, f"{len(dates)} line{'s' if len(dates) != 1 else ''} past the internal date with no actual dispatch (oldest {min(dates):%d-%m-%Y})", PAST_WHY, "warning", "/scheduler", len(dates))
        )  # fmt: skip
    return items
