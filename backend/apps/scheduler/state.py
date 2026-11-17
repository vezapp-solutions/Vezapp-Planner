"""What state each order is in for planning: the badge shown beside it, and why.

Closed          the order is not open (closed, dispatched or cancelled)
Covered         the balance is zero: WIP, FG and dispatched cover the order
Cannot plan     master data is missing for the part; the reasons say what to fill in
At risk         planned, but it cannot be dispatched by its date (or did not fit the window)
Planned         planned and expected to make its date
Not planned yet open with a balance and master data, but the plan has not been run since it appeared

The state is worked out when the list is read, from the order, the masters and the latest plan, so it
can never disagree with them.
"""

from dataclasses import dataclass, field

from .models import ScheduleLine

CLOSED, COVERED, CANNOT_PLAN, AT_RISK, PLANNED, UNPLANNED = (
    "closed",
    "covered",
    "cannot_plan",
    "at_risk",
    "planned",
    "not_planned_yet",
)


@dataclass
class OrderState:
    state: str
    reasons: list[str] = field(default_factory=list)
    est_dispatch: str | None = None
    slack_working_days: int | None = None


def order_states(company, lines: list[ScheduleLine]) -> dict[int, OrderState]:
    from apps.insights.service import latest_plan  # imported here to keep the apps loosely coupled
    from apps.plans.inputs import part_reasons
    from apps.plans.models import PlanHeatPour, PlanLine

    open_with_balance = [ln for ln in lines if ln.is_open and ln.balance > 0]
    reasons = (
        part_reasons(company, {ln.part_id for ln in open_with_balance}) if open_with_balance else {}
    )
    plan = latest_plan(company)
    plan_lines = {}
    if plan is not None and open_with_balance:
        plan_lines = {
            pl.schedule_line_id: pl
            for pl in PlanLine.objects.filter(
                plan=plan, schedule_line_id__in=[ln.pk for ln in open_with_balance]
            )
        }

    short: dict[int, str] = {}
    if plan is not None and plan_lines:
        for pour in PlanHeatPour.objects.filter(
            heat__plan=plan,
            heat__furnace__isnull=True,
            plan_line_id__in=[pl.pk for pl in plan_lines.values()],
        ).select_related("heat"):
            short.setdefault(
                pour.plan_line_id,
                f"No furnace room for the {pour.heat.grade} heat on {pour.heat.day:%d-%m-%Y} "
                f"({pour.heat.heat_no}).",
            )

    out: dict[int, OrderState] = {}
    for ln in lines:
        if not ln.is_open:
            out[ln.pk] = OrderState(CLOSED)
        elif ln.balance <= 0:
            out[ln.pk] = OrderState(COVERED)
        elif reasons.get(ln.part_id):
            out[ln.pk] = OrderState(CANNOT_PLAN, reasons[ln.part_id])
        else:
            pl = plan_lines.get(ln.pk)
            if pl is None:
                out[ln.pk] = OrderState(UNPLANNED)
            else:
                furnace = short.get(pl.pk)
                bad = pl.status in ("at_risk", "unscheduled") or furnace is not None
                text = pl.holding_text or (pl.notes[0] if pl.notes else "")
                why = [
                    t
                    for t in (text if pl.status in ("at_risk", "unscheduled") else "", furnace)
                    if t
                ]
                out[ln.pk] = OrderState(
                    AT_RISK if bad else PLANNED,
                    why,
                    pl.est_dispatch_date.isoformat() if pl.est_dispatch_date else None,
                    pl.slack_working_days,
                )
    return out
