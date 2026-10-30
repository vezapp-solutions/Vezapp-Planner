"""Example what-if scenarios for the demo foundries (synthetic). Drafts that have not been run."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apps.accounts.models import User
from apps.accounts.roles import Role
from apps.resources.models import Resource
from apps.scenarios.models import ChangeKind, Scenario, ScenarioChange

IST = ZoneInfo("Asia/Kolkata")


def _next_weekday(start: date, weekday: int) -> date:
    return start + timedelta(days=(weekday - start.weekday()) % 7)


def _scenario(company, name, notes, changes, created_by):
    scenario, created = Scenario.objects.get_or_create(
        company=company, name=name, defaults={"notes": notes, "created_by": created_by}
    )
    if created:
        for order, (kind, params) in enumerate(changes, start=1):
            ScenarioChange.objects.create(
                company=company, scenario=scenario, kind=kind, params=params, order=order
            )


def ensure_demo_scenarios(company, today: date | None = None):
    """Two drafts per foundry: lose furnace F1 for the next working day, and open the plant on a Sunday."""
    today = today or date.today()
    planner = User.objects.filter(company=company, role=Role.PLANNER).first()
    furnace = Resource.objects.filter(company=company, code="F1").first()
    if furnace is None:
        return

    day = today + timedelta(days=1)
    if day.weekday() == 6:  # Sunday is the weekly off, so a block there would change nothing
        day += timedelta(days=1)
    start = datetime.combine(day, datetime.min.time(), IST)
    _scenario(
        company,
        "F1 down for a day",
        "Lining change on the main furnace the day after today. Which lines move?",
        [
            (
                ChangeKind.BLOCK_RESOURCE,
                {
                    "resource": furnace.pk,
                    "start": start.isoformat(),
                    "end": (start + timedelta(hours=23, minutes=59)).isoformat(),
                    "reason": "Lining change",
                },
            )
        ],
        planner,
    )

    sunday = _next_weekday(today + timedelta(days=1), 6)
    _scenario(
        company,
        "Sunday extra shift",
        "Open the plant for one Sunday to pull lines forward.",
        [
            (
                ChangeKind.EXTRA_SHIFT,
                {
                    "day_from": sunday.isoformat(),
                    "day_to": sunday.isoformat(),
                    "name": "Sunday day shift",
                    "start_time": "06:00:00",
                    "end_time": "14:00:00",
                    "break_minutes": 30,
                    "resources": [],
                },
            )
        ],
        planner,
    )
