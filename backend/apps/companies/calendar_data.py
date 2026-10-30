"""Loads a company's working calendar from the database into the pure-Python engine's types."""

from collections import defaultdict

from planning.calendar import ShiftSpec, shift_minutes

from .models import Holiday, Shift, WeekdayShift


def to_spec(shift: Shift) -> ShiftSpec:
    return ShiftSpec(shift.pk, shift.name, shift.start_time, shift.end_time, shift.break_minutes)


def load_week(company) -> dict[int, list[ShiftSpec]]:
    week: dict[int, list[ShiftSpec]] = defaultdict(list)
    rows = WeekdayShift.objects.for_company(company).select_related("shift")
    for row in rows:
        week[row.weekday].append(to_spec(row.shift))
    return dict(week)


def load_holidays(company, start, end) -> dict:
    """date -> None for a full holiday, or frozenset of shift ids that are off."""
    out: dict = {}
    qs = (
        Holiday.objects.for_company(company)
        .filter(date__range=(start, end))
        .prefetch_related("shifts_off")
    )
    for holiday in qs:
        out[holiday.date] = (
            None if holiday.full_day else frozenset(s.pk for s in holiday.shifts_off.all())
        )
    return out


def week_summary(company) -> dict:
    shifts = list(Shift.objects.for_company(company))
    by_day: dict[int, list[int]] = defaultdict(list)
    for row in WeekdayShift.objects.for_company(company):
        by_day[row.weekday].append(row.shift_id)
    net = {s.pk: shift_minutes(s.start_time, s.end_time, s.break_minutes) for s in shifts}
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    days = [
        {
            "weekday": d,
            "name": names[d],
            "shift_ids": by_day.get(d, []),
            "minutes": sum(net[i] for i in by_day.get(d, [])),
        }
        for d in range(7)
    ]
    return {"days": days, "week_minutes": sum(d["minutes"] for d in days)}
