from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CompanyQuerySet(models.QuerySet):
    def for_company(self, company):
        """Rows of one company. No company means no rows, never all rows."""
        if company is None:
            return self.none()
        return self.filter(company=company)


class CompanyScopedModel(TimeStampedModel):
    """Base of every business record: it belongs to exactly one Company (tenant)."""

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="+")

    objects = CompanyQuerySet.as_manager()

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """Who changed what, when, with the values before and after. Rows are never edited."""

    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"

    company = models.ForeignKey(
        "companies.Company", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=10, choices=Action.choices)
    model_label = models.CharField(max_length=100)
    object_pk = models.CharField(max_length=64)
    object_repr = models.CharField(max_length=200, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["model_label", "object_pk"]),
        ]

    def __str__(self):
        return f"{self.action} {self.model_label}#{self.object_pk} by {self.username or '-'}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("Audit log rows are append-only.")
        super().save(*args, **kwargs)
