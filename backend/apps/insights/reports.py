"""The three Reports: dispatch performance, utilisation, and plan versus actual.

Each returns the JSON the screen shows and a Report the PDF and Excel renderers print.
"""

from collections import defaultdict
from datetime import date, timedelta

from rest_framework.exceptions import ValidationError

from apps.plans.models import Plan, PlanLine, PlanStatus
from apps.plans.reports import Report, Table, _n, fmt_date
from apps.scheduler.models import LineStatus, ScheduleLine
from insights import performance
from insights.model import DispatchRow

from . import collect


def _pct(share: float) -> str:
    return f"{round(share * 100)}%"


def _in_range(rows: list[DispatchRow], start: date | None, end: date | None, customer: str | None):
    return [
        r
        for r in rows
        if (start is None or r.actual_date >= start)
        and (end is None or r.actual_date <= end)
        and (not customer or r.customer_code == customer)
    ]


# --- dispatch performance --------------------------------------------------------------------------
def dispatch_performance(company, start: date | None, end: date | None, customer: str | None):
    rows = _in_range(collect.dispatch_rows(company), start, end, customer)
    overall = performance.group_stats(rows, lambda r: "All lines")
    data = {
        "from": start, "to": end, "customer": customer or "",
        "overall": overall[0] if overall else None,
        "by_customer": performance.by_customer(rows),
        "by_part": performance.by_part(rows),
        "by_month": performance.by_month(rows),
    }  # fmt: skip

    def table(title: str, stats: list[dict], first: str, with_name: bool = False) -> Table:
        columns = [
            first,
            *(["Name"] if with_name else []),
            "Lines",
            "Pieces",
            "On time",
            "Late",
            "On time %",
            "Avg delay (days)",
            "Worst delay (days)",
        ]
        body = [
            [s["group"], *([s["name"]] if with_name else []), s["lines"], _n(s["pieces"]), s["on_time"], s["late"],
             _pct(s["on_time_pct"]), _n(s["avg_delay_days"], 1), s["max_delay_days"]]
            for s in stats
        ]  # fmt: skip
        return Table(title, columns, [[str(c) for c in r] for r in body])

    window = f"{fmt_date(start)} to {fmt_date(end)}" if start or end else "all dispatches"
    report = Report(
        "Dispatch performance",
        f"On time = dispatched on or before the internal date · {window}"
        + (f" · customer {customer}" if customer else ""),
        [
            table("By month of dispatch", data["by_month"], "Month"),
            table("By customer", data["by_customer"], "Customer", with_name=True),
            table("By part", data["by_part"], "Part"),
        ],
        "dispatch-performance",
    )
    return data, report


# --- utilisation ------------------------------------------------------------------------------------
def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def utilisation(plan: Plan, start: date, end: date):
    rows = [r for r in collect.load_rows(plan) if start <= r[4] <= end]
    per: dict[int, dict] = {}
    for rid, code, name, kind, day, load, cap, _required in rows:
        res = per.setdefault(
            rid,
            {
                "id": rid,
                "code": code,
                "name": name,
                "kind": kind,
                "days": defaultdict(lambda: [0.0, 0.0]),
            },
        )
        res["days"][day][0] += load
        res["days"][day][1] += cap
    resources = []
    for res in sorted(per.values(), key=lambda r: (r["kind"], r["code"])):
        days = res.pop("days")
        load = sum(v[0] for v in days.values())
        cap = sum(v[1] for v in days.values())
        loaded = {d: v[0] / v[1] for d, v in days.items() if v[1] > 0 and v[0] > 0}
        peak_day = max(loaded, key=lambda d: (loaded[d], d)) if loaded else None
        weeks: dict[date, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for d, (ld, cp) in days.items():
            weeks[_week_start(d)][0] += ld
            weeks[_week_start(d)][1] += cp
        resources.append({
            **res, "load": round(load, 1), "capacity": round(cap, 1),
            "utilisation": round(load / cap, 4) if cap > 0 else None,
            "peak_utilisation": round(loaded[peak_day], 4) if peak_day else None, "peak_date": peak_day,
            "weeks": [
                {"week_start": w, "load": round(v[0], 1), "capacity": round(v[1], 1),
                 "utilisation": round(v[0] / v[1], 4) if v[1] > 0 else None}
                for w, v in sorted(weeks.items())
            ],
        })  # fmt: skip
    data = {
        "from": start,
        "to": end,
        "plan": {"id": plan.pk, "version": plan.version},
        "resources": resources,
    }

    week_starts = sorted({w["week_start"] for r in resources for w in r["weeks"]})
    columns = [
        "Resource",
        "Load (h)",
        "Capacity (h)",
        "Utilisation",
        "Busiest day",
        *[f"Wk {w:%d-%m}" for w in week_starts],
    ]
    body = []
    for r in resources:
        by_week = {w["week_start"]: w["utilisation"] for w in r["weeks"]}
        body.append([
            f"{r['code']} {r['name']}", _n(r["load"] / 60, 1), _n(r["capacity"] / 60, 1),
            _pct(r["utilisation"]) if r["utilisation"] is not None else "–",
            f"{fmt_date(r['peak_date'])} ({_pct(r['peak_utilisation'])})" if r["peak_date"] else "–",
            *[_pct(by_week[w]) if by_week.get(w) is not None else "–" for w in week_starts],
        ])  # fmt: skip
    report = Report(
        "Resource utilisation",
        f"{fmt_date(start)} to {fmt_date(end)} · plan v{plan.version}",
        [Table("Planned load against capacity", columns, body)],
        "utilisation",
    )
    return data, report


# --- plan versus actual ------------------------------------------------------------------------------
def plan_vs_actual(company, start: date | None, end: date | None):
    lines = list(
        ScheduleLine.objects.for_company(company)
        .filter(actual_dispatch_date__isnull=False)
        .exclude(status=LineStatus.CANCELLED)
        .select_related("customer", "part")
    )
    lines = [
        ln
        for ln in lines
        if (start is None or ln.actual_dispatch_date >= start)
        and (end is None or ln.actual_dispatch_date <= end)
    ]
    planned: dict[int, PlanLine] = {}
    for pl in (
        PlanLine.objects.filter(
            company=company,
            plan__status=PlanStatus.CONFIRMED,
            schedule_line__in=[ln.pk for ln in lines],
        )
        .select_related("plan")
        .order_by("schedule_line_id", "-plan__version")
    ):
        planned.setdefault(pl.schedule_line_id, pl)

    rows, matched = [], []
    for ln in lines:
        pl = planned.get(ln.pk)
        est = pl.est_dispatch_date if pl else None
        row = {
            "line_id": ln.pk, "customer_code": ln.customer.code, "customer_name": ln.customer.name,
            "part_number": ln.part.part_number, "qty": ln.actual_dispatched_qty or ln.dispatch_qty,
            "internal_date": ln.internal_dispatch_date, "est_date": est, "actual_date": ln.actual_dispatch_date,
            "plan_version": pl.plan.version if pl else None, "planned_status": pl.status if pl else None,
            "est_error_days": (ln.actual_dispatch_date - est).days if est else None,
            "delay_days": max(0, (ln.actual_dispatch_date - ln.internal_dispatch_date).days),
        }  # fmt: skip
        rows.append(row)
        if est:
            matched.append(row)
    rows.sort(
        key=lambda r: (r["est_error_days"] is None, -abs(r["est_error_days"] or 0), r["line_id"])
    )

    summary = {
        "lines": len(rows), "with_confirmed_plan": len(matched), "without_confirmed_plan": len(rows) - len(matched),
        "mean_abs_error_days": round(sum(abs(r["est_error_days"]) for r in matched) / len(matched), 2) if matched else None,
        "within_one_day": round(sum(1 for r in matched if abs(r["est_error_days"]) <= 1) / len(matched), 4) if matched else None,
        "estimated_on_time_actual_late": sum(1 for r in matched if r["est_date"] <= r["internal_date"] and r["delay_days"] > 0),
        "estimated_late_actual_on_time": sum(1 for r in matched if r["est_date"] > r["internal_date"] and r["delay_days"] == 0),
    }  # fmt: skip
    data = {"from": start, "to": end, "summary": summary, "lines": rows}

    columns = [
        "Customer",
        "Part",
        "Qty",
        "Internal date",
        "Estimated",
        "Actual",
        "Error (days)",
        "Late vs internal (days)",
        "Plan",
    ]
    body = [
        [r["customer_code"], r["part_number"], _n(r["qty"]), fmt_date(r["internal_date"]), fmt_date(r["est_date"]),
         fmt_date(r["actual_date"]), "–" if r["est_error_days"] is None else f"{r['est_error_days']:+d}", str(r["delay_days"]),
         f"v{r['plan_version']}" if r["plan_version"] else "no confirmed plan"]
        for r in rows
    ]  # fmt: skip
    note = (
        f"{summary['with_confirmed_plan']} of {summary['lines']} lines have an estimate in a confirmed plan; "
        + (
            f"on average the actual date was {summary['mean_abs_error_days']} days from the estimate."
            if matched
            else "none to compare yet."
        )
    )
    report = Report(
        "Plan versus actual dispatch",
        "Estimate in the latest confirmed plan against what happened"
        + (f" · {fmt_date(start)} to {fmt_date(end)}" if start or end else ""),
        [Table("Lines with an actual dispatch date", columns, body, note=note)],
        "plan-vs-actual",
    )
    return data, report


def parse_date(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({field: "Use a date like 2026-11-02."}) from exc
