"""Refresh a company's insight cards from its latest plan, schedule and masters; test a suggestion."""

import logging
from datetime import date

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.plans.inputs import build_input
from apps.plans.models import Plan, PlanStatus
from apps.scenarios.service import diff_payload
from insights import digest, health, performance, plan_cards, rules
from insights.model import Card
from planning.whatif import AllowResource, apply_changes

from . import collect
from .models import Insight, InsightRun, RunTrigger

log = logging.getLogger(__name__)


def latest_plan(company) -> Plan | None:
    """The plan the screens open on: the newest draft, else the newest confirmed plan."""
    plans = Plan.objects.filter(company=company)
    return plans.filter(status=PlanStatus.DRAFT).first() or plans.first()


def build_cards(company, plan: Plan | None, today: date) -> list[Card]:
    cards: list[Card] = []
    if plan is not None and plan.calculated_at is not None:
        lines = collect.line_facts(plan)
        rows = collect.load_rows(plan)
        days = collect.window_days(plan, rows, today)
        loads, shift_minutes = collect.capacity_inputs(rows)
        cards += plan_cards.at_risk(lines)
        cards += plan_cards.bottleneck_forecast(collect.bottleneck_days(plan, days))
        cards += plan_cards.capacity_gap(loads, shift_minutes)
        cards += plan_cards.melting(collect.melt_rows(plan), collect.furnace_days(rows))
        cards += plan_cards.load_balancing(collect.balance_candidates(plan, rows, days))
        cards += plan_cards.month_forecast(lines, today)
        cards += plan_cards.concentration(lines, collect.quantity_history(company), today)
    cards += performance.dispatch_cards(collect.dispatch_rows(company), today)
    cards += health.data_health(collect.health_items(company, today))
    return cards


@transaction.atomic
def refresh(company, plan: Plan | None = None, trigger: str = RunTrigger.MANUAL) -> InsightRun:
    """Compute every card and store them as a new run, with a trend against the previous run."""
    today = timezone.localdate()
    plan = plan or latest_plan(company)
    cards = digest.ranked(build_cards(company, plan, today))

    previous_run = InsightRun.objects.filter(company=company).first()
    previous = (
        dict(previous_run.cards.values_list("key", "impact")) if previous_run is not None else {}
    )
    run = InsightRun.objects.create(
        company=company, plan=plan, trigger=trigger,
        counts={
            "total": len(cards),
            "by_severity": {s: sum(1 for c in cards if c.severity == s) for s in rules.SEVERITY_WEIGHT},
            "by_type": {t: sum(1 for c in cards if c.type == t) for t in sorted({c.type for c in cards})},
            "resolved": len(digest.resolved(cards, previous)),
        },
    )  # fmt: skip
    Insight.objects.bulk_create(
        [
            Insight(
                company=company, run=run, key=c.key, type=c.type, severity=c.severity, title=c.title,
                message=c.message, numbers=c.numbers, entities=c.entities, action=c.action,
                why=list(c.why), impact=c.impact, rank=c.rank, trend=digest.trend(c, previous),
            )
            for c in cards
        ]
    )  # fmt: skip
    stale = (
        InsightRun.objects.filter(company=company)
        .order_by("-id")
        .values_list("pk", flat=True)[rules.RUNS_KEPT :]
    )
    InsightRun.objects.filter(pk__in=list(stale)).delete()
    return run


def refresh_quietly(company, plan: Plan | None = None, trigger: str = RunTrigger.MANUAL) -> None:
    """Refresh as a side effect of something else: a failure here must never fail that."""
    try:
        with transaction.atomic():
            refresh(company, plan, trigger)
    except Exception:
        log.exception("Insight refresh failed for company %s", company.pk)


def latest_run(company) -> InsightRun | None:
    return InsightRun.objects.filter(company=company).first()


def dry_run(company, insight: Insight) -> dict:
    """Test a load-balancing suggestion: plan twice, with and without it, and diff. Changes nothing."""
    recipe = (insight.entities or {}).get("dry_run")
    if insight.type != "load_balancing" or not recipe:
        raise ValidationError({"detail": "This insight has nothing to test."})
    inp, lines_by_id = build_input(company, timezone.localdate())
    changed = apply_changes(
        inp, [AllowResource(recipe["part_id"], recipe["op_code"], recipe["resource_id"])]
    )
    return diff_payload(inp, changed, lines_by_id)
