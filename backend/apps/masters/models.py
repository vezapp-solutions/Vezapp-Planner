from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.companies.models import GSTIN_VALIDATOR
from apps.core.audit import audited
from apps.core.models import CompanyScopedModel


@audited()
class Grade(CompanyScopedModel):
    """Metal grade. Only one grade can be in a heat, so grade drives heat pooling."""

    name = models.CharField(max_length=60)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["company", "name"], name="uniq_grade_name")]

    def __str__(self):
        return self.name


class Priority(models.TextChoices):
    A = "A", "A (highest)"
    B = "B", "B"
    C = "C", "C"


@audited()
class Customer(CompanyScopedModel):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    billing_address = models.TextField(blank=True)
    shipping_address = models.TextField(blank=True)
    gstin = models.CharField(max_length=15, blank=True, validators=[GSTIN_VALIDATOR])
    state = models.CharField(max_length=60, blank=True)
    priority = models.CharField(max_length=1, choices=Priority.choices, default=Priority.B)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_customer_code")
        ]

    def __str__(self):
        return f"{self.code} {self.name}"


@audited()
class Part(CompanyScopedModel):
    part_number = models.CharField(max_length=60)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    grade = models.ForeignKey(
        Grade, null=True, blank=True, on_delete=models.PROTECT, related_name="parts"
    )
    material_grade = models.CharField(
        max_length=80, blank=True
    )  # free text as printed on the drawing
    drawing_number = models.CharField(max_length=60, blank=True)
    drawing_revision = models.CharField(max_length=20, blank=True)
    casting_weight_kg = models.DecimalField(max_digits=10, decimal_places=3)
    finished_weight_kg = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    # Metal poured into one mould, runners and risers included.
    pouring_weight_per_mould_kg = models.DecimalField(max_digits=10, decimal_places=3)
    cavities_per_mould = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1)]
    )
    cores_per_mould = models.PositiveSmallIntegerField(default=0)
    pattern_number = models.CharField(max_length=60, blank=True)
    rejection_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    customers = models.ManyToManyField(Customer, through="PartCustomer", related_name="parts")

    class Meta:
        ordering = ["part_number"]
        constraints = [
            models.UniqueConstraint(fields=["company", "part_number"], name="uniq_part_number")
        ]

    def __str__(self):
        return f"{self.part_number} {self.name}"


@audited()
class PartCustomer(CompanyScopedModel):
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name="customer_links")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="part_links")
    is_default = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["part", "customer"], name="uniq_part_customer"),
            models.UniqueConstraint(
                fields=["part"], condition=Q(is_default=True), name="one_default_customer_per_part"
            ),
        ]


class OpKind(models.TextChoices):
    CORE = "core", "Core"
    MOULDING = "moulding", "Moulding"
    MELTING = "melting", "Melting and pouring"
    POST = "post", "Post-casting operation"


class Bucket(models.TextChoices):
    SHIFT = "shift", "Per shift"
    DAY = "day", "Per day"


@audited()
class OperationType(CompanyScopedModel):
    """The operations a company routes parts through. Core to Dispatch are built in; extras start inactive."""

    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=OpKind.choices, default=OpKind.POST)
    default_sequence = models.PositiveSmallIntegerField(default=100)
    default_enabled = models.BooleanField(default=False)
    default_bucket = models.CharField(max_length=5, choices=Bucket.choices, default=Bucket.SHIFT)
    is_active = models.BooleanField(default=True)
    is_builtin = models.BooleanField(default=False)
    # A part may route through this operation several times (machining: OP10, OP20, OP30...).
    multi_step = models.BooleanField(default=False)

    class Meta:
        ordering = ["default_sequence", "name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_operation_code")
        ]

    def __str__(self):
        return self.name


class TimeBasis(models.TextChoices):
    PER_CORE = "per_core", "Minutes per core"
    PER_MOULD = "per_mould", "Minutes per mould"
    PER_HEAT = "per_heat", "Minutes per heat"
    PER_PIECE = "per_piece", "Minutes per piece"
    PER_BATCH = "per_batch", "Minutes per batch"
    FIXED_PER_SHIFT = "fixed_per_shift", "Fixed minutes per shift"
    FIXED_PER_DAY = "fixed_per_day", "Fixed minutes per day"


@audited()
class PartOperation(CompanyScopedModel):
    """One step of a part's route. Kind-specific settings (core scrap, moulds per heat, cooling...) live in extra."""

    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name="operations")
    op_type = models.ForeignKey(
        OperationType, on_delete=models.PROTECT, related_name="part_operations"
    )
    sequence = models.PositiveSmallIntegerField(default=100)
    enabled = models.BooleanField(default=True)
    time_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    time_basis = models.CharField(
        max_length=20, choices=TimeBasis.choices, default=TimeBasis.PER_PIECE
    )
    batch_size = models.PositiveIntegerField(null=True, blank=True)
    capacity_bucket = models.CharField(max_length=5, choices=Bucket.choices, blank=True)
    lag_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    outsourced = models.BooleanField(default=False)
    lead_days = models.PositiveSmallIntegerField(null=True, blank=True)
    # Settings that depend on the kind. For machining: machine_types (resource type ids whose
    # machines may run it), except (machine ids that may not), time_by_type ({type id: minutes}).
    extra = models.JSONField(default=dict, blank=True)
    resources = models.ManyToManyField(
        "resources.Resource", blank=True, related_name="part_operations"
    )
    # Further steps of a multi-step operation: 0 is the original single step, then OP numbers.
    step = models.PositiveSmallIntegerField(default=0)
    label = models.CharField(max_length=80, blank=True)  # for example "Rough milling"
    setup_minutes = models.DecimalField(
        max_digits=8, decimal_places=2, default=0
    )  # per lot, per machine

    class Meta:
        ordering = ["part", "sequence", "step"]
        constraints = [
            models.UniqueConstraint(fields=["part", "op_type", "step"], name="uniq_part_operation")
        ]


# (code, name, kind, sequence, enabled by default, bucket, built in, active)
DEFAULT_OPERATION_TYPES = [
    ("core", "Core", OpKind.CORE, 10, True, Bucket.SHIFT, True, True),
    ("moulding", "Moulding", OpKind.MOULDING, 20, True, Bucket.SHIFT, True, True),
    ("melting", "Melting and pouring", OpKind.MELTING, 30, True, Bucket.SHIFT, True, True),
    ("knockout", "Knockout", OpKind.POST, 40, True, Bucket.SHIFT, True, True),
    ("shot_blasting", "Shot blasting", OpKind.POST, 45, False, Bucket.SHIFT, False, False),
    ("fettling", "Fettling", OpKind.POST, 50, True, Bucket.SHIFT, True, True),
    ("grinding", "Grinding", OpKind.POST, 55, False, Bucket.SHIFT, False, False),
    ("heat_treatment", "Heat treatment", OpKind.POST, 58, False, Bucket.DAY, False, False),
    ("machining", "Machining", OpKind.POST, 60, True, Bucket.SHIFT, True, True),
    ("painting", "Painting", OpKind.POST, 65, False, Bucket.SHIFT, False, False),
    ("inspection", "Inspection", OpKind.POST, 68, False, Bucket.SHIFT, False, False),
    ("packing", "Packing", OpKind.POST, 70, True, Bucket.SHIFT, True, True),
    ("dispatch", "Dispatch", OpKind.POST, 80, True, Bucket.DAY, True, True),
]


MULTI_STEP_CODES = {"machining"}


def ensure_default_operation_types(company):
    for code, name, kind, seq, enabled, bucket, builtin, active in DEFAULT_OPERATION_TYPES:
        OperationType.objects.get_or_create(
            company=company,
            code=code,
            defaults=dict(
                name=name,
                kind=kind,
                default_sequence=seq,
                default_enabled=enabled,
                default_bucket=bucket,
                is_builtin=builtin,
                is_active=active,
                multi_step=code in MULTI_STEP_CODES,
            ),  # fmt: skip
        )
