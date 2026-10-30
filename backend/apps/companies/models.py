from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from apps.core.audit import audited
from apps.core.models import CompanyScopedModel, TimeStampedModel
from planning.calendar import crosses_midnight, shift_minutes

GSTIN_VALIDATOR = RegexValidator(
    regex=r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
    message="Enter a valid 15-character GSTIN.",
)


@audited()
class Company(TimeStampedModel):
    """A client foundry. The tenant boundary of the whole product."""

    name = models.CharField(max_length=200, unique=True)
    address = models.TextField(blank=True)
    gstin = models.CharField(max_length=15, blank=True, validators=[GSTIN_VALIDATOR])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name


class Bucket(models.TextChoices):
    SHIFT = "shift", "Shift"
    DAY = "day", "Day"


@audited()
class CompanySettings(TimeStampedModel):
    """Planning settings. One row per company, created on first use."""

    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="settings")
    horizon_days = models.PositiveSmallIntegerField(
        default=30, validators=[MinValueValidator(1), MaxValueValidator(366)]
    )
    default_bucket = models.CharField(max_length=5, choices=Bucket.choices, default=Bucket.SHIFT)
    # Operation code after which rejection is booked: quantities before it include the rejection allowance.
    rejection_booked_at = models.CharField(max_length=40, default="fettling")
    # Kept for compatibility; the plan counts heats per part and does not pool them across parts.
    pooling_enabled = models.BooleanField(default=True)
    # progressive: an operation works on pieces as the previous one releases them. whole_lot: it
    # waits for the whole lot.
    flow_mode = models.CharField(
        max_length=12,
        choices=[("progressive", "Pieces flow on"), ("whole_lot", "Whole lot at a time")],
        default="progressive",
    )
    pour_same_shift = models.BooleanField(default=True)
    melt_loss_default_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(Decimal("99.99"))],
    )

    class Meta:
        verbose_name_plural = "company settings"

    def __str__(self):
        return f"Settings of {self.company}"


@audited()
class Shift(CompanyScopedModel):
    """A named working shift. A shift crossing midnight belongs to the day it starts."""

    name = models.CharField(max_length=60)
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_minutes = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["start_time", "name"]
        constraints = [models.UniqueConstraint(fields=["company", "name"], name="uniq_shift_name")]

    def __str__(self):
        return self.name

    @property
    def crosses_midnight(self):
        return crosses_midnight(self.start_time, self.end_time)

    @property
    def net_minutes(self):
        return shift_minutes(self.start_time, self.end_time, self.break_minutes)


@audited()
class WeekdayShift(CompanyScopedModel):
    """Shift s runs on weekday d (0 = Monday). A weekday with no rows is a weekly off."""

    weekday = models.PositiveSmallIntegerField(validators=[MaxValueValidator(6)])
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="weekdays")

    class Meta:
        ordering = ["weekday", "shift__start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "weekday", "shift"], name="uniq_weekday_shift"
            )
        ]


@audited()
class Holiday(CompanyScopedModel):
    """A full holiday, or a day where only some shifts are off."""

    date = models.DateField()
    name = models.CharField(max_length=120)
    full_day = models.BooleanField(default=True)
    shifts_off = models.ManyToManyField(Shift, blank=True, related_name="holidays")

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(fields=["company", "date"], name="uniq_holiday_date")
        ]

    def __str__(self):
        return f"{self.date} {self.name}"


@audited()
class Plant(CompanyScopedModel):
    name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_plant_name_per_company")
        ]

    def __str__(self):
        return self.name
