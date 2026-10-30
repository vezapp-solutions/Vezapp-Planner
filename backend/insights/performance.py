"""Dispatch performance from actual dispatch dates. On time means the actual date is on or before the
internal date; delay is the days after it. Shared by the cards, the report and the assistant."""

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from . import rules
from .format import indian, month_name, pct, plural
from .model import Card, DispatchRow, scaled


def group_stats(
    rows: Sequence[DispatchRow], key: Callable[[DispatchRow], str]
) -> list[dict[str, Any]]:
    groups: dict[str, list[DispatchRow]] = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    out = []
    for name, items in groups.items():
        late = [r for r in items if not r.on_time]
        delays = [r.delay_days for r in late]
        out.append({
            "group": name, "lines": len(items), "pieces": sum(r.qty for r in items),
            "on_time": len(items) - len(late), "late": len(late),
            "on_time_pct": round((len(items) - len(late)) / len(items), 4),
            "avg_delay_days": round(sum(delays) / len(delays), 2) if delays else 0.0,
            "max_delay_days": max(delays) if delays else 0,
        })  # fmt: skip
    return out


def by_customer(rows: Sequence[DispatchRow]) -> list[dict[str, Any]]:
    stats = group_stats(rows, lambda r: r.customer_code)
    names = {r.customer_code: r.customer_name for r in rows}
    for s in stats:
        s["name"] = names[s["group"]]
    return sorted(stats, key=lambda s: (s["on_time_pct"], -s["lines"], s["group"]))


def by_part(rows: Sequence[DispatchRow]) -> list[dict[str, Any]]:
    return sorted(
        group_stats(rows, lambda r: r.part_number),
        key=lambda s: (s["on_time_pct"], -s["lines"], s["group"]),
    )


def by_month(rows: Sequence[DispatchRow]) -> list[dict[str, Any]]:
    """By month of the actual dispatch date, oldest first."""
    return sorted(
        group_stats(rows, lambda r: r.actual_date.strftime("%Y-%m")), key=lambda s: s["group"]
    )


def _previous_month(today: date) -> str:
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f"{year}-{month:02d}"


def dispatch_cards(rows: Sequence[DispatchRow], today: date) -> list[Card]:
    if not rows:
        return []
    months = {m["group"]: m for m in by_month(rows)}
    this_key, prev_key = today.strftime("%Y-%m"), _previous_month(today)
    current = months.get(this_key) or months[max(months)]
    prev = months.get(prev_key) if current["group"] == this_key else None
    label = month_name(int(current["group"][:4]), int(current["group"][5:]))
    on_time = current["on_time_pct"]
    severity = (
        "critical"
        if on_time < rules.ON_TIME_CRITICAL
        else "warning"
        if on_time < rules.ON_TIME_WARN
        else "info"
    )
    trend = ""
    if prev:
        delta = round((on_time - prev["on_time_pct"]) * 100)
        trend = (
            f", {abs(delta)} points {'up' if delta > 0 else 'down'} on {pct(prev['on_time_pct'])} the month before"
            if delta
            else f", unchanged from {pct(prev['on_time_pct'])} the month before"
        )
    cards = [
        Card(
            key="dispatch:overall", type="dispatch_performance", severity=severity,
            title=f"{pct(on_time)} of lines dispatched on time in {label}",
            message=(
                f"{current['on_time']} of {plural(current['lines'], 'line')} left on or before the internal date{trend}; "
                f"late lines averaged {indian(current['avg_delay_days'], 1)} days late."
            ),
            numbers={
                "month": current["group"], "lines": current["lines"], "on_time": current["on_time"],
                "late": current["late"], "on_time_pct": on_time, "avg_delay_days": current["avg_delay_days"],
                "previous_on_time_pct": prev["on_time_pct"] if prev else None,
                "months": list(months.values()),
            },
            entities={},
            action="See Reports, Dispatch performance, for the customers and parts behind the late lines." if current["late"] else "Keep it up.",
            why=(
                "On time means the actual dispatch date is on or before the internal dispatch date.",
                "Delay is the number of days after the internal date. The month is the month of the actual dispatch date.",
            ),
            impact=scaled(current["late"], 10),
        )
    ]  # fmt: skip
    for noun, stats in (("customer", by_customer(rows)), ("part", by_part(rows))):
        repeat = [
            s
            for s in stats
            if s["lines"] >= rules.REPEAT_MIN_LINES and s["on_time_pct"] < rules.REPEAT_ON_TIME
        ][: rules.MAX_REPEAT_CARDS]
        for s in repeat:
            label_name = f"{s['group']} ({s['name']})" if noun == "customer" else s["group"]
            cards.append(
                Card(
                    key=f"dispatch:{noun}:{s['group']}", type="dispatch_performance", severity="warning",
                    title=f"{s['group']} is repeatedly late",
                    message=(
                        f"{label_name}: {s['late']} of {plural(s['lines'], 'line')} dispatched late "
                        f"({pct(s['on_time_pct'])} on time), {indian(s['avg_delay_days'], 1)} days late on average."
                    ),
                    numbers={k: s[k] for k in ("lines", "on_time", "late", "on_time_pct", "avg_delay_days", "max_delay_days")},
                    entities={f"{noun}s": [s["group"]]},
                    action=f"Look at why {s['group']} slips: capacity on its route, or internal dates set too tight.",
                    why=(
                        f"Flagged when a {noun} has {rules.REPEAT_MIN_LINES} or more dispatched lines and under "
                        f"{pct(rules.REPEAT_ON_TIME)} of them on time.",
                    ),
                    impact=scaled(s["late"], 10),
                )
            )  # fmt: skip
    return cards
