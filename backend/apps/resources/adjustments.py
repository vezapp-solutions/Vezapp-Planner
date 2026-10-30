"""Checks shared by capacity adjustments and what-if changes that add a shift."""

from datetime import date, time, timedelta

from apps.companies.calendar_data import load_week
from planning.calendar import ShiftSpec, overlap_minutes, shift_minutes, shift_window

from .models import AdjustmentKind, CapacityAdjustment

MAX_RANGE_DAYS = 92


def extra_shift_problem(
    company,
    day_from: date,
    day_to: date,
    start: time,
    end: time,
    break_minutes: int,
    exclude_id: int | None = None,
) -> str | None:
    """Why this extra shift cannot be added, or None. It must be a real shift and must not overlap
    a regular shift or another extra shift on any of its days."""
    if day_to < day_from:
        return "The last day cannot be before the first day."
    if (day_to - day_from).days + 1 > MAX_RANGE_DAYS:
        return f"Choose at most {MAX_RANGE_DAYS} days."
    try:
        shift_minutes(start, end, break_minutes)
    except ValueError as exc:
        return str(exc)

    candidate = ShiftSpec(0, "extra", start, end, break_minutes)
    week = load_week(company)
    others = list(
        CapacityAdjustment.objects.for_company(company)
        .filter(kind=AdjustmentKind.EXTRA_SHIFT, day_to__gte=day_from, day_from__lte=day_to)
        .exclude(pk=exclude_id)
    )
    day = day_from
    while day <= day_to:
        mine = shift_window(day, candidate)
        for regular in week.get(day.weekday(), ()):
            if overlap_minutes(*mine, *shift_window(day, regular)) > 0:
                return f"It overlaps {regular.name} on {day:%d-%m-%Y}."
        for other in others:
            if other.day_from <= day <= other.day_to:
                theirs = shift_window(
                    day, ShiftSpec(0, other.name, other.start_time, other.end_time, 0)
                )
                if overlap_minutes(*mine, *theirs) > 0:
                    return f"It overlaps the extra shift “{other.name}” on {day:%d-%m-%Y}."
        day += timedelta(days=1)
    return None
