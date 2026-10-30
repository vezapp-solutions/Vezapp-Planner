"""The plan's shift-by-shift timeline."""

from bisect import bisect_right
from datetime import date, datetime, timedelta

from .calendar import ShiftInstance, shift_instances, shift_minutes, shift_window
from .model import PlanInput, Slot


class Timeline:
    def __init__(self, slots: list[Slot]):
        self.slots = slots
        self._ends = [s.end for s in slots]
        self.by_day: dict[date, list[int]] = {}
        for s in slots:
            self.by_day.setdefault(s.day, []).append(s.idx)
        self.days = sorted(self.by_day)
        self._day_index = {d: i for i, d in enumerate(self.days)}

    def __len__(self) -> int:
        return len(self.slots)

    def first_slot_after(self, moment: datetime) -> int:
        """Index of the first slot that ends after the moment (the slot it falls in, or the next)."""
        return bisect_right(self._ends, moment)

    def day_end(self, day: date) -> datetime:
        return max(self.slots[i].end for i in self.by_day[day])

    def working_days_between(self, a: date, b: date) -> int:
        """Signed count of working days from a to b: positive when b is later.

        Counts the working days in (a, b] when b > a and -(days in (b, a]) when b < a.
        """
        if a == b:
            return 0
        low, high = (a, b) if a < b else (b, a)
        count = sum(1 for d in self.days if low < d <= high)
        return count if b > a else -count

    def slot_containing_or_before(self, moment: datetime) -> int:
        """Last slot that starts at or before the moment (0 if none)."""
        lo = 0
        for i, s in enumerate(self.slots):
            if s.start <= moment:
                lo = i
            else:
                break
        return lo


def build_timeline(inp: PlanInput) -> Timeline:
    s = inp.settings
    last_internal = max((ln.internal_date for ln in inp.lines), default=s.plan_from)
    end = max(
        s.plan_from + timedelta(days=s.horizon_days - 1),
        last_internal + timedelta(days=30),
    )
    end = min(end, s.plan_from + timedelta(days=s.max_window_days))
    instances = shift_instances(inp.week, inp.holidays, s.plan_from, end)
    instances = _with_extra_shifts(instances, inp, end)
    slots = [
        Slot(i, ins.day, ins.shift.id, ins.shift.name, ins.start, ins.end, ins.minutes)
        for i, ins in enumerate(instances)
    ]
    return Timeline(slots)


def _with_extra_shifts(instances, inp: PlanInput, end: date):
    """Add one-off shifts. The timeline must stay in time order with no overlaps, so an extra
    shift that overlaps a slot already there is left out (the screens refuse such a shift)."""
    if not inp.extra_shifts:
        return instances
    merged = list(instances)
    for extra in inp.extra_shifts:
        day = max(extra.day_from, inp.settings.plan_from)
        while day <= min(extra.day_to, end):
            start, finish = shift_window(day, extra.shift)
            merged.append(
                ShiftInstance(
                    day, extra.shift, start, finish,
                    shift_minutes(extra.shift.start, extra.shift.end, extra.shift.break_minutes),
                )
            )  # fmt: skip
            day += timedelta(days=1)
    merged.sort(key=lambda i: (i.start, i.shift.id))
    clean: list = []
    for item in merged:
        if clean and item.start < clean[-1].end:
            continue
        clean.append(item)
    return clean
