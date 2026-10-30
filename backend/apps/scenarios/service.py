"""Run a what-if (baseline against changed plan) and apply it to the real data."""

import hashlib
import json
from datetime import date, datetime, time

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.plans import service as plan_service
from apps.plans.inputs import EXTRA_SHIFT_ID_BASE, build_input, data_fingerprint
from apps.plans.models import Plan, PlanStatus
from apps.resources.models import AdjustmentKind, CapacityAdjustment, Downtime, Resource
from apps.scheduler.models import ScheduleLine
from planning.calendar import ShiftSpec
from planning.engine import run_plan
from planning.model import ExtraShift, Overtime, PlanInput
from planning.whatif import BlockResource, ChangeDate, ChangeQty, apply_changes, diff_results

from .models import ChangeKind, Scenario, ScenarioStatus

# Ids of one-off shifts invented by a scenario, apart from the real ones in the masters.
HYPOTHETICAL_SHIFT_BASE = EXTRA_SHIFT_ID_BASE * 2


def change_signature(scenario: Scenario) -> str:
    rows = [(c.kind, c.params) for c in scenario.changes.all().order_by("order", "id")]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


def result_state(scenario: Scenario) -> str:
    """never_run, fresh, changes_edited (the list of changes moved on) or data_changed."""
    if scenario.last_run_at is None:
        return "never_run"
    if scenario.run_signature != change_signature(scenario):
        return "changes_edited"
    if scenario.run_fingerprint != data_fingerprint(scenario.company):
        return "data_changed"
    return "fresh"


def _naive_local(text: str) -> datetime:
    return timezone.localtime(datetime.fromisoformat(text)).replace(tzinfo=None)


def _engine_changes(scenario: Scenario) -> list:
    out = []
    for n, c in enumerate(scenario.changes.all().order_by("order", "id")):
        p = c.params
        if c.kind == ChangeKind.BLOCK_RESOURCE:
            out.append(
                BlockResource(p["resource"], _naive_local(p["start"]), _naive_local(p["end"]))
            )
        elif c.kind == ChangeKind.CHANGE_QTY:
            out.append(ChangeQty(p["line"], p["qty"]))
        elif c.kind == ChangeKind.CHANGE_DATE:
            out.append(ChangeDate(p["line"], date.fromisoformat(p["date"])))
        elif c.kind == ChangeKind.EXTRA_SHIFT:
            shift = ShiftSpec(
                HYPOTHETICAL_SHIFT_BASE + n, p["name"], time.fromisoformat(p["start_time"]),
                time.fromisoformat(p["end_time"]), p.get("break_minutes", 0),
            )  # fmt: skip
            out.append(
                ExtraShift(
                    date.fromisoformat(p["day_from"]),
                    date.fromisoformat(p["day_to"]),
                    shift,
                    frozenset(p["resources"]) if p.get("resources") else None,
                )
            )
        elif c.kind == ChangeKind.OVERTIME:
            out.append(
                Overtime(
                    date.fromisoformat(p["day_from"]),
                    date.fromisoformat(p["day_to"]),
                    p["minutes"],
                    p.get("shift"),
                    frozenset(p["resources"]) if p.get("resources") else None,
                )
            )
    return out


def diff_payload(inp: PlanInput, changed: PlanInput, lines_by_id: dict) -> dict:
    """Plan `inp` and `changed` and describe what differs, as the JSON a scenario result stores."""
    before = run_plan(inp)
    after = run_plan(changed)
    diff = diff_results(
        before, after, {ln.id: ln for ln in inp.lines}, {ln.id: ln for ln in changed.lines}
    )

    payload = diff.as_dict()
    for entry in payload["lines"]:
        sl = lines_by_id[entry["line_id"]]
        entry.update(
            part_number=sl.part.part_number, part_name=sl.part.name,
            customer_code=sl.customer.code, customer_name=sl.customer.name,
        )  # fmt: skip
    payload["bottleneck_before"], payload["bottleneck_after"] = (
        diff.bottleneck_before,
        diff.bottleneck_after,
    )

    names = {r.id: r for r in inp.resources}
    mentioned = {int(k) for k in payload["peak_utilisation"]} | {
        x for x in (diff.bottleneck_before, diff.bottleneck_after) if x
    }
    mentioned |= {
        int(d[k]) for d in payload["day_bottlenecks"] for k in ("before", "after") if d[k]
    }
    return {
        "plan_from": inp.settings.plan_from.isoformat(),
        "lines_planned": len(inp.lines),
        "runtime_ms": before.summary["runtime_ms"] + after.summary["runtime_ms"],
        "resources": {str(i): {"code": names[i].code} for i in mentioned if i in names},
        "diff": payload,
    }


def run(scenario: Scenario) -> Scenario:
    """Plan twice from today's data, once as it is and once with the changes, and keep the diff."""
    if scenario.status == ScenarioStatus.APPLIED:
        raise ValidationError({"detail": "This scenario has already been applied."})
    if not scenario.changes.exists():
        raise ValidationError({"detail": "Add at least one change before running the scenario."})
    company = scenario.company
    fingerprint = data_fingerprint(company)
    inp, lines_by_id = build_input(company, timezone.localdate())
    changed: PlanInput = apply_changes(inp, _engine_changes(scenario))
    scenario.result = diff_payload(inp, changed, lines_by_id)
    scenario.last_run_at = timezone.now()
    scenario.run_fingerprint = fingerprint
    scenario.run_signature = change_signature(scenario)
    scenario.save()
    return scenario


def apply(scenario: Scenario, user, recalculate: bool = True) -> dict:
    """Make the changes real, all or nothing. Needs a fresh run, so what is applied is what was seen."""
    if scenario.status == ScenarioStatus.APPLIED:
        raise ValidationError({"detail": "This scenario has already been applied."})
    state = result_state(scenario)
    if state == "never_run":
        raise ValidationError({"detail": "Run the scenario first to see what it does."})
    if state == "changes_edited":
        raise ValidationError(
            {"detail": "The changes were edited after the last run. Run it again before applying."}
        )
    if state == "data_changed":
        raise ValidationError(
            {
                "detail": "The schedule or masters have changed since the last run. Run it again before applying."
            }
        )

    summary = {"downtimes": 0, "line_edits": 0, "adjustments": 0}
    company = scenario.company
    with transaction.atomic():
        for c in scenario.changes.all().order_by("order", "id"):
            p = c.params
            if c.kind == ChangeKind.BLOCK_RESOURCE:
                Downtime.objects.create(
                    company=company,
                    resource=Resource.objects.for_company(company).get(pk=p["resource"]),
                    start_at=datetime.fromisoformat(p["start"]),
                    end_at=datetime.fromisoformat(p["end"]),
                    reason=(p.get("reason") or f"What-if: {scenario.name}")[:200],
                )
                summary["downtimes"] += 1
            elif c.kind in (ChangeKind.CHANGE_QTY, ChangeKind.CHANGE_DATE):
                line = ScheduleLine.objects.for_company(company).get(pk=p["line"])
                if c.kind == ChangeKind.CHANGE_QTY:
                    line.dispatch_qty = p["qty"]
                else:
                    line.internal_dispatch_date = date.fromisoformat(p["date"])
                line.save()
                summary["line_edits"] += 1
            else:
                is_shift = c.kind == ChangeKind.EXTRA_SHIFT
                adj = CapacityAdjustment.objects.create(
                    company=company,
                    kind=AdjustmentKind.EXTRA_SHIFT if is_shift else AdjustmentKind.OVERTIME,
                    day_from=date.fromisoformat(p["day_from"]),
                    day_to=date.fromisoformat(p["day_to"]),
                    name=p.get("name", "") if is_shift else "",
                    start_time=time.fromisoformat(p["start_time"]) if is_shift else None,
                    end_time=time.fromisoformat(p["end_time"]) if is_shift else None,
                    break_minutes=p.get("break_minutes", 0) if is_shift else 0,
                    shift_id=None if is_shift else p.get("shift"),
                    minutes=None if is_shift else p["minutes"],
                    note=f"What-if: {scenario.name}"[:200],
                )
                adj.resources.set(
                    Resource.objects.for_company(company).filter(pk__in=p.get("resources") or [])
                )
                summary["adjustments"] += 1
        scenario.status = ScenarioStatus.APPLIED
        scenario.applied_at = timezone.now()
        scenario.applied_by = user
        scenario.save()

    summary["plan"] = None
    if recalculate:
        plans = Plan.objects.filter(company=company)
        draft = plans.filter(status=PlanStatus.DRAFT).first()
        plan = plan_service.calculate(draft) if draft else plan_service.create_plan(company, user)
        summary["plan"] = {"id": plan.pk, "version": plan.version, "new": draft is None}
    return summary
