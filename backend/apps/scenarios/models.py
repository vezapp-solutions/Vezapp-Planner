from django.conf import settings
from django.db import models

from apps.core.audit import audited
from apps.core.models import CompanyScopedModel


class ScenarioStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    APPLIED = "applied", "Applied"


class ChangeKind(models.TextChoices):
    BLOCK_RESOURCE = "block_resource", "Block a resource"
    CHANGE_QTY = "change_qty", "Change a quantity"
    CHANGE_DATE = "change_date", "Change a date"
    EXTRA_SHIFT = "extra_shift", "Add a shift"
    OVERTIME = "overtime", "Add overtime"


@audited()
class Scenario(CompanyScopedModel):
    """A named set of what-if changes. Running it never touches real data; applying it does."""

    name = models.CharField(max_length=120)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=ScenarioStatus.choices, default=ScenarioStatus.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    last_run_at = models.DateTimeField(null=True, blank=True)
    # What the stored result was calculated from: the company's data and the list of changes.
    run_fingerprint = models.CharField(max_length=64, blank=True)
    run_signature = models.CharField(max_length=64, blank=True)
    result = models.JSONField(default=dict, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.name


class ScenarioChange(CompanyScopedModel):
    """One change in a scenario. `params` are validated per kind when the change is added."""

    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="changes")
    kind = models.CharField(max_length=20, choices=ChangeKind.choices)
    params = models.JSONField(default=dict)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.kind} in {self.scenario}"
