"""Working calendar maths: shift minutes, shift windows, usable capacity.

Pure Python, no Django. Times are naive local (Asia/Kolkata) wall-clock values.
A shift that crosses midnight belongs to the day it starts.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from .trace import Traced

DAY_MINUTES = 24 * 60


@dataclass(frozen=True)
class ShiftSpec:
    id: int
    name: str
    start: time
    end: time
    break_minutes: int = 0


@dataclass(frozen=True)
class ShiftInstance:
    day: date
    shift: ShiftSpec
    start: datetime
    end: datetime
    minutes: int


def gross_minutes(start: time, end: time) -> int:
    """Clock minutes from start to end. End at or before start means the shift crosses midnight."""
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    if e == s:
        raise ValueError("A shift cannot start and end at the same time.")
    return (e - s) % DAY_MINUTES


def crosses_midnight(start: time, end: time) -> bool:
    return (end.hour * 60 + end.minute) < (start.hour * 60 + start.minute)


def shift_minutes(start: time, end: time, break_minutes: int) -> int:
    """Net working minutes in a shift: clock time minus the break."""
    net = gross_minutes(start, end) - break_minutes
    if net <= 0:
        raise ValueError("The break is as long as the whole shift.")
    return net


def shift_window(day: date, shift: ShiftSpec) -> tuple[datetime, datetime]:
    start = datetime.combine(day, shift.start)
    return start, start + timedelta(minutes=gross_minutes(shift.start, shift.end))


def overlap_minutes(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> Decimal:
    latest_start = max(a_start, b_start)
    earliest_end = min(a_end, b_end)
    if earliest_end <= latest_start:
        return Decimal(0)
    return Decimal((earliest_end - latest_start).total_seconds()) / 60


def merge_intervals(
    intervals: Sequence[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Union of possibly overlapping blocked periods, so downtime is never counted twice."""
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def usable_minutes(
    shift_net_minutes: int | Decimal,
    units: int,
    efficiency_pct: Decimal | int | float,
    downtime_minutes: Decimal | int = 0,
) -> Traced:
    """Capacity of a resource in one bucket: bucket minutes x units x efficiency - downtime."""
    efficiency = Decimal(str(efficiency_pct))
    gross = Decimal(shift_net_minutes) * units * efficiency / 100
    value = max(gross - Decimal(downtime_minutes), Decimal(0))
    return Traced(
        value=value,
        formula="bucket minutes × units × efficiency% ÷ 100 − downtime minutes (not below 0)",
        inputs={
            "bucket_minutes": Decimal(shift_net_minutes),
            "units": units,
            "efficiency_pct": efficiency,
            "downtime_minutes": Decimal(downtime_minutes),
        },
    )


def heats_per_bucket(
    usable: Decimal, minutes_per_heat: Decimal, max_heats: int | None = None
) -> Traced:
    """Whole heats a furnace can tap in a bucket (a heat cannot be started and left unfinished)."""
    whole = int(usable // minutes_per_heat) if minutes_per_heat > 0 else 0
    note = ""
    if max_heats is not None and whole > max_heats:
        whole, note = max_heats, "limited by max heats per shift"
    return Traced(
        value=whole,
        formula="floor(usable minutes ÷ minutes per heat), capped at max heats per shift if set",
        inputs={
            "usable_minutes": usable,
            "minutes_per_heat": minutes_per_heat,
            "max_heats": max_heats,
        },
        note=note,
    )


def shift_instances(
    week: Mapping[int, Sequence[ShiftSpec]],
    holidays: Mapping[date, frozenset[int] | None],
    start: date,
    end: date,
) -> list[ShiftInstance]:
    """Every shift that actually runs from start to end (inclusive).

    week maps weekday (0=Monday) to that day's shifts. holidays maps a date to None for a full
    holiday, or to the set of shift ids that are off that day.
    """
    out: list[ShiftInstance] = []
    day = start
    while day <= end:
        if day in holidays and holidays[day] is None:
            day += timedelta(days=1)
            continue
        shifts_off = holidays.get(day) or frozenset()
        for shift in sorted(week.get(day.weekday(), ()), key=lambda s: (s.start, s.id)):
            if shift.id in shifts_off:
                continue
            window_start, window_end = shift_window(day, shift)
            out.append(
                ShiftInstance(
                    day=day,
                    shift=shift,
                    start=window_start,
                    end=window_end,
                    minutes=shift_minutes(shift.start, shift.end, shift.break_minutes),
                )
            )
        day += timedelta(days=1)
    return out
