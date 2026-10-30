"""Status, holding operation and bottlenecks."""

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal

from .ledger import ZERO
from .model import DayBottleneck, LineStatus, LoadCell, OpResult
from .timeline import Timeline


def classify(slack_working_days: int) -> LineStatus:
    """On Track: two or more working days spare. Tight: 0 or 1. At Risk: late."""
    if slack_working_days >= 2:
        return "on_track"
    if slack_working_days >= 0:
        return "tight"
    return "at_risk"


def day_of(timeline: Timeline, moment: datetime) -> date:
    """The working day a finish time belongs to (a night shift belongs to the day it started)."""
    probe = moment - timedelta(minutes=1)
    i = timeline.first_slot_after(probe)
    if i < len(timeline) and timeline.slots[i].start <= probe:
        return timeline.slots[i].day
    return moment.date()


MIN_WAIT_HOURS = Decimal(6)


def holding_operation(ops: list[OpResult], timeline: Timeline) -> tuple[str | None, str]:
    """The operation that held the line up most.

    Normally the one whose work waited longest for capacity once it was ready (queueing, which is
    where a bottleneck shows). When nothing waited, the operation that takes the longest.
    """
    best_wait: OpResult | None = None
    longest: tuple[Decimal, OpResult] | None = None
    for op in ops:
        if op.finish_at is not None and op.latest_finish is not None:
            op.delay_days = timeline.working_days_between(
                day_of(timeline, op.latest_finish), day_of(timeline, op.finish_at)
            )
        wait = op.wait_hours or ZERO
        if wait >= MIN_WAIT_HOURS and (best_wait is None or wait > (best_wait.wait_hours or ZERO)):
            best_wait = op
        if op.start_at and op.finish_at:
            span = Decimal((op.finish_at - op.start_at).total_seconds()) / 3600
            if longest is None or span > longest[0]:
                longest = (span, op)
    if best_wait is not None:
        days = (best_wait.wait_hours or ZERO) / 24
        return (
            best_wait.code,
            f"{best_wait.name} held it up: its work waited about {days:.1f} days on average for capacity.",
        )
    if longest is not None:
        days = longest[0] / 24
        return longest[
            1
        ].code, f"{longest[1].name} takes the longest ({days:.1f} days from first to last piece)."
    return None, ""


def peak_utilisation(
    timeline: Timeline, loads: Mapping[tuple[int, int], LoadCell]
) -> dict[int, Decimal]:
    """Highest single-day utilisation of each resource that has any load."""
    per_day: dict[tuple[int, date], list[Decimal]] = {}
    for (rid, idx), cell in loads.items():
        acc = per_day.setdefault((rid, timeline.slots[idx].day), [ZERO, ZERO])
        acc[0] += cell.load
        acc[1] += cell.capacity
    peaks: dict[int, Decimal] = {}
    for (rid, _), (load, cap) in per_day.items():
        if load > 0 and cap > 0:
            peaks[rid] = max(peaks.get(rid, ZERO), load / cap)
    return peaks


def bottlenecks(
    timeline: Timeline, loads: Mapping[tuple[int, int], LoadCell], codes: Mapping[int, str]
) -> tuple[list[DayBottleneck], int | None]:
    per_day: dict[date, dict[int, list[Decimal]]] = {}
    for (rid, idx), cell in loads.items():
        day = timeline.slots[idx].day
        acc = per_day.setdefault(day, {}).setdefault(rid, [ZERO, ZERO])
        acc[0] += cell.load
        acc[1] += cell.capacity

    result: list[DayBottleneck] = []
    peak: dict[int, Decimal] = {}
    total: dict[int, Decimal] = {}
    for day in sorted(per_day):
        best = None
        for rid, (load, cap) in per_day[day].items():
            if load <= 0 or cap <= 0:
                continue
            util = load / cap
            peak[rid] = max(peak.get(rid, ZERO), util)
            total[rid] = total.get(rid, ZERO) + load
            key = (util, load, [-ord(c) for c in codes.get(rid, "")])
            if best is None or key > best[0]:
                best = (key, rid, util, load, cap)
        if best:
            _, rid, util, load, cap = best
            result.append(DayBottleneck(day, rid, util, load, cap))
    overall = max(peak, key=lambda r: (peak[r], total.get(r, ZERO))) if peak else None
    return result, overall
