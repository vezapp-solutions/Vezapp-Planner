"""Insight rules that read a calculated plan: at risk, bottlenecks, capacity, melting, balancing,
month-end forecast and concentration."""

import calendar
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from . import rules
from .format import fmt_date, indian, month_name, pct, plural, tonnes
from .model import (
    BalanceCandidate,
    Card,
    DayBottleneck,
    FurnaceDay,
    LineFact,
    LoadRow,
    MeltRow,
    scaled,
)

BAD = ("at_risk", "unscheduled")


def _late_working_days(line: LineFact) -> int:
    return (
        -line.slack_working_days
        if line.slack_working_days is not None and line.slack_working_days < 0
        else 0
    )


# --- 1. at-risk dispatches ------------------------------------------------------------------------
def at_risk(lines: Sequence[LineFact]) -> list[Card]:
    if not lines:
        return []
    total_pieces = sum(ln.qty for ln in lines) or 1
    bad = [ln for ln in lines if ln.status in BAD]
    if not bad:
        tight = sum(1 for ln in lines if ln.status == "tight")
        tail = f"; {tight} are tight (0 or 1 working day spare)." if tight else "."
        return [
            Card(
                key="at_risk:none", type="at_risk", severity="info",
                title="No lines are at risk",
                message=(
                    f"The {plural(len(lines), 'line')} {'is' if len(lines) == 1 else 'are'} estimated "
                    f"on or before {'its' if len(lines) == 1 else 'their'} internal date{tail}"
                ),
                numbers={"lines": len(lines), "at_risk": 0, "tight": tight},
                action="Nothing to do. Keep an eye on the tight lines.",
                why=("A line is at risk when its estimated dispatch date is after its internal date.",),
            )
        ]  # fmt: skip

    bad.sort(
        key=lambda ln: (
            ln.status != "unscheduled",
            -_late_working_days(ln),
            ln.internal_date,
            ln.line_id,
        )
    )
    unscheduled = [ln for ln in bad if ln.status == "unscheduled"]
    worst_days = max(_late_working_days(ln) for ln in bad)
    pieces_late = sum(ln.qty for ln in bad)
    held = Counter(ln.holding or "no single operation" for ln in bad)
    top_hold, top_n = held.most_common(1)[0]
    critical = bool(unscheduled) or worst_days >= rules.CRITICAL_LATE_WORKING_DAYS
    worst = bad[0]
    worst_text = (
        f"{worst.part_number} for {worst.customer_code} does not fit the planning window"
        if worst.status == "unscheduled"
        else f"the worst is {worst.part_number} for {worst.customer_code}, {plural(worst_days, 'working day')} late"
    )
    held_text = f", held up by {top_hold}" if worst.holding else ""
    summary = Card(
        key="at_risk:summary", type="at_risk",
        severity="critical" if critical else "warning",
        title=f"{plural(len(bad), 'line')} will miss {'their' if len(bad) > 1 else 'its'} internal date",
        message=f"{plural(len(bad), 'line')} ({indian(pieces_late)} pieces) are late; {worst_text}{held_text}.",
        numbers={
            "lines_at_risk": len(bad), "unscheduled": len(unscheduled), "pieces_late": pieces_late,
            "worst_working_days_late": worst_days, "held_up_by": dict(held),
        },
        entities={
            "lines": [ln.line_id for ln in bad[: rules.LISTED_LINES]],
            "customers": sorted({ln.customer_code for ln in bad}),
            "parts": sorted({ln.part_number for ln in bad}),
        },
        action=(
            f"Open Plan filtered to At risk. {top_hold} holds up {top_n} of them: add a shift or overtime "
            "there, or move internal dates."
            if top_hold != "no single operation"
            else "Open Plan filtered to At risk and review the dates."
        ),
        why=(
            "A line is at risk when its estimated dispatch date is after its internal date (fewer than 0 working days spare).",
            "Held up by is the operation whose work waited longest for capacity (see the line detail on Plan).",
            *[
                f"{ln.part_number} for {ln.customer_code}: internal {fmt_date(ln.internal_date)}, "
                + (
                    f"estimated {fmt_date(ln.est_date)} ({plural(_late_working_days(ln), 'working day')} late)"
                    if ln.est_date
                    else "not scheduled within the planning window"
                )
                for ln in bad[: rules.LISTED_LINES]
            ],
        ),
        impact=scaled(pieces_late, 0.2 * total_pieces),
    )  # fmt: skip
    cards = [summary]
    for ln in bad[: rules.WORST_LINES]:
        days = _late_working_days(ln)
        crit = ln.status == "unscheduled" or days >= rules.CRITICAL_LATE_WORKING_DAYS
        cards.append(
            Card(
                key=f"at_risk:line:{ln.line_id}", type="at_risk",
                severity="critical" if crit else "warning",
                title=(
                    f"{ln.part_number} for {ln.customer_code} is not scheduled"
                    if ln.status == "unscheduled"
                    else f"{ln.part_number} for {ln.customer_code} will be {plural(days, 'working day')} late"
                ),
                message=(
                    f"{indian(ln.qty)} pieces due {fmt_date(ln.internal_date)}"
                    + (f", estimated {fmt_date(ln.est_date)}" if ln.est_date else ", no date inside the planning window")
                    + (f". {ln.holding_text}" if ln.holding_text else ".")
                ),
                numbers={
                    "qty": ln.qty, "internal_date": ln.internal_date.isoformat(),
                    "est_date": ln.est_date.isoformat() if ln.est_date else None,
                    "working_days_late": days,
                },
                entities={"lines": [ln.line_id], "customers": [ln.customer_code], "parts": [ln.part_number]},
                action="Open the line on Plan to see where it waits, then add capacity there or move its date.",
                why=(ln.holding_text or "No single operation stands out.",),
                impact=scaled(ln.qty, 0.2 * total_pieces),
            )
        )  # fmt: skip
    return cards


# --- 2. bottleneck forecast -----------------------------------------------------------------------
def bottleneck_forecast(days: Sequence[DayBottleneck]) -> list[Card]:
    busy = [d for d in days if d.resource_code]
    if not busy:
        return []
    by_resource = Counter(d.resource_code for d in busy)
    # The bottleneck is the resource that gets fullest; when several are about equally full, the
    # one that is busiest on more days.
    top = max(
        by_resource,
        key=lambda c: (
            round(max(d.utilisation for d in busy if d.resource_code == c), 2),
            by_resource[c],
            c,
        ),
    )
    peak = max(
        (d for d in busy if d.resource_code == top),
        key=lambda d: (d.utilisation, -d.day.toordinal()),
    )
    hot = [d for d in busy if d.utilisation >= rules.HOT_UTIL]
    saturated = [d for d in busy if d.utilisation >= rules.SATURATED_UTIL]
    if len(saturated) >= rules.SATURATED_DAYS_CRITICAL:
        severity = "critical"
    elif hot:
        severity = "warning"
    else:
        severity = "info"
    return [
        Card(
            key="bottleneck:forecast", type="bottleneck_forecast", severity=severity,
            title=f"{top} is the bottleneck for the next {plural(len(days), 'working day')}",
            message=(
                f"{top} is the busiest resource on {by_resource[top]} of the next {len(days)} working days, "
                f"peaking at {pct(peak.utilisation)} on {fmt_date(peak.day)}."
            ),
            numbers={
                "top_resource": top, "days_as_busiest": by_resource[top],
                "peak_utilisation": round(peak.utilisation, 4), "peak_date": peak.day.isoformat(),
                "peak_resource": peak.resource_code, "days_hot": len(hot), "days_saturated": len(saturated),
                "by_resource": dict(by_resource),
                "days": [
                    {"date": d.day.isoformat(), "resource": d.resource_code, "utilisation": round(d.utilisation, 4)}
                    for d in days
                ],
            },
            entities={"resources": sorted(by_resource), "dates": [d.day.isoformat() for d in hot]},
            action=(
                f"Check the load heatmap for {peak.resource_code} around {fmt_date(peak.day)}; consider overtime or an extra shift."
                if hot
                else "Load is comfortable. No action needed."
            ),
            why=(
                "The busiest resource of a day is the one with the highest load ÷ capacity that day.",
                f"Hot means {pct(rules.HOT_UTIL)} or more; saturated means the resource is full.",
            ),
            impact=scaled(len(hot), max(len(days), 1)),
        )
    ]  # fmt: skip


# --- 3. capacity gap ------------------------------------------------------------------------------
def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def capacity_gap(loads: Sequence[LoadRow], avg_shift_minutes: Mapping[int, float]) -> list[Card]:
    weeks: dict[tuple[int, date], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    names: dict[int, tuple[str, str]] = {}
    for r in loads:
        acc = weeks[(r.resource_id, _week_start(r.day))]
        acc[0] += r.capacity
        acc[1] += r.load
        acc[2] += r.required
        names[r.resource_id] = (r.code, r.name)

    per_resource: dict[int, list[tuple[date, float, float, float]]] = defaultdict(list)
    for (rid, week), (cap, load, req) in sorted(weeks.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        per_resource[rid].append((week, cap, load, req))

    cards: list[Card] = []
    spare: list[tuple[float, Card]] = []
    for rid, rows in per_resource.items():
        code, name = names[rid]
        shift = avg_shift_minutes.get(rid) or 0.0
        short = []
        for week, cap, load, req in rows:
            gap = req - cap
            if gap > 1e-6:
                extra = math.ceil(gap / shift) if shift > 0 else None
                short.append({
                    "week_start": week.isoformat(), "capacity": round(cap, 1), "required": round(req, 1),
                    "load": round(load, 1), "shortfall": round(gap, 1), "extra_shifts": extra,
                })  # fmt: skip
        total_cap = sum(r[1] for r in rows)
        total_load = sum(r[2] for r in rows)
        total_req = sum(r[3] for r in rows)
        if short:
            first = max(short, key=lambda w: w["shortfall"])
            extra = first["extra_shifts"]
            share = first["shortfall"] / first["capacity"] if first["capacity"] else 1.0
            when = fmt_date(first["week_start"])
            need = (
                f"needs about {plural(extra, 'extra shift')}"
                if extra is not None
                else f"is short by about {indian(first['shortfall'] / 60, 1)} hours"
            )
            more = len(short) - 1
            total_extra = sum(w["extra_shifts"] or 0 for w in short)
            cards.append(
                Card(
                    key=f"capacity_gap:{rid}", type="capacity_gap",
                    severity="critical" if share >= rules.GAP_CRITICAL_SHARE else "warning",
                    title=f"{name} is short of capacity",
                    message=(
                        f"{name} {need} in the week of {when}"
                        + (f" and {plural(more, 'other week')} fall short too." if more else ".")
                    ),
                    numbers={
                        "resource": code, "weeks_short": len(short), "total_extra_shifts": total_extra,
                        "worst_week": first["week_start"], "weeks": short,
                    },
                    entities={"resources": [code], "dates": [w["week_start"] for w in short]},
                    action=f"Add {plural(extra or 1, 'shift')} or overtime for {name} in the week of {when}, or move lines' internal dates.",
                    why=(
                        "Required minutes come from walking each line back from its internal date with unlimited capacity.",
                        "Capacity is the shifts' working minutes × units × efficiency, less downtime.",
                        "Extra shifts = shortfall ÷ the resource's average shift capacity, rounded up.",
                    ),
                    impact=scaled(total_extra, 10),
                )
            )  # fmt: skip
        elif total_cap > 0 and (total_load > 0 or total_req > 0):
            util = total_load / total_cap
            if util < rules.SPARE_UTIL:
                spare.append((
                    util,
                    Card(
                        key=f"capacity_gap:spare:{rid}", type="capacity_gap", severity="info",
                        title=f"{name} has spare capacity",
                        message=f"{name} is at {pct(util)} over the plan; about {indian((total_cap - total_load) / 60)} working hours are free.",
                        numbers={
                            "resource": code, "utilisation": round(util, 4),
                            "spare_minutes": round(total_cap - total_load, 1),
                        },
                        entities={"resources": [code]},
                        action=f"Room to pull lines forward or take more orders on {name}.",
                        why=("Utilisation is planned load ÷ capacity summed over every shift of the plan.",),
                        impact=0.0,
                    ),
                ))  # fmt: skip
    cards.sort(key=lambda c: -c.rank)
    spare.sort(key=lambda t: t[0])
    return cards + [c for _, c in spare[: rules.MAX_SPARE_CARDS]]


# --- 4. melting -----------------------------------------------------------------------------------
def melting(melt: Sequence[MeltRow], furnace_days: Sequence[FurnaceDay]) -> list[Card]:
    cards: list[Card] = []
    if melt:
        per_day: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        per_grade: dict[str, float] = defaultdict(float)
        for m in melt:
            per_day[m.day][m.grade or "no grade"] += m.kg
            per_grade[m.grade or "no grade"] += m.kg
        days = sorted(per_day)
        peak_day = max(days, key=lambda d: (sum(per_day[d].values()), d))
        peak_kg = sum(per_day[peak_day].values())
        total_kg = sum(per_grade.values())
        split = ", ".join(
            f"{g} {tonnes(kg)}"
            for g, kg in sorted(per_day[peak_day].items(), key=lambda kv: -kv[1])
        )
        cards.append(
            Card(
                key="melting:tonnes", type="melting", severity="info",
                title="Planned melt by grade",
                message=(
                    f"{tonnes(total_kg)} of metal over {plural(len(days), 'day')}; the peak is {tonnes(peak_kg)} on "
                    f"{fmt_date(peak_day)} ({split})."
                ),
                numbers={
                    "total_tonnes": round(total_kg / 1000, 2), "by_grade": {g: round(kg / 1000, 2) for g, kg in per_grade.items()},
                    "peak_day": peak_day.isoformat(), "peak_tonnes": round(peak_kg / 1000, 2),
                    "days": [
                        {"date": d.isoformat(), "total_tonnes": round(sum(per_day[d].values()) / 1000, 2),
                         "grades": {g: round(kg / 1000, 2) for g, kg in per_day[d].items()}}
                        for d in days[: rules.MELT_DAYS_LISTED]
                    ],
                },
                entities={"dates": [peak_day.isoformat()], "grades": sorted(per_grade)},
                action="Group lines of the same grade on the same days where dates allow, to avoid alloy changes.",
                why=(
                    "Metal for a line is its pieces to pour × pouring weight, spread over the days its melting work is planned.",
                    "Only one alloy runs in a furnace in a period, so a day with several grades costs changeovers.",
                ),
                impact=0.0,
            )
        )  # fmt: skip

    by_furnace: dict[str, dict[date, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0.0])
    )
    for f in furnace_days:
        acc = by_furnace[f.code][f.day]
        acc[0] += f.load
        acc[1] += f.capacity
    for code, per in sorted(by_furnace.items()):
        working = sorted(d for d, (_, cap) in per.items() if cap > 0)
        loaded = [d for d in working if per[d][0] > 0]
        if not loaded:
            continue
        span = [d for d in working if loaded[0] <= d <= loaded[-1]]
        if len(span) < rules.UNEVEN_MIN_DAYS:
            continue
        utils = [per[d][0] / per[d][1] for d in span]
        mean = statistics.fmean(utils)
        cv = statistics.pstdev(utils) / mean if mean > 0 else 0.0
        full = sum(1 for u in utils if u >= rules.SATURATED_UTIL)
        quiet = sum(1 for u in utils if u <= rules.UNEVEN_LOW)
        if cv > rules.UNEVEN_CV or (full and quiet):
            cards.append(
                Card(
                    key=f"melting:uneven:{code}", type="melting", severity="warning",
                    title=f"{code} load is uneven",
                    message=f"{code} is full on {plural(full, 'day')} and under {pct(rules.UNEVEN_LOW)} on {plural(quiet, 'day')} between {fmt_date(span[0])} and {fmt_date(span[-1])}.",
                    numbers={
                        "furnace": code, "days": len(span), "full_days": full, "quiet_days": quiet,
                        "mean_utilisation": round(mean, 4), "variation": round(cv, 3),
                    },
                    entities={"resources": [code], "dates": [d.isoformat() for d in span if per[d][0] / per[d][1] <= rules.UNEVEN_LOW]},
                    action="Pull lines forward onto the quiet days or move internal dates so the furnace runs evenly.",
                    why=(
                        "Uneven means the day-to-day utilisation varies a lot (standard deviation over mean above "
                        f"{rules.UNEVEN_CV}) or the furnace is full on some days and under {pct(rules.UNEVEN_LOW)} on others.",
                    ),
                    impact=min(10.0, cv * 10),
                )
            )  # fmt: skip
    return cards


# --- 5. load balancing ----------------------------------------------------------------------------
def load_balancing(candidates: Sequence[BalanceCandidate]) -> list[Card]:
    good = [c for c in candidates if c.from_util - c.to_util >= rules.BALANCE_MIN_GAP]
    good.sort(key=lambda c: (-(c.from_util - c.to_util) * c.pieces, c.part_number, c.to_code))
    cards = []
    for c in good[: rules.MAX_BALANCE_CARDS]:
        cards.append(
            Card(
                key=f"load_balancing:{c.part_id}:{c.op_code}:{c.to_id}", type="load_balancing", severity="warning",
                title=f"Allow {c.to_code} for {c.op_name} of {c.part_number}",
                message=(
                    f"{c.from_code} is at {pct(c.from_util)} while {c.to_code} is at {pct(c.to_util)}; "
                    f"{c.op_name} of {c.part_number} is only allowed on {c.from_code}."
                ),
                numbers={
                    "from_resource": c.from_code, "from_utilisation": round(c.from_util, 4),
                    "to_resource": c.to_code, "to_utilisation": round(c.to_util, 4), "pieces": c.pieces,
                },
                entities={
                    "parts": [c.part_number], "resources": [c.from_code, c.to_code],
                    "dry_run": {"part_id": c.part_id, "op_code": c.op_code, "resource_id": c.to_id},
                },
                action=f"Allow {c.to_code} on the {c.part_number} route (Masters, Parts and routes), then press Test it to see the effect.",
                why=(
                    "The planner gives each piece of work to the allowed resource with most free time, so a resource that is not allowed never takes load.",
                    "Utilisation is load ÷ capacity on the days a resource has work in the next 14 working days.",
                    f"A suggestion needs the alternative to be at least {pct(rules.BALANCE_MIN_GAP)} less loaded.",
                    "Test it runs the plan twice, with and without the change, and shows which lines move. Nothing is changed.",
                ),
                impact=min(10.0, (c.from_util - c.to_util) * 10),
            )
        )  # fmt: skip
    return cards


# --- 7. month-end forecast ------------------------------------------------------------------------
def _month_bounds(today: date) -> tuple[date, date]:
    return today.replace(day=1), today.replace(day=calendar.monthrange(today.year, today.month)[1])


def month_forecast(lines: Sequence[LineFact], today: date) -> list[Card]:
    first, last = _month_bounds(today)
    scope = [ln for ln in lines if first <= ln.internal_date <= last]
    if not scope:
        return []
    done = [ln for ln in scope if ln.est_date is not None and ln.est_date <= last]
    slipping = [ln for ln in scope if ln not in done]
    plan_qty, fc_qty = sum(ln.qty for ln in scope), sum(ln.qty for ln in done)
    plan_t, fc_t = sum(ln.tonnes for ln in scope), sum(ln.tonnes for ln in done)
    priced = [ln for ln in scope if ln.price is not None]
    plan_v = sum((ln.price or 0.0) * ln.qty for ln in scope)
    fc_v = sum((ln.price or 0.0) * ln.qty for ln in done)
    unpriced = len(scope) - len(priced)
    short = 1 - fc_qty / plan_qty
    severity = (
        "critical" if short >= rules.MONTH_SHORT_CRITICAL else "warning" if slipping else "info"
    )
    value = f", worth ₹{indian(fc_v)} of ₹{indian(plan_v)}" if priced else ""
    month = month_name(today.year, today.month)
    return [
        Card(
            key="month_forecast", type="month_forecast", severity=severity,
            title=f"{month}: {pct(fc_qty / plan_qty)} of planned pieces forecast to dispatch",
            message=(
                f"{indian(fc_qty)} of {indian(plan_qty)} pieces ({indian(fc_t, 1)} of {indian(plan_t, 1)} t{value}) are estimated by "
                f"{fmt_date(last)}; {plural(len(slipping), 'line')} slip into next month."
            ),
            numbers={
                "month": today.strftime("%Y-%m"), "planned_qty": plan_qty, "forecast_qty": fc_qty,
                "planned_tonnes": round(plan_t, 2), "forecast_tonnes": round(fc_t, 2),
                "planned_value": round(plan_v, 2), "forecast_value": round(fc_v, 2),
                "lines_without_price": unpriced, "slipping_lines": len(slipping),
            },
            entities={"lines": [ln.line_id for ln in slipping[: rules.SLIPPING_LISTED]]},
            action=(
                f"Review the {plural(len(slipping), 'slipping line')} on Plan, or move their dates deliberately."
                if slipping
                else "On course for the month."
            ),
            why=(
                f"Scope: lines whose internal date is in {month}. Forecast: those with an estimated date on or before {fmt_date(last)}.",
                "Weight is casting weight × quantity; value uses each part's selling price"
                + (f" ({plural(unpriced, 'line')} have no price and add nothing)." if unpriced else "."),
            ),
            impact=min(10.0, short * 10),
        )
    ]  # fmt: skip


# --- 8. concentration and mix ----------------------------------------------------------------------
def concentration(
    lines: Sequence[LineFact], history: Mapping[int, Sequence[int]], today: date
) -> list[Card]:
    first, last = _month_bounds(today)
    scope = [ln for ln in lines if first <= ln.internal_date <= last]
    total = sum(ln.tonnes for ln in scope)
    cards: list[Card] = []
    if scope and total > 0:
        by_customer: dict[str, float] = defaultdict(float)
        by_grade: dict[str, float] = defaultdict(float)
        for ln in scope:
            by_customer[ln.customer_code] += ln.tonnes
            by_grade[ln.grade or "no grade"] += ln.tonnes
        top_c = sorted(by_customer.items(), key=lambda kv: -kv[1])[: rules.CONCENTRATION_TOP_N]
        top_g = sorted(by_grade.items(), key=lambda kv: -kv[1])[: rules.CONCENTRATION_TOP_N]
        share_c = sum(t for _, t in top_c) / total
        lead_share = top_c[0][1] / total
        month = month_name(today.year, today.month)
        cards.append(
            Card(
                key="concentration:mix", type="concentration",
                severity="warning" if lead_share >= rules.CONCENTRATION_WARN_SHARE else "info",
                title=f"Top {plural(len(top_c), 'customer')} make up {pct(share_c)} of {month}",
                message=(
                    f"{top_c[0][0]} alone is {pct(lead_share)} of the month's {indian(total, 1)} t; "
                    f"the top grade is {top_g[0][0]} at {pct(top_g[0][1] / total)}."
                ),
                numbers={
                    "month": today.strftime("%Y-%m"), "total_tonnes": round(total, 2),
                    "customers": [{"code": c, "tonnes": round(t, 2), "share": round(t / total, 4)} for c, t in top_c],
                    "grades": [{"grade": g, "tonnes": round(t, 2), "share": round(t / total, 4)} for g, t in top_g],
                },
                entities={"customers": [c for c, _ in top_c], "grades": [g for g, _ in top_g]},
                action=(
                    f"A single customer ({top_c[0][0]}) dominates the month: check capacity is not tied to one order book."
                    if lead_share >= rules.CONCENTRATION_WARN_SHARE
                    else "No single customer dominates the month. No action needed."
                ),
                why=(f"Share = tonnes (casting weight × quantity) of lines with an internal date in {month}, by customer and by grade.",),
                impact=min(10.0, lead_share * 10) if lead_share >= rules.CONCENTRATION_WARN_SHARE else 0.0,
            )
        )  # fmt: skip

    unusual = []
    for ln in scope:
        past = history.get(ln.part_id, ())
        if len(past) >= rules.LARGE_MIN_HISTORY:
            usual = statistics.median(past)
            if usual > 0 and ln.qty >= rules.LARGE_FACTOR * usual:
                unusual.append((ln.qty / usual, usual, ln))
    unusual.sort(key=lambda t: -t[0])
    for ratio, usual, ln in unusual[: rules.MAX_LARGE_CARDS]:
        cards.append(
            Card(
                key=f"concentration:large:{ln.line_id}", type="concentration", severity="info",
                title=f"{ln.part_number} for {ln.customer_code} is unusually large",
                message=f"{indian(ln.qty)} pieces is {ratio:.1f} times the usual {indian(usual)} for this part.",
                numbers={"qty": ln.qty, "usual_qty": usual, "ratio": round(ratio, 2), "history_lines": len(history[ln.part_id])},
                entities={"lines": [ln.line_id], "parts": [ln.part_number], "customers": [ln.customer_code]},
                action="Confirm the quantity with the customer; a typing slip here would take real capacity.",
                why=(
                    f"Flagged when a line is at least {rules.LARGE_FACTOR:g} times the median of the part's other lines "
                    f"(needs {rules.LARGE_MIN_HISTORY} or more).",
                ),
                impact=min(10.0, ratio),
            )
        )  # fmt: skip
    return cards
