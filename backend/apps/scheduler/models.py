from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.audit import audited
from apps.core.models import CompanyScopedModel


class LineStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    IN_PROGRESS = "in_progress", "In progress"
    DISPATCHED = "dispatched", "Dispatched"
    CANCELLED = "cancelled", "Cancelled"


class UploadMode(models.TextChoices):
    INSERT = "insert", "Insert new rows only"
    UPSERT = "upsert", "Insert new and update matching rows"


class UploadBatch(CompanyScopedModel):
    """One committed Excel or CSV upload, kept as history."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    username = models.CharField(max_length=150, blank=True)
    file_name = models.CharField(max_length=255)
    mode = models.CharField(max_length=10, choices=UploadMode.choices)
    skipped_errors = models.BooleanField(default=False)
    rows_total = models.PositiveIntegerField(default=0)
    rows_inserted = models.PositiveIntegerField(default=0)
    rows_updated = models.PositiveIntegerField(default=0)
    rows_unchanged = models.PositiveIntegerField(default=0)
    rows_skipped = models.PositiveIntegerField(default=0)  # duplicates left alone
    rows_error = models.PositiveIntegerField(default=0)  # rows not loaded because of errors
    rows_warning = models.PositiveIntegerField(default=0)
    # Rows with errors or warnings, kept so the error report can be downloaded later.
    report = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.file_name} ({self.created_at:%d-%m-%Y %H:%M})"


@audited()
class ScheduleLine(CompanyScopedModel):
    """One dispatch requirement: this customer wants this many of this part by this date."""

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="+")
    part = models.ForeignKey("masters.Part", on_delete=models.PROTECT, related_name="+")
    dispatch_qty = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    internal_dispatch_date = models.DateField()
    actual_dispatch_date = models.DateField(null=True, blank=True)
    actual_dispatched_qty = models.PositiveIntegerField(null=True, blank=True)
    remarks = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=12, choices=LineStatus.choices, default=LineStatus.PLANNED)
    upload_batch = models.ForeignKey(
        UploadBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name="lines"
    )

    class Meta:
        # Entry order (id) is the last tie-break in scheduling, after date and customer priority.
        ordering = ["internal_dispatch_date", "id"]
        indexes = [models.Index(fields=["company", "internal_dispatch_date"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(dispatch_qty__gte=1), name="line_qty_positive"
            )
        ]

    def __str__(self):
        return f"{self.customer.code} {self.part.part_number} × {self.dispatch_qty}"

    @property
    def month(self) -> str:
        return self.internal_dispatch_date.strftime("%Y-%m")
