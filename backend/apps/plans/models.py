from django.conf import settings
from django.db import models

from apps.core.audit import audited
from apps.core.models import CompanyQuerySet, CompanyScopedModel


class PlanStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    CONFIRMED = "confirmed", "Confirmed"


class LineStatus(models.TextChoices):
    ON_TRACK = "on_track", "On track"
    TIGHT = "tight", "Tight"
    AT_RISK = "at_risk", "At risk"
    UNSCHEDULED = "unscheduled", "Not scheduled"


class PlanRow(models.Model):
    """Base of the bulky result tables: owned by a company, with no timestamp columns.

    A plan writes thousands of these in one go, so each row carries only what it needs.
    """

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="+")

    objects = CompanyQuerySet.as_manager()

    class Meta:
        abstract = True


@audited()
class Plan(CompanyScopedModel):
    """One calculated plan. A draft can be recalculated; a confirmed plan is a frozen baseline."""

    version = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=PlanStatus.choices, default=PlanStatus.DRAFT)
    plan_from = models.DateField()
    calculated_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    input_fingerprint = models.CharField(max_length=64, blank=True)
    settings_snapshot = models.JSONField(default=dict, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    bottleneck_resource = models.ForeignKey(
        "resources.Resource", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["company", "version"], name="uniq_plan_version")
        ]

    def __str__(self):
        return f"Plan v{self.version}"


class PlanSlot(PlanRow):
    """One shift of one working day in a plan's timeline. Allocations and loads point here."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="slots")
    idx = models.PositiveIntegerField()
    slot_date = models.DateField()
    shift_id = models.PositiveIntegerField()
    shift_name = models.CharField(max_length=60)
    start = models.DateTimeField()
    end = models.DateTimeField()

    def __str__(self):
        return f"{self.slot_date} {self.shift_name}"

    class Meta:
        ordering = ["idx"]
        indexes = [models.Index(fields=["plan", "slot_date"])]


class PlanLine(PlanRow):
    """The result for one schedule line, with a snapshot of what was planned."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="lines")
    schedule_line = models.ForeignKey(
        "scheduler.ScheduleLine", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    customer_code = models.CharField(max_length=30)
    customer_name = models.CharField(max_length=200)
    part_number = models.CharField(max_length=60)
    part_name = models.CharField(max_length=200)
    qty = models.PositiveIntegerField()
    internal_date = models.DateField()
    priority = models.CharField(max_length=1, default="B")
    status = models.CharField(max_length=12, choices=LineStatus.choices)
    est_dispatch_date = models.DateField(null=True, blank=True)
    finish_at = models.DateTimeField(null=True, blank=True)
    slack_working_days = models.IntegerField(null=True, blank=True)
    holding_op = models.CharField(max_length=40, blank=True)
    holding_text = models.CharField(max_length=300, blank=True)
    notes = models.JSONField(default=list, blank=True)
    requirement = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.part_number} for {self.customer_code}"

    class Meta:
        ordering = ["internal_date", "id"]
        indexes = [models.Index(fields=["plan", "status"])]


class PlanOperation(PlanRow):
    plan_line = models.ForeignKey(PlanLine, on_delete=models.CASCADE, related_name="operations")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10)
    sequence = models.PositiveSmallIntegerField()
    minutes = models.FloatField(default=0)
    units = models.FloatField(default=0)
    ready_at = models.DateTimeField(null=True, blank=True)
    start_at = models.DateTimeField(null=True, blank=True)
    finish_at = models.DateTimeField(null=True, blank=True)
    latest_start = models.DateTimeField(null=True, blank=True)
    latest_finish = models.DateTimeField(null=True, blank=True)
    delay_days = models.IntegerField(null=True, blank=True)
    wait_hours = models.FloatField(null=True, blank=True)
    capacity_modelled = models.BooleanField(default=True)
    outsourced = models.BooleanField(default=False)
    complete = models.BooleanField(default=True)
    resource_codes = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["plan_line", "sequence"]


class PlanAllocation(PlanRow):
    """Minutes of one operation of one line on one resource in one shift."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="allocations")
    plan_line = models.ForeignKey(PlanLine, on_delete=models.CASCADE, related_name="allocations")
    op_code = models.CharField(max_length=40)
    resource = models.ForeignKey(
        "resources.Resource", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )  # empty for operations whose capacity is not modelled
    slot = models.ForeignKey(PlanSlot, on_delete=models.CASCADE, related_name="allocations")
    minutes = models.FloatField()  # all machine minutes, setup included
    qty = models.FloatField()
    setup_minutes = models.FloatField(default=0)  # the part of `minutes` spent on machine setup

    def __str__(self):
        return f"{self.op_code} {self.minutes:.0f} min"

    class Meta:
        indexes = [models.Index(fields=["plan", "slot"])]


class PlanLoad(PlanRow):
    """Load, capacity and required load of one resource in one shift (only shifts that matter)."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="loads")
    resource = models.ForeignKey(
        "resources.Resource", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    slot = models.ForeignKey(PlanSlot, on_delete=models.CASCADE, related_name="loads")
    load = models.FloatField(default=0)
    capacity = models.FloatField(default=0)
    required = models.FloatField(default=0)

    def __str__(self):
        return f"load {self.load:.0f} of {self.capacity:.0f} min"

    class Meta:
        indexes = [models.Index(fields=["plan", "slot"])]
