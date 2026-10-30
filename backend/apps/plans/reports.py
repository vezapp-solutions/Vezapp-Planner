"""The data behind the printed plans. Renderers (PDF, Excel) turn a Report into a file."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from planning.model import type_of

from .models import Plan, PlanAllocation, PlanLine, PlanLoad

DEPARTMENTS = {
    "all": "All departments",
    "core": "Core shop",
    "moulding": "Moulding",
    "melting": "Melting and pouring",
    "knockout": "Knockout",
    "fettling": "Fettling",
    "machining": "Machining",
    "packing": "Packing",
    "dispatch": "Dispatch",
}
UNIT = {"core": "cores", "moulding": "moulds", "melting": "moulds"}
STATUS = {
    "on_track": "On track",
    "tight": "Tight",
    "at_risk": "At risk",
    "unscheduled": "Not scheduled",
}


@dataclass
class Table:
    title: str
    columns: list[str]
    rows: list[list[str]]
    widths: list[float] = field(default_factory=list)  # relative column widths; empty = even
    note: str = ""


@dataclass
class Report:
    title: str
    subtitle: str
    tables: list[Table]
    filename: str


def fmt_date(d: date | None) -> str:
    return d.strftime("%d-%m-%Y") if d else "–"


def _n(value: float, digits: int = 0) -> str:
    """Indian digit grouping (1,23,456)."""
    text = f"{abs(value):.{digits}f}"
    whole, _, frac = text.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join([*parts, tail])
    out = whole + (f".{frac}" if frac else "")
    return f"-{out}" if value < 0 else out


def _qty(code: str, qty: float) -> str:
    return f"{_n(qty, 0 if qty == int(qty) else 1)} {UNIT.get(type_of(code), 'pcs')}"


def _department(raw: str) -> str:
    if raw and raw not in DEPARTMENTS:
        raise ValidationError({"department": f"Choose one of: {', '.join(DEPARTMENTS)}."})
    return raw or "all"


def _load_table(plan: Plan, slot_filter: dict, title: str) -> Table:
    merged: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for r in PlanLoad.objects.filter(plan=plan, **slot_filter).select_related("resource"):
        if r.resource_id:
            m = merged[r.resource.code]
            m[0] += r.load
            m[1] += r.capacity
    rows = [
        [code, _n(v[0], 0), _n(v[1], 0), f"{v[0] / v[1] * 100:.0f}%" if v[1] > 0 else "–"]
        for code, v in sorted(merged.items())
        if v[0] > 0 or v[1] > 0
    ]
    return Table(
        title, ["Resource", "Load (min)", "Capacity (min)", "Utilisation"], rows, [3, 2, 2, 2]
    )


def _work_rows(allocs, aggregate_shifts: bool) -> list[list[str]]:
    grouped: dict[tuple, list[float]] = defaultdict(lambda: [0.0, 0.0])
    meta: dict[tuple, PlanAllocation] = {}
    for a in allocs:
        key = (a.resource.code if a.resource else "(not modelled)", a.op_code, a.plan_line_id) + (
            () if aggregate_shifts else (a.slot_id,)
        )
        grouped[key][0] += a.minutes
        grouped[key][1] += a.qty
        meta[key] = a
    rows = []
    for key in sorted(grouped, key=lambda k: (k[0], meta[k].plan_line.internal_date, k[1], k[2])):
        a, v = meta[key], grouped[key]
        pl = a.plan_line
        rows.append(
            [key[0], a.op_code, pl.part_number, pl.customer_code, _qty(a.op_code, v[1]), _n(v[0], 0), fmt_date(pl.internal_date), STATUS[pl.status]]
        )  # fmt: skip
    return rows


WORK_COLUMNS = ["Resource", "Operation", "Part", "Customer", "Quantity", "Minutes", "Due", "Status"]
WORK_WIDTHS = [2.2, 2, 2.4, 2.2, 2.4, 1.6, 2, 2]


def shift_or_day_plan(
    plan: Plan, day: date, department: str, shift_id: int | None, per_shift: bool
) -> Report:
    department = _department(department)
    base = PlanAllocation.objects.filter(plan=plan, slot__slot_date=day).select_related(
        "plan_line", "slot", "resource"
    )
    if department != "all":
        base = base.filter(
            Q(op_code=department) | Q(op_code__startswith=f"{department}~")
        )  # every step
    if shift_id:
        base = base.filter(slot__shift_id=shift_id)
    allocs = list(base)

    dept_title = DEPARTMENTS[department]
    tables: list[Table] = []
    if per_shift:
        shifts = sorted({(a.slot.start, a.slot.shift_id, a.slot.shift_name) for a in allocs})
        for start, sid, name in shifts:
            part = [a for a in allocs if a.slot.shift_id == sid]
            tables.append(
                Table(f"{name} ({start:%H:%M})", WORK_COLUMNS, _work_rows(part, False), WORK_WIDTHS)
            )
        title = f"Shift plan: {dept_title}"
        loadf = {"slot__slot_date": day, **({"slot__shift_id": shift_id} if shift_id else {})}
    else:
        tables.append(Table("Work planned", WORK_COLUMNS, _work_rows(allocs, True), WORK_WIDTHS))
        title = f"Day plan: {dept_title}"
        loadf = {"slot__slot_date": day}
    if not allocs:
        tables = [
            Table("Nothing is planned", ["Note"], [["No work is planned for this selection."]], [1])
        ]
    else:
        tables.append(_load_table(plan, loadf, "Resource load"))
    stem = f"{'shift' if per_shift else 'day'}-plan-{day.isoformat()}-{department}"
    return Report(title, f"{fmt_date(day)} · {dept_title}", tables, stem)


def dispatch_vs_estimate(plan: Plan, month: str) -> Report:
    try:
        year, mon = (int(x) for x in month.split("-"))
        first = date(year, mon, 1)
    except (ValueError, AttributeError) as exc:
        raise ValidationError({"month": "Use a month like 2026-11."}) from exc
    lines = list(
        PlanLine.objects.filter(
            plan=plan, internal_date__year=year, internal_date__month=mon
        ).order_by("internal_date", "id")
    )
    counts: dict[str, int] = defaultdict(int)
    for ln in lines:
        counts[ln.status] += 1
    rows = [
        [fmt_date(ln.internal_date), ln.customer_code, f"{ln.part_number} {ln.part_name}"[:34], _n(ln.qty), fmt_date(ln.est_dispatch_date),
         "–" if ln.slack_working_days is None else f"{ln.slack_working_days:+d}", STATUS[ln.status], ln.holding_op or "–"]
        for ln in lines
    ]  # fmt: skip
    summary = Table(
        "Summary",
        ["Lines", "On track", "Tight", "At risk", "Not scheduled"],
        [
            [
                str(len(lines)),
                *[str(counts.get(k, 0)) for k in ("on_track", "tight", "at_risk", "unscheduled")],
            ]
        ],
        [1, 1, 1, 1, 1],
    )
    detail = Table(
        "Dispatch lines",
        [
            "Internal date",
            "Customer",
            "Part",
            "Qty",
            "Estimated",
            "Slack (working days)",
            "Status",
            "Held up by",
        ],
        rows or [["No lines in this month."] + [""] * 7],
        [1.7, 1.6, 3.6, 1.2, 1.7, 1.8, 1.6, 1.8],
    )
    return Report(
        "Dispatch plan vs estimated dates",
        f"{first:%B %Y} · plan v{plan.version}",
        [summary, detail],
        f"dispatch-vs-estimate-{month}",
    )


def resource_load(plan: Plan, start: date, end: date) -> Report:
    if end < start or (end - start).days > 30:
        raise ValidationError({"to": "Pick a range of 1 to 31 days."})
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    cells: dict[str, dict[date, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for r in PlanLoad.objects.filter(plan=plan, slot__slot_date__range=(start, end)).select_related(
        "slot", "resource"
    ):
        if r.resource_id:
            c = cells[r.resource.code][r.slot.slot_date]
            c[0] += r.load
            c[1] += r.capacity
    working = [d for d in days if any(cells[c].get(d, [0, 0])[1] > 0 for c in cells)]
    columns = ["Resource", *[d.strftime("%d-%m") for d in working]]
    rows = []
    for code in sorted(cells):
        row = [code]
        for d in working:
            load, cap = cells[code].get(d, [0.0, 0.0])
            row.append(f"{load / cap * 100:.0f}%" if cap > 0 else "–")
        rows.append(row)
    table = Table(
        "Utilisation per working day (load ÷ capacity)",
        columns,
        rows or [["No load in this period."]],
        [2, *[1] * len(working)],
    )
    return Report(
        "Resource load report",
        f"{fmt_date(start)} to {fmt_date(end)} · plan v{plan.version}",
        [table],
        f"resource-load-{start.isoformat()}-{end.isoformat()}",
    )
