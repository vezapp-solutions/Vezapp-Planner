from django.db import models

from apps.core.models import CompanyScopedModel


class RunTrigger(models.TextChoices):
    PLAN = "plan", "Plan calculated"
    MANUAL = "manual", "Refreshed by hand"
    ACTUALS = "actuals", "Actual dispatch dates uploaded"


class InsightRun(CompanyScopedModel):
    """One refresh of a company's insight cards. Kept so cards can show a trend."""

    plan = models.ForeignKey(
        "plans.Plan", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    trigger = models.CharField(max_length=10, choices=RunTrigger.choices)
    counts = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["company", "-id"])]

    def __str__(self):
        return f"Insight run {self.pk} ({self.created_at:%d-%m-%Y %H:%M})"


class Insight(CompanyScopedModel):
    """One card. Derived data, rewritten on every run, so it is not audited."""

    run = models.ForeignKey(InsightRun, on_delete=models.CASCADE, related_name="cards")
    key = models.CharField(max_length=120)
    type = models.CharField(max_length=30)
    severity = models.CharField(max_length=10)
    title = models.CharField(max_length=200)
    message = models.TextField()
    numbers = models.JSONField(default=dict, blank=True)
    entities = models.JSONField(default=dict, blank=True)
    action = models.TextField(blank=True)
    why = models.JSONField(default=list, blank=True)
    impact = models.FloatField(default=0)
    rank = models.FloatField(default=0)
    trend = models.CharField(max_length=8, default="new")

    class Meta:
        ordering = ["-rank", "key"]
        indexes = [models.Index(fields=["run", "type"])]

    def __str__(self):
        return self.title
