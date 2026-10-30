from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.audit import audited
from apps.core.models import CompanyScopedModel


class Kind(models.TextChoices):
    CORE_MACHINE = "core_machine", "Core Machine"
    MOULDING_LINE = "moulding_line", "Moulding Line"
    FURNACE = "furnace", "Furnace"
    WORK_CENTRE = "work_centre", "Work Centre"


@audited()
class ResourceType(CompanyScopedModel):
    """The four seeded types decide which rated fields apply; a Company Admin may add more of a kind."""

    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_resource_type")
        ]

    def __str__(self):
        return self.name


class Status(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    MAINTENANCE = "maintenance", "Under maintenance"


@audited()
class Resource(CompanyScopedModel):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=120)
    resource_type = models.ForeignKey(
        ResourceType, on_delete=models.PROTECT, related_name="resources"
    )
    plant = models.ForeignKey(
        "companies.Plant", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    units = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    efficiency_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )
    remarks = models.TextField(blank=True)

    # Rated capacity. Which fields apply depends on the type's kind (see planning.checks).
    rate_per_hour = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )  # cores, moulds or pieces / h
    cycle_seconds = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )  # core: seconds per shot
    cores_per_shot = models.PositiveSmallIntegerField(null=True, blank=True)
    heat_kg = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True
    )  # furnace: liquid metal per heat
    heat_minutes = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True
    )  # furnace: tap to tap
    max_heats_per_shift = models.PositiveSmallIntegerField(null=True, blank=True)

    # Empty means the resource works every company shift.
    shifts = models.ManyToManyField("companies.Shift", blank=True, related_name="resources")

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_resource_code")
        ]

    def __str__(self):
        return f"{self.code} {self.name}"

    @property
    def kind(self):
        return self.resource_type.kind


@audited()
class Downtime(CompanyScopedModel):
    """A blocked period (maintenance, breakdown, lining change). It removes capacity."""

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="downtimes")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["start_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")), name="downtime_end_after_start"
            )
        ]


class AdjustmentKind(models.TextChoices):
    EXTRA_SHIFT = "extra_shift", "Extra shift"
    OVERTIME = "overtime", "Overtime"


@audited()
class CapacityAdjustment(CompanyScopedModel):
    """A one-off change to working time that every later plan honours: an extra shift on some
    days, or overtime in the existing shifts. Created by hand or by applying a what-if."""

    kind = models.CharField(max_length=12, choices=AdjustmentKind.choices)
    day_from = models.DateField()
    day_to = models.DateField()
    # extra shift
    name = models.CharField(max_length=60, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    break_minutes = models.PositiveSmallIntegerField(default=0)
    # overtime: extra clock minutes in each shift of the range (one shift, or all when none is set)
    shift = models.ForeignKey(
        "companies.Shift", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    # blank means every resource
    resources = models.ManyToManyField(Resource, blank=True, related_name="capacity_adjustments")
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["day_from", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(day_to__gte=models.F("day_from")), name="adjustment_days_ordered"
            )
        ]

    def __str__(self):
        what = self.name or "Overtime"
        return f"{what} {self.day_from:%d-%m-%Y}"


DEFAULT_RESOURCE_TYPES = [
    ("Core Machine", Kind.CORE_MACHINE),
    ("Moulding Line", Kind.MOULDING_LINE),
    ("Furnace", Kind.FURNACE),
    ("Work Centre", Kind.WORK_CENTRE),
]


def ensure_default_resource_types(company):
    for name, kind in DEFAULT_RESOURCE_TYPES:
        ResourceType.objects.get_or_create(
            company=company, name=name, defaults={"kind": kind, "is_default": True}
        )
