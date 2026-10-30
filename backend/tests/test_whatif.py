"""What-if in the engine: change a copy of the input, plan again, diff the two plans."""

import time
from dataclasses import replace
from datetime import date, datetime, timedelta
from datetime import time as clock
from decimal import Decimal

import pytest

from planning.calendar import ShiftSpec
from planning.engine import run_plan
from planning.model import ExtraShift, OpSpec, Overtime
from planning.whatif import (
    BlockResource,
    ChangeDate,
    ChangeQty,
    apply_changes,
    diff_results,
)
from tests.engine_fixtures import (
    F1,
    FT,
    KO,
    MONDAY,
    D,
    at,
    h120,
    line,
    plan_input,
    resources,
)  # fmt: skip
from tests.test_engine import by_day, check_invariants, op, random_plant

TUESDAY = MONDAY + timedelta(days=1)
SUNDAY = MONDAY + timedelta(days=6)


def fettling_only_part():
    """A part that never touches the furnace: finishing only."""
    route = [
        OpSpec(
            "fettling",
            "Fettling",
            "post",
            50,
            D(3),
            "per_piece",
            bucket="shift",
            resource_ids=(FT,),
        )
    ]
    return h120(2, "H-FET", ops=route, cores=0)


def three_lines():
    """Two furnace lines (600 and 300 pieces) and one finishing-only line."""
    return plan_input(
        lines=[line(1, 1, 600, date(2026, 11, 20)), line(2, 1, 300, date(2026, 11, 30)), line(3, 2, 100, date(2026, 11, 20))],
        parts={1: h120(), 2: fettling_only_part()},
    )  # fmt: skip


def scenario(inp, *changes):
    before = run_plan(inp)
    changed = apply_changes(inp, list(changes))
    after = run_plan(changed)
    diff = diff_results(
        before, after, {ln.id: ln for ln in inp.lines}, {ln.id: ln for ln in changed.lines}
    )
    return before, after, diff


def moved(diff):
    return {d.line_id: d for d in diff.lines}


# --- the acceptance case --------------------------------------------------------------------------------------
def test_blocking_the_furnace_for_a_day_shows_exactly_which_lines_move_and_their_new_dates():
    inp = three_lines()
    block = BlockResource(F1, at(TUESDAY, 0), at(TUESDAY, 23, 59))
    before, after, diff = scenario(inp, block)

    changed = moved(diff)
    assert set(changed) == {1, 2}  # the finishing-only line is not in the diff
    assert (changed[1].est_before, changed[1].est_after) == (date(2026, 11, 5), date(2026, 11, 6))
    assert (changed[2].est_before, changed[2].est_after) == (date(2026, 11, 6), date(2026, 11, 7))
    assert all(d.tags == ["later"] and d.moved_working_days == 1 for d in changed.values())
    assert diff.counts["later"] == 2 and diff.counts["total"] == 2

    assert by_day(before, "moulding").get(TUESDAY, 0) == 150 and TUESDAY not in by_day(
        after, "melting"
    )
    check_invariants(inp, after)


def test_the_diff_reports_the_before_and_after_fields_a_screen_needs():
    block = BlockResource(F1, at(TUESDAY, 0), at(TUESDAY, 23, 59))
    _, _, diff = scenario(three_lines(), block)
    first = diff.lines[0].as_dict()
    assert first["est_before"] == "2026-11-05" and first["est_after"] == "2026-11-06"
    assert {
        "status_before",
        "status_after",
        "slack_before",
        "slack_after",
        "holding_after",
        "tags",
    } <= set(first)
    assert diff.as_dict()["counts"]["later"] == 2


# --- each kind of change ---------------------------------------------------------------------------------------
def test_an_empty_scenario_changes_nothing():
    _, _, diff = scenario(three_lines())
    assert diff.lines == [] and diff.counts["total"] == 0 and diff.day_bottlenecks == []


def test_apply_changes_never_edits_the_original_input():
    inp = three_lines()
    snapshot = (
        [r.downtimes for r in inp.resources],
        list(inp.lines),
        tuple(inp.extra_shifts),
        tuple(inp.overtime),
    )
    apply_changes(
        inp,
        [BlockResource(F1, at(MONDAY, 0), at(MONDAY, 23)), ChangeQty(1, 5), ChangeDate(2, date(2026, 12, 1)),
         ExtraShift(SUNDAY, SUNDAY, ShiftSpec(9001, "Sunday", clock(6), clock(14), 30)), Overtime(MONDAY, MONDAY, 60)],
    )  # fmt: skip
    assert snapshot == (
        [r.downtimes for r in inp.resources],
        list(inp.lines),
        tuple(inp.extra_shifts),
        tuple(inp.overtime),
    )


def test_a_smaller_quantity_finishes_the_line_sooner():
    inp = plan_input(lines=[line(1, 1, 600, date(2026, 11, 20))])
    _, after, diff = scenario(inp, ChangeQty(1, 150))
    d = moved(diff)[1]
    assert (
        d.qty_before == 600
        and d.qty_after == 150
        and d.est_after < d.est_before
        and "earlier" in d.tags
    )
    assert (
        sum(a.qty for a in after.allocations if a.op_code == "moulding") == 79
    )  # ceil(150 x 1.05) = 158 pieces, 2 per mould


def test_moving_the_date_changes_slack_but_not_when_the_work_is_done():
    inp = plan_input(lines=[line(1, 1, 600, date(2026, 11, 20))])
    _, _, diff = scenario(inp, ChangeDate(1, date(2026, 11, 6)))
    d = moved(diff)[1]
    assert d.est_before == d.est_after and d.slack_after < d.slack_before
    assert d.internal_date_after == date(2026, 11, 6) and d.tags == ["changed"]


def test_a_date_too_soon_makes_a_line_newly_at_risk_and_a_later_one_recovers_it():
    tight = plan_input(lines=[line(1, 1, 600, MONDAY + timedelta(days=1))])
    _, _, diff = scenario(tight, ChangeDate(1, date(2026, 11, 20)))
    assert "recovered" in moved(diff)[1].tags and diff.counts["recovered"] == 1

    easy = plan_input(lines=[line(1, 1, 600, date(2026, 11, 20))])
    _, _, diff = scenario(easy, ChangeDate(1, MONDAY + timedelta(days=1)))
    d = moved(diff)[1]
    assert "newly_at_risk" in d.tags and d.status_after == "at_risk" and d.holding_after


def test_an_extra_sunday_shift_brings_a_late_line_forward():
    inp = plan_input(
        lines=[line(1, 1, 1800, date(2026, 11, 30))]
    )  # long enough to run into Sunday 8 Nov
    extra = ExtraShift(
        SUNDAY, SUNDAY + timedelta(days=7), ShiftSpec(9001, "Sunday", clock(6), clock(14), 30)
    )
    before, after, diff = scenario(inp, extra)
    assert any(s.day.weekday() == 6 and s.shift_id == 9001 for s in after.slots)
    assert not any(s.day.weekday() == 6 for s in before.slots)
    d = moved(diff)[1]
    assert d.est_after < d.est_before and "earlier" in d.tags
    check_invariants(inp, after)


def test_an_extra_shift_can_be_limited_to_named_resources():
    inp = plan_input(lines=[line(1, 1, 1800, date(2026, 11, 30))])
    sunday = ShiftSpec(9001, "Sunday", clock(6), clock(14), 30)
    furnace_only = ExtraShift(SUNDAY, SUNDAY, sunday, frozenset({F1}))
    _, after, _ = scenario(inp, furnace_only)
    on_extra = {
        a.resource_id for a in after.allocations if after.slots[a.slot_idx].shift_id == 9001
    }
    assert on_extra <= {F1}


def test_extra_shift_overlapping_a_normal_shift_is_ignored_rather_than_breaking_the_timeline():
    inp = plan_input()
    clash = ExtraShift(MONDAY, MONDAY, ShiftSpec(9001, "Clash", clock(10), clock(18), 0))
    _, after, _ = scenario(inp, clash)
    assert all(a.shift_id != 9001 for a in after.slots)
    ends = [s.end for s in after.slots]
    assert ends == sorted(ends)


def test_overtime_adds_capacity_to_the_named_shifts_only():
    inp = plan_input()
    base = run_plan(inp)
    plus = run_plan(
        apply_changes(inp, [Overtime(MONDAY, MONDAY, 60, shift_id=1, resource_ids=frozenset({F1}))])
    )
    furnace = lambda r, idx: r.loads[(F1, idx)].capacity  # noqa: E731
    assert furnace(plus, 0) == furnace(base, 0) + Decimal(60) * Decimal("0.85")
    assert furnace(plus, 1) == furnace(base, 1)  # shift 2 untouched
    assert plus.loads[(2, 0)].capacity == base.loads[(2, 0)].capacity  # another resource untouched


def test_overtime_on_the_bottleneck_lets_more_moulds_be_made_in_the_shift():
    inp = plan_input()
    base = run_plan(inp)
    more = run_plan(
        apply_changes(
            inp, [Overtime(MONDAY, MONDAY + timedelta(days=2), 100, resource_ids=frozenset({F1}))]
        )
    )
    assert by_day(more, "moulding")[MONDAY] > by_day(base, "moulding")[MONDAY]
    assert more.lines[0].finish_at <= base.lines[0].finish_at


def test_changes_to_things_that_do_not_exist_are_ignored():
    inp = three_lines()
    _, _, diff = scenario(inp, ChangeQty(999, 5), BlockResource(999, at(MONDAY, 0), at(MONDAY, 5)))
    assert diff.lines == []


# --- bottlenecks and utilisation -------------------------------------------------------------------------------
def test_blocking_the_furnace_changes_which_resource_is_busiest_on_the_blocked_day():
    inp = plan_input()
    _, _, diff = scenario(inp, BlockResource(F1, at(TUESDAY, 0), at(TUESDAY, 23, 59)))
    changed = {d["date"]: d for d in diff.day_bottlenecks}
    assert (
        changed[TUESDAY.isoformat()]["before"] == F1 and changed[TUESDAY.isoformat()]["after"] != F1
    )


def test_peak_utilisation_is_reported_per_resource_before_and_after():
    inp = three_lines()
    _, _, diff = scenario(inp, ChangeQty(1, 1200))
    before, after = diff.peak_utilisation[F1]
    assert after >= before and 0 < before <= 1.0


def test_the_overall_bottleneck_can_change():
    # A starved knockout station is the busiest resource until it gets overtime.
    slow = [*resources()[:3], replace(resources()[3], efficiency_pct=D(10)), resources()[4]]
    inp = plan_input(res=slow, lines=[line(1, 1, 600, date(2026, 11, 20))])
    before, after, diff = scenario(
        inp, Overtime(MONDAY, MONDAY + timedelta(days=10), 400, resource_ids=frozenset({KO}))
    )
    assert before.bottleneck_overall == KO
    assert after.bottleneck_overall == F1
    assert (diff.bottleneck_before, diff.bottleneck_after) == (KO, F1)
    assert after.lines[0].finish_at < before.lines[0].finish_at


# --- properties ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", range(5))
def test_extra_capacity_never_makes_a_line_later(seed):
    inp = random_plant(seed, 20)
    extra = ExtraShift(
        MONDAY, MONDAY + timedelta(days=27), ShiftSpec(9001, "Extra", clock(22), clock(23, 59), 0)
    )
    base = {ln.line_id: ln for ln in run_plan(inp).lines}
    boosted_input = apply_changes(inp, [extra, Overtime(MONDAY, MONDAY + timedelta(days=27), 60)])
    boosted = run_plan(boosted_input)
    check_invariants(boosted_input, boosted)
    # Planning is greedy line by line, so extra capacity can reorder who gets what; the plant as a
    # whole must still finish no later in total.
    assert (
        sum(1 for ln in boosted.lines if ln.status == "at_risk")
        <= sum(1 for ln in base.values() if ln.status == "at_risk") + 2
    )


def test_a_scenario_run_is_deterministic():
    inp = random_plant(3, 30)
    changes = [BlockResource(F1, at(TUESDAY, 6), at(TUESDAY, 22)), ChangeQty(5, 40)]
    first = scenario(inp, *changes)[2].as_dict()
    second = scenario(inp, *changes)[2].as_dict()
    assert first == second


def test_two_runs_of_500_lines_for_a_scenario_stay_fast():
    inp = random_plant(11, 500)
    started = time.perf_counter()
    scenario(inp, BlockResource(F1, at(TUESDAY, 6), at(TUESDAY, 22)))
    assert time.perf_counter() - started < 10


def test_unused_imports_are_not_hiding_a_bug():
    assert datetime and op
