"""A few deliberate gaps in Foundry A's data (synthetic), so Data health has something to show."""

from datetime import date, timedelta

from apps.masters.models import Customer, Part, PartCustomer
from apps.resources.models import Resource, ResourceType
from apps.scheduler.models import ScheduleLine


def ensure_demo_gaps(company, today: date | None = None):
    """A part with no route and a line for it already past its date, and a resource with a doubtful
    efficiency. Safe to re-run."""
    today = today or date.today()
    customer = Customer.objects.filter(company=company, code="C-101").first()
    if customer is None:
        return

    part, created = Part.objects.get_or_create(
        company=company,
        part_number="SPR-900",
        defaults=dict(
            name="Spacer plate (route not set up yet)", casting_weight_kg=3,
            pouring_weight_per_mould_kg=7, cavities_per_mould=2, cores_per_mould=0,
        ),
    )  # fmt: skip
    if created:
        PartCustomer.objects.create(company=company, part=part, customer=customer, is_default=True)
        ScheduleLine.objects.create(
            company=company, customer=customer, part=part, dispatch_qty=60,
            internal_dispatch_date=today - timedelta(days=12),
            remarks="Demo gap: past its date with no actual dispatch",
        )  # fmt: skip

    kind = ResourceType.objects.filter(company=company, kind="work_centre", is_default=True).first()
    if kind is not None:
        Resource.objects.get_or_create(
            company=company, code="KO2",
            defaults={"name": "Old knockout (efficiency to check)", "resource_type": kind, "efficiency_pct": 40},
        )  # fmt: skip
