"""Turns a company's masters and schedule into the planning engine's PlanInput, and fingerprints them."""

import hashlib
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Max
from django.utils import timezone

from apps.companies.calendar_data import load_holidays, load_week
from apps.companies.models import CompanySettings, Holiday, Shift, WeekdayShift
from apps.masters.machines import (
    allowed_ids,
    code_of,
    engine_extra,
    machines_by_type,
    name_of,
    times_by_type,
)
from apps.masters.models import Customer, OperationType, Part, PartOperation
from apps.resources.models import AdjustmentKind, CapacityAdjustment, Downtime, Resource, Status
from apps.scheduler.models import LineStatus, ScheduleLine
from planning.calendar import ShiftSpec
from planning.model import (
    ExtraShift,
    LineInput,
    OpSpec,
    Overtime,
    PartSpec,
    PlanInput,
    PlanSettings,
    ResourceSpec,
)

FINGERPRINT_MODELS = (
    ScheduleLine,
    Part,
    PartOperation,
    OperationType,
    Customer,
    Resource,
    Downtime,
    Shift,
    WeekdayShift,
    Holiday,
    CompanySettings,
    CapacityAdjustment,
)

# Ids of one-off shifts, kept clear of real shift ids so a slot's shift can be told apart.
EXTRA_SHIFT_ID_BASE = 1_000_000


def data_fingerprint(company) -> str:
    """Changes whenever anything a plan depends on is added, edited or deleted."""
    pieces = []
    for model in FINGERPRINT_MODELS:
        qs = (
            model.objects.filter(company=company)
            if hasattr(model, "company")
            else model.objects.all()
        )
        agg = qs.aggregate(n=Count("pk"), last=Max("updated_at"))
        pieces.append(
            f"{model.__name__}:{agg['n']}:{agg['last'].isoformat() if agg['last'] else ''}"
        )
    return hashlib.sha256("|".join(pieces).encode()).hexdigest()


def _local(dt):
    return timezone.localtime(dt).replace(tzinfo=None)


def _dec(value) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def plan_settings(company, plan_from: date) -> PlanSettings:
    s, _ = CompanySettings.objects.get_or_create(company=company)
    return PlanSettings(
        plan_from=plan_from,
        horizon_days=s.horizon_days,
        flow_mode=s.flow_mode,
        pour_same_shift=s.pour_same_shift,
        default_melt_loss_pct=Decimal(str(s.melt_loss_default_pct)),
    )


def build_input(company, plan_from: date) -> tuple[PlanInput, dict[int, ScheduleLine]]:
    """Everything the engine needs. Returns the input and the schedule lines by id."""
    settings = plan_settings(company, plan_from)

    lines_qs = (
        ScheduleLine.objects.for_company(company)
        .filter(status__in=[LineStatus.PLANNED, LineStatus.IN_PROGRESS])
        .select_related("customer", "part")
    )
    lines = list(lines_qs)
    part_ids = {ln.part_id for ln in lines}

    seq_of = {o.code: o.default_sequence for o in OperationType.objects.for_company(company)}
    rejection_seq = seq_of.get(CompanySettings.objects.get(company=company).rejection_booked_at, 50)
    by_type = machines_by_type(company)

    parts: dict[int, PartSpec] = {}
    for part in Part.objects.for_company(company).filter(pk__in=part_ids).select_related("grade"):
        ops = []
        route = (
            part.operations.filter(enabled=True)
            .select_related("op_type")
            .prefetch_related("resources")
            .order_by("sequence", "step", "id")
        )
        for o in route:
            ops.append(
                OpSpec(
                    code=code_of(o),
                    name=name_of(o),
                    kind=o.op_type.kind,
                    sequence=o.sequence,
                    time_value=_dec(o.time_value),
                    time_basis=o.time_basis,
                    batch_size=o.batch_size,
                    bucket=o.capacity_bucket or o.op_type.default_bucket,
                    lag_hours=Decimal(str(o.lag_hours)),
                    outsourced=o.outsourced,
                    lead_days=o.lead_days,
                    resource_ids=tuple(allowed_ids(o, by_type)),
                    extra=engine_extra(o),
                    step=o.step,
                    setup_minutes=Decimal(str(o.setup_minutes or 0)),
                    time_by_type=times_by_type(o),
                )
            )
        parts[part.pk] = PartSpec(
            id=part.pk,
            part_number=part.part_number,
            grade_id=part.grade_id,
            grade_name=part.grade.name if part.grade else "",
            casting_weight_kg=Decimal(str(part.casting_weight_kg)),
            pouring_weight_per_mould_kg=Decimal(str(part.pouring_weight_per_mould_kg)),
            cavities_per_mould=part.cavities_per_mould,
            cores_per_mould=part.cores_per_mould,
            rejection_pct=Decimal(str(part.rejection_pct)),
            ops=tuple(ops),
            rejection_seq=rejection_seq,
        )

    resources = []
    for r in (
        Resource.objects.for_company(company)
        .select_related("resource_type")
        .prefetch_related("shifts", "downtimes")
    ):
        resources.append(
            ResourceSpec(
                id=r.pk,
                code=r.code,
                type_id=r.resource_type_id,
                kind=r.resource_type.kind,
                units=r.units,
                efficiency_pct=Decimal(str(r.efficiency_pct)),
                active=r.status == Status.ACTIVE,
                shift_ids=frozenset(s.pk for s in r.shifts.all()),
                downtimes=tuple((_local(d.start_at), _local(d.end_at)) for d in r.downtimes.all()),
                rate_per_hour=_dec(r.rate_per_hour),
                cycle_seconds=_dec(r.cycle_seconds),
                cores_per_shot=r.cores_per_shot,
                heat_kg=_dec(r.heat_kg),
                heat_minutes=_dec(r.heat_minutes),
                max_heats_per_shift=r.max_heats_per_shift,
            )
        )

    line_inputs = [
        LineInput(
            id=ln.pk,
            part_id=ln.part_id,
            qty=ln.dispatch_qty,
            internal_date=ln.internal_dispatch_date,
            customer_id=ln.customer_id,
            priority=ln.customer.priority,
            entry_order=ln.pk,
        )
        for ln in lines
    ]
    horizon_end = plan_from + timedelta(days=settings.max_window_days)
    extra_shifts, overtime = load_adjustments(company, plan_from)
    inp = PlanInput(
        settings=settings,
        week=load_week(company),
        holidays=load_holidays(company, plan_from, horizon_end),
        resources=resources,
        parts=parts,
        lines=line_inputs,
        extra_shifts=extra_shifts,
        overtime=overtime,
    )
    return inp, {ln.pk: ln for ln in lines}


def load_adjustments(
    company, plan_from: date
) -> tuple[tuple[ExtraShift, ...], tuple[Overtime, ...]]:
    """Extra shifts and overtime recorded in the masters, from the plan start onwards."""
    extras: list[ExtraShift] = []
    overtime: list[Overtime] = []
    rows = (
        CapacityAdjustment.objects.for_company(company)
        .filter(day_to__gte=plan_from)
        .prefetch_related("resources")
    )
    for adj in rows:
        named = frozenset(r.pk for r in adj.resources.all()) or None
        if adj.kind == AdjustmentKind.EXTRA_SHIFT:
            shift = ShiftSpec(
                EXTRA_SHIFT_ID_BASE + adj.pk,
                adj.name or "Extra shift",
                adj.start_time,
                adj.end_time,
                adj.break_minutes,
            )
            extras.append(ExtraShift(adj.day_from, adj.day_to, shift, named))
        elif adj.kind == AdjustmentKind.OVERTIME and adj.minutes:
            overtime.append(Overtime(adj.day_from, adj.day_to, adj.minutes, adj.shift_id, named))
    return tuple(extras), tuple(overtime)
