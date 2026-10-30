"""Synthetic dispatch schedule for the demo foundries, placed relative to today so it is never stale."""

import random
from datetime import date, timedelta

from apps.masters.models import Customer, Part
from apps.scheduler.models import LineStatus, ScheduleLine


def _month_start(day: date, offset: int) -> date:
    index = day.year * 12 + day.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def build_demo_schedule(company, today: date | None = None):
    """Last month (shipped, some late), this month and next month. Safe to re-run."""
    today = today or date.today()
    if ScheduleLine.objects.filter(company=company).exists():
        return
    rng = random.Random(company.pk)
    customers = {c.pk: c for c in Customer.objects.filter(company=company)}
    pairs = [
        (link.customer_id, part)
        for part in Part.objects.filter(company=company, is_active=True)
        for link in part.customer_links.all()
    ]
    if not pairs:
        return

    for offset, count in ((-1, 14), (0, 16), (1, 12)):
        first = _month_start(today, offset)
        for _ in range(count):
            customer_id, part = rng.choice(pairs)
            day = first + timedelta(days=rng.randrange(0, 27))
            qty = rng.choice([40, 60, 80, 100, 120, 150, 200])
            line = ScheduleLine(
                company=company,
                customer=customers[customer_id],
                part=part,
                dispatch_qty=qty,
                internal_dispatch_date=day,
            )
            if day < today and rng.random() < 0.85:
                late = rng.choice([0, 0, 0, 1, 2, 4, 7])  # days after the internal date
                shipped = min(day + timedelta(days=late), today)
                line.actual_dispatch_date = shipped
                line.actual_dispatched_qty = qty if rng.random() < 0.9 else int(qty * 0.8)
                line.status = LineStatus.DISPATCHED
            elif day <= today + timedelta(days=3):
                line.status = LineStatus.IN_PROGRESS
            line.save()
