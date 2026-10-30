"""Calculate a plan and keep its results: the only place the engine meets the database."""

from datetime import date

from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from planning.engine import run_plan
from planning.model import PlanResult

from .inputs import build_input, data_fingerprint
from .models import Plan, PlanAllocation, PlanLine, PlanLoad, PlanOperation, PlanSlot, PlanStatus

BATCH = 1000
_TZ = timezone.get_default_timezone()  # the engine's clock: Asia/Kolkata


def aware(moment):
    """The engine works in naive local (Asia/Kolkata) time; the database stores aware datetimes."""
    return (
        timezone.make_aware(moment) if moment is not None and timezone.is_naive(moment) else moment
    )


def _requirement_json(req) -> dict:
    if req is None:
        return {}
    return {
        "pieces_to_pour": req.pieces_to_pour,
        "moulds": req.moulds,
        "cores": req.cores,
        "metal_kg": float(req.metal_kg),
        "moulds_per_heat": req.moulds_per_heat,
        "heats": req.heats,
        "minutes": {k: float(v) for k, v in req.minutes.items()},
        "units": {k: float(v) for k, v in req.units.items()},
        "traces": {k: t.as_dict() for k, t in req.traces.items()},
    }


def _save(plan: Plan, inp, lines_by_id, result: PlanResult, resources_by_id) -> None:
    company = plan.company
    plan_lines: dict[int, PlanLine] = {}
    rows = []
    for lr in result.lines:
        sl = lines_by_id[lr.line_id]
        rows.append(
            PlanLine(
                company=company,
                plan=plan,
                schedule_line=sl,
                customer_code=sl.customer.code,
                customer_name=sl.customer.name,
                part_number=sl.part.part_number,
                part_name=sl.part.name,
                qty=sl.dispatch_qty,
                internal_date=sl.internal_dispatch_date,
                priority=sl.customer.priority,
                status=lr.status,
                est_dispatch_date=lr.est_dispatch,
                finish_at=aware(lr.finish_at),
                slack_working_days=lr.slack_working_days,
                holding_op=lr.holding_op or "",
                holding_text=lr.holding_text[:300],
                notes=lr.notes,
                requirement=_requirement_json(lr.requirement),
            )
        )
    for created, lr in zip(
        PlanLine.objects.bulk_create(rows, batch_size=BATCH), result.lines, strict=True
    ):
        plan_lines[lr.line_id] = created

    def dt(moment):
        return (
            connection.ops.adapt_datetimefield_value(aware(moment)) if moment is not None else None
        )

    op_rows = []
    for lr in result.lines:
        pl = plan_lines[lr.line_id]
        for o in lr.ops:
            codes = ", ".join(
                resources_by_id[i].code for i in o.resource_ids if i in resources_by_id
            )
            op_rows.append(
                (
                    company.pk, pl.pk, o.code, o.name, o.kind, o.sequence, float(o.minutes), float(o.units),
                    dt(o.ready_at), dt(o.start_at), dt(o.finish_at), dt(o.latest_start), dt(o.latest_finish),
                    o.delay_days, float(o.wait_hours) if o.wait_hours is not None else None,
                    o.capacity_modelled, o.outsourced, o.complete, codes,
                )
            )  # fmt: skip
    _insert(
        PlanOperation,
        (
            "company_id", "plan_line_id", "code", "name", "kind", "sequence", "minutes", "units",
            "ready_at", "start_at", "finish_at", "latest_start", "latest_finish", "delay_days",
            "wait_hours", "capacity_modelled", "outsourced", "complete", "resource_codes",
        ),
        op_rows,
    )  # fmt: skip
    slot_rows = [
        PlanSlot(
            company_id=company.pk, plan_id=plan.pk, idx=s.idx, slot_date=s.day, shift_id=s.shift_id,
            shift_name=s.shift_name, start=aware(s.start), end=aware(s.end),
        )
        for s in result.slots
    ]  # fmt: skip
    slot_ids = {
        row.idx: row.pk for row in PlanSlot.objects.bulk_create(slot_rows, batch_size=BATCH)
    }

    # The two biggest tables hold only numbers, so they are inserted with plain SQL: building a
    # model object per row costs several times more than the engine itself.
    _insert(
        PlanAllocation,
        ("company_id", "plan_id", "plan_line_id", "op_code", "resource_id", "slot_id", "minutes", "qty", "setup_minutes"),
        (
            (company.pk, plan.pk, plan_lines[a.line_id].pk, a.op_code, a.resource_id,
             slot_ids[a.slot_idx], float(a.minutes), float(a.qty), float(a.setup))
            for a in result.allocations
        ),
    )  # fmt: skip
    _insert(
        PlanLoad,
        ("company_id", "plan_id", "resource_id", "slot_id", "load", "capacity", "required"),
        (
            (company.pk, plan.pk, rid, slot_ids[idx], float(c.load), float(c.capacity), float(c.required))
            for (rid, idx), c in result.loads.items()
        ),
    )  # fmt: skip


def _insert(model, columns: tuple[str, ...], rows) -> None:
    sql = (
        f"INSERT INTO {connection.ops.quote_name(model._meta.db_table)} "
        f"({', '.join(connection.ops.quote_name(c) for c in columns)}) "
        f"VALUES ({', '.join(['%s'] * len(columns))})"
    )
    with connection.cursor() as cursor:
        cursor.executemany(sql, list(rows))


@transaction.atomic
def calculate(plan: Plan, plan_from: date | None = None) -> Plan:
    """(Re)calculate a draft plan from the company's current data."""
    if plan.status != PlanStatus.DRAFT:
        raise ValidationError({"detail": "A confirmed plan is frozen. Start a new plan instead."})
    company = plan.company
    plan_from = plan_from or timezone.localdate()
    inp, lines_by_id = build_input(company, plan_from)
    result = run_plan(inp)

    plan.lines.all().delete()  # cascades to operations and allocations
    plan.slots.all().delete()  # cascades to allocations and loads
    resources_by_id = {r.id: r for r in inp.resources}
    _save(plan, inp, lines_by_id, result, resources_by_id)

    codes = {r.id: r for r in inp.resources}
    bottleneck_days = [
        {
            "date": b.day.isoformat(),
            "resource_id": b.resource_id,
            "resource_code": codes[b.resource_id].code if b.resource_id in codes else "",
            "utilisation": round(float(b.utilisation), 4),
            "load": round(float(b.load), 2),
            "capacity": round(float(b.capacity), 2),
        }
        for b in result.bottlenecks
    ]
    plan.plan_from = plan_from
    plan.calculated_at = timezone.now()
    plan.input_fingerprint = data_fingerprint(company)
    plan.settings_snapshot = {
        "flow_mode": inp.settings.flow_mode,
        "pour_same_shift": inp.settings.pour_same_shift,
        "horizon_days": inp.settings.horizon_days,
        "default_melt_loss_pct": float(inp.settings.default_melt_loss_pct),
    }
    plan.summary = {**result.summary, "bottlenecks": bottleneck_days}
    plan.bottleneck_resource_id = result.bottleneck_overall
    plan.save()

    from apps.insights.service import refresh_quietly  # imported here: it needs this module's peers

    refresh_quietly(company, plan, "plan")
    return plan


def create_plan(company, user) -> Plan:
    last = Plan.objects.filter(company=company).aggregate(m=Max("version"))["m"] or 0
    plan = Plan.objects.create(
        company=company, version=last + 1, plan_from=timezone.localdate(), created_by=user
    )
    return calculate(plan)


def stale_reasons(plan: Plan) -> list[str]:
    reasons = []
    if plan.status == PlanStatus.CONFIRMED:
        return reasons  # a confirmed plan is a baseline: it is not meant to follow later changes
    if plan.input_fingerprint != data_fingerprint(plan.company):
        reasons.append("Masters or the schedule have changed since this plan was calculated.")
    if plan.plan_from < timezone.localdate():
        reasons.append("This plan was calculated for an earlier day.")
    return reasons
