"""Capacity ledger: minutes available and used per resource per shift slot."""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from .calendar import merge_intervals, overlap_minutes, usable_minutes
from .model import ExtraShift, Overtime, ResourceSpec
from .timeline import Timeline

EPS = Decimal("0.000001")
ZERO = Decimal(0)


def window_fraction(slot_start: datetime, slot_end: datetime, ready: datetime | None) -> Decimal:
    """Share of the slot that is still ahead of the moment the work becomes ready."""
    if ready is None or ready <= slot_start:
        return Decimal(1)
    if ready >= slot_end:
        return ZERO
    return Decimal((slot_end - ready).total_seconds()) / Decimal(
        (slot_end - slot_start).total_seconds()
    )


class Ledger:
    def __init__(
        self,
        timeline: Timeline,
        resources: Sequence[ResourceSpec],
        extra_shifts: Sequence[ExtraShift] = (),
        overtime: Sequence[Overtime] = (),
    ):
        self.timeline = timeline
        extra_for = {e.shift.id: e.resource_ids for e in extra_shifts}
        n = len(timeline)
        self.cap: dict[int, list[Decimal]] = {}
        self.used: dict[int, list[Decimal]] = {}
        self.first_open: dict[int, int] = {}
        self.heats_used: dict[tuple[int, int], int] = {}
        for r in resources:
            blocked = merge_intervals(list(r.downtimes))
            caps: list[Decimal] = []
            for slot in timeline.slots:
                if slot.shift_id in extra_for:
                    named = extra_for[slot.shift_id]
                    works = (not r.shift_ids) if named is None else r.id in named
                else:
                    works = not r.shift_ids or slot.shift_id in r.shift_ids
                if not r.active or not works:
                    caps.append(ZERO)
                    continue
                down = sum(
                    (overlap_minutes(slot.start, slot.end, b0, b1) for b0, b1 in blocked), ZERO
                )
                cap = usable_minutes(slot.minutes, r.units, r.efficiency_pct, down).value
                for ot in overtime:
                    if (
                        ot.day_from <= slot.day <= ot.day_to
                        and (ot.shift_id is None or ot.shift_id == slot.shift_id)
                        and (ot.resource_ids is None or r.id in ot.resource_ids)
                    ):
                        cap += Decimal(ot.minutes) * r.units * r.efficiency_pct / 100
                caps.append(cap)
            self.cap[r.id] = caps
            self.used[r.id] = [ZERO] * n
            self.first_open[r.id] = 0

    def free(self, rid: int, idx: int) -> Decimal:
        return self.cap[rid][idx] - self.used[rid][idx]

    def avail(self, rid: int, idx: int, ready: datetime | None = None) -> Decimal:
        """Minutes usable by work that becomes ready at `ready`.

        Earlier work fills the front of a slot, so a late release only sees the part of the
        slot that is both still ahead and not yet used.
        """
        cap, used = self.cap[rid][idx], self.used[rid][idx]
        if ready is None:
            return max(cap - used, ZERO)
        slot = self.timeline.slots[idx]
        frac = window_fraction(slot.start, slot.end, ready)
        return max(cap - max(used, cap * (1 - frac)), ZERO)

    def take(self, rid: int, idx: int, minutes: Decimal) -> None:
        self.used[rid][idx] += minutes

    def earliest_open(self, rids: Sequence[int], from_idx: int) -> int:
        """First slot at or after from_idx where any of these resources may still have room."""
        best = len(self.timeline)
        for rid in rids:
            i = self.first_open[rid]
            n = len(self.timeline)
            while i < n and self.cap[rid][i] - self.used[rid][i] <= EPS:
                i += 1
            self.first_open[rid] = i
            best = min(best, i)
        return max(best, from_idx)
