"""Backward pass (infinite capacity): the latest each operation may start and finish.

Walks back from the internal dispatch date, subtracting each operation's working-time duration
and the waits between steps. The same walk spreads each operation's minutes over the shifts it
must run in, which gives the *required load* to compare with capacity.
"""

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal

from .explode import resources_of
from .ledger import ZERO
from .model import LineInput, PartSpec, Requirement, ResourceSpec
from .timeline import Timeline


def parallel_factor(op, res: Mapping[int, ResourceSpec]) -> Decimal:
    """How many minutes of work the op's resources absorb per clock minute (units × efficiency)."""
    members = [r for r in resources_of(op, res) if r.active]
    if not members:
        return Decimal(1)
    return sum((Decimal(r.units) * r.efficiency_pct / 100 for r in members), ZERO) or Decimal(1)


def deadline_for(timeline: Timeline, day: date) -> datetime:
    """Latest moment of work on a dispatch date; the last working day before it when it is not one."""
    if day in timeline.by_day:
        return timeline.day_end(day)
    earlier = [d for d in timeline.days if d < day]
    return timeline.day_end(earlier[-1]) if earlier else timeline.slots[0].start


def back_working(timeline: Timeline, end: datetime, minutes: Decimal) -> datetime:
    """The moment `minutes` of working time before `end` (clamped to the start of the plan)."""
    remaining = minutes
    i = timeline.first_slot_after(end - timedelta(microseconds=1))
    if i >= len(timeline):
        i = len(timeline) - 1
    while i >= 0 and remaining > 0:
        slot = timeline.slots[i]
        stop = min(end, slot.end)
        if stop <= slot.start:
            i -= 1
            continue
        clock = Decimal((slot.end - slot.start).total_seconds())
        usable = Decimal(slot.minutes) * Decimal((stop - slot.start).total_seconds()) / clock
        if usable >= remaining:
            seconds = clock * remaining / Decimal(slot.minutes)
            return stop - timedelta(seconds=float(seconds))
        remaining -= usable
        i -= 1
    return timeline.slots[0].start


def backward_pass(
    line: LineInput,
    part: PartSpec,
    req: Requirement,
    timeline: Timeline,
    res: Mapping[int, ResourceSpec],
) -> tuple[dict[str, tuple[datetime, datetime]], dict[tuple[int, int], Decimal]]:
    """Returns ({op code: (latest start, latest finish)}, {(resource id, slot idx): required minutes})."""
    windows: dict[str, tuple[datetime, datetime]] = {}
    required: dict[tuple[int, int], Decimal] = {}
    if not len(timeline):
        return windows, required

    def duration(op) -> Decimal:
        return req.minutes.get(op.code, ZERO) / parallel_factor(op, res)

    finish = deadline_for(timeline, line.internal_date)
    ops = list(part.ops)
    i = len(ops) - 1
    while i >= 0:
        op = ops[i]
        if op.kind == "melting" and i > 0 and ops[i - 1].kind == "moulding":
            moulding = ops[i - 1]  # poured as they are moulded, so the two run side by side
            m_start = back_working(timeline, finish, duration(moulding))
            p_start = back_working(timeline, finish, duration(op))
            windows[op.code] = (p_start, finish)
            windows[moulding.code] = (m_start, finish)
            start = min(m_start, p_start)
            finish = start
            i -= 2
            continue
        if op.outsourced:
            start = finish - timedelta(days=op.lead_days or 0)
        else:
            start = back_working(timeline, finish, duration(op))
        windows[op.code] = (start, finish)
        # the wait after the previous step comes off before this one may start
        prev_lag = ops[i - 1].lag_hours if i > 0 else ZERO
        if i > 0 and ops[i - 1].kind == "melting":
            prev_lag += Decimal(str(ops[i - 1].extra.get("cooling_hours") or 0))
        finish = start - timedelta(seconds=float(prev_lag * 3600))
        i -= 1

    for op in ops:
        if op.outsourced or op.code not in windows:
            continue
        members = [r for r in resources_of(op, res) if r.active]
        if not members:
            continue
        minutes = req.minutes.get(op.code, ZERO)
        if minutes <= 0:
            continue
        start, end = windows[op.code]
        lo = timeline.first_slot_after(start)
        hi = timeline.first_slot_after(end - timedelta(microseconds=1))
        indices = [k for k in range(lo, min(hi, len(timeline) - 1) + 1) if k < len(timeline)] or [
            min(lo, len(timeline) - 1)
        ]
        weights = {k: Decimal(timeline.slots[k].minutes) for k in indices}
        total_w = sum(weights.values(), ZERO) or Decimal(1)
        shares = {r.id: Decimal(r.units) * r.efficiency_pct for r in members}
        total_s = sum(shares.values(), ZERO) or Decimal(1)
        for k in indices:
            for rid, share in shares.items():
                required[(rid, k)] = (
                    required.get((rid, k), ZERO) + minutes * weights[k] / total_w * share / total_s
                )
    return windows, required
