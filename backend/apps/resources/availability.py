"""Available minutes of a resource per shift, from the company calendar, units, efficiency and downtime."""

from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone

from apps.companies.calendar_data import load_holidays, load_week
from planning.calendar import (
    heats_per_bucket,
    merge_intervals,
    overlap_minutes,
    shift_instances,
    usable_minutes,
)

from .models import Kind, Status


def _local(dt: datetime) -> datetime:
    return timezone.localtime(dt).replace(tzinfo=None)


def resource_availability(resource, start: date, end: date) -> dict:
    company = resource.company
    instances = shift_instances(load_week(company), load_holidays(company, start, end), start, end)
    allowed = set(resource.shifts.values_list("pk", flat=True))
    if allowed:
        instances = [i for i in instances if i.shift.id in allowed]

    window_start = datetime.combine(start, datetime.min.time())
    window_end = datetime.combine(end, datetime.max.time())
    blocked = merge_intervals(
        [
            (_local(d.start_at), _local(d.end_at))
            for d in resource.downtimes.all()
            if _local(d.end_at) > window_start and _local(d.start_at) < window_end
        ]
    )
    running = resource.status == Status.ACTIVE

    rows, per_day = [], {}
    for inst in instances:
        downtime = sum(
            (overlap_minutes(inst.start, inst.end, b0, b1) for b0, b1 in blocked), Decimal(0)
        )
        usable = usable_minutes(inst.minutes, resource.units, resource.efficiency_pct, downtime)
        available = usable.value if running else Decimal(0)
        row = {
            "date": inst.day.isoformat(),
            "shift_id": inst.shift.id,
            "shift_name": inst.shift.name,
            "start": inst.start.isoformat(timespec="minutes"),
            "end": inst.end.isoformat(timespec="minutes"),
            "shift_minutes": inst.minutes,
            "downtime_minutes": float(downtime.quantize(Decimal("0.01"))),
            "available_minutes": float(available.quantize(Decimal("0.01"))),
            "trace": {
                **usable.as_dict(),
                "note": ""
                if running
                else f"resource is {resource.get_status_display().lower()}: no capacity",
            },
        }
        if resource.resource_type.kind == Kind.FURNACE and resource.heat_minutes:
            heats = heats_per_bucket(available, resource.heat_minutes, resource.max_heats_per_shift)
            row["heats"] = heats.as_dict()
        rows.append(row)
        per_day[row["date"]] = round(per_day.get(row["date"], 0) + row["available_minutes"], 2)

    return {
        "resource": resource.pk,
        "status": resource.status,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "shifts": rows,
        "days": [{"date": d, "available_minutes": m} for d, m in sorted(per_day.items())],
        "total_available_minutes": round(sum(per_day.values()), 2),
    }
