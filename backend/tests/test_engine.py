"""Planning engine: the section 7.5 worked example and every scheduling rule. Pure Python, no database."""

import random
import time
from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from planning.calendar import ShiftSpec
from planning.engine import run_plan
from planning.kpis import classify
from planning.model import OpSpec, PlanSettings, ResourceSpec
from tests.engine_fixtures import (
    F1,
    KO,
    LINE_A,
    MONDAY,
    S1,
    S2,
    D,
    at,
    h120,
    line,
    plan_input,
    resources,
    week,
)  # fmt: skip

EPS = Decimal("0.0001")


# --- helpers ----------------------------------------------------------------------------------------
def by_day(result, code, rid=None):
    """Quantity allocated per calendar day for an operation."""
    out = defaultdict(Decimal)
    for a in result.allocations:
        if a.op_code == code and (rid is None or a.resource_id == rid):
            out[result.slots[a.slot_idx].day] += a.qty
    return dict(sorted(out.items()))


def op(result, code, line_id=1):
    ln = next(ln for ln in result.lines if ln.line_id == line_id)
    return next(o for o in ln.ops if o.code == code)


def check_invariants(inp, result):
    """Rules that must hold for any plan, whatever the inputs."""
    used = defaultdict(Decimal)
    for a in result.allocations:
        if a.resource_id is not None:
            used[(a.resource_id, a.slot_idx)] += a.minutes
    for (rid, idx), minutes in used.items():
        assert minutes <= result.loads[(rid, idx)].capacity + EPS, (
            f"resource {rid} slot {idx} over capacity"
        )
        assert result.loads[(rid, idx)].load == pytest.approx(minutes, abs=EPS)

    per_op = defaultdict(Decimal)
    for a in result.allocations:
        per_op[(a.line_id, a.op_code)] += a.minutes
    for ln in result.lines:
        if ln.status == "unscheduled" or ln.requirement is None:
            continue
        for o in ln.ops:
            need = ln.requirement.minutes.get(o.code, Decimal(0))
            if o.outsourced or not o.capacity_modelled:
                assert per_op[(ln.line_id, o.code)] == 0 or not o.capacity_modelled
                continue
            got = per_op[(ln.line_id, o.code)]
            if o.kind == "melting":
                assert got >= need - EPS  # whole heats per shift can only add minutes
            else:
                assert got == pytest.approx(need, abs=EPS), (
                    f"line {ln.line_id} {o.code}: {got} vs {need}"
                )
            if o.start_at and o.ready_at:
                assert o.start_at >= o.ready_at - timedelta(seconds=1)


# --- section 7.5: the mandatory worked example -------------------------------------------------------
def test_worked_example_requirement_numbers():
    result = run_plan(plan_input())
    rq = result.lines[0].requirement
    assert rq.pieces_to_pour == 630  # ceil(600 x 1.05)
    assert rq.moulds == 315  # 630 / 2 cavities
    assert rq.cores == 630  # 315 x 2
    assert rq.metal_kg == Decimal(18900)  # 315 x 60
    assert rq.heats == 21  # ceil(315 / 15)
    assert rq.minutes == {
        "core": D(630), "moulding": D("472.5"), "melting": D(1575), "knockout": D(315), "fettling": D(1890),
    }  # fmt: skip
    assert rq.traces["moulds"].formula and rq.traces["heats"].inputs == {
        "moulds": 315,
        "moulds_per_heat": 15,
    }


def test_worked_example_schedule_is_limited_by_the_furnace_not_the_moulding_line():
    result = run_plan(plan_input())
    moulds = by_day(result, "moulding")
    # Line A could make all 315 moulds in a day (765 / 1.5 = 510), but F1 pours 10 heats = 150 moulds a day.
    assert list(moulds.values()) == [150, 150, 15]
    assert list(moulds) == [MONDAY, MONDAY + timedelta(days=1), MONDAY + timedelta(days=2)]
    assert by_day(result, "melting") == moulds  # poured in the shift they are moulded
    assert (
        sum(a.minutes for a in result.allocations if a.op_code == "melting") == 1575
    )  # 21 heats x 75


def test_worked_example_bottleneck_is_furnace_f1():
    result = run_plan(plan_input())
    assert result.bottleneck_overall == F1
    first_two = [b for b in result.bottlenecks if b.day <= MONDAY + timedelta(days=1)]
    assert [b.resource_id for b in first_two] == [F1, F1]
    assert first_two[0].utilisation == pytest.approx(
        Decimal(750) / 765, abs=EPS
    )  # 10 heats x 75 of 765


def test_worked_example_dates_and_status():
    ln = run_plan(plan_input()).lines[0]
    assert ln.est_dispatch == date(2026, 11, 5)
    assert ln.status == "on_track" and ln.slack_working_days > 2
    assert ln.holding_op is None


def test_worked_example_cooling_delays_knockout_by_four_hours():
    result = run_plan(plan_input())
    assert op(result, "knockout").start_at == at(MONDAY, 18)  # poured by 14:00, +4 h in the mould


def test_worked_example_invariants():
    inp = plan_input()
    check_invariants(inp, run_plan(inp))


# --- calendar: holidays, weekly off, downtime, night shifts -------------------------------------------
def test_a_full_holiday_removes_all_capacity_that_day():
    tuesday = MONDAY + timedelta(days=1)
    inp = plan_input(holidays={tuesday: None})
    result = run_plan(inp)
    assert tuesday not in by_day(result, "moulding")
    assert list(by_day(result, "moulding").values()) == [150, 150, 15]  # Mon, Wed, Thu
    check_invariants(inp, result)


def test_a_holiday_for_one_shift_leaves_the_other_running():
    inp = plan_input(holidays={MONDAY: frozenset({2})})
    moulds = by_day(run_plan(inp), "moulding")
    assert moulds[MONDAY] == 75  # only shift 1 ran


def test_sunday_is_skipped_as_a_weekly_off():
    inp = plan_input(lines=[line(qty=2400, internal=date(2026, 12, 20))])
    result = run_plan(inp)
    assert not any(d.weekday() == 6 for d in by_day(result, "fettling"))


def test_furnace_downtime_pushes_moulding_to_the_next_day():
    furnace = replace(resources()[2], downtimes=((at(MONDAY, 5), at(MONDAY, 23)),))
    inp = plan_input(res=[*resources()[:2], furnace, *resources()[3:]])
    result = run_plan(inp)
    assert MONDAY not in by_day(result, "moulding")
    assert list(by_day(result, "moulding").values()) == [150, 150, 15]
    check_invariants(inp, result)


def test_part_day_downtime_removes_only_the_overlapping_minutes():
    furnace = replace(
        resources()[2], downtimes=((at(MONDAY, 6), at(MONDAY, 10)),)
    )  # 4 h of shift 1
    inp = plan_input(res=[*resources()[:2], furnace, *resources()[3:]])
    result = run_plan(inp)
    assert by_day(result, "moulding")[MONDAY] < 150
    check_invariants(inp, result)


def test_resource_under_maintenance_or_inactive_has_no_capacity():
    off = replace(resources()[1], active=False)
    result = run_plan(plan_input(res=[resources()[0], off, *resources()[2:]]))
    ln = result.lines[0]
    assert ln.status == "unscheduled" and "moulding" in (ln.holding_op or "") or ln.notes


def test_a_resource_working_only_some_shifts():
    furnace = replace(resources()[2], shift_ids=frozenset({1}))  # shift 1 only
    result = run_plan(plan_input(res=[*resources()[:2], furnace, *resources()[3:]]))
    assert all(
        result.slots[a.slot_idx].shift_id == 1 for a in result.allocations if a.resource_id == F1
    )
    assert list(by_day(result, "moulding").values())[:2] == [75, 75]


def test_a_shift_crossing_midnight_belongs_to_the_day_it_starts():
    night = ShiftSpec(
        3, "Night", datetime(2000, 1, 1, 22).time(), datetime(2000, 1, 1, 6).time(), 30
    )
    inp = plan_input(shifts=(night,))
    result = run_plan(inp)
    assert result.slots[0].start == at(MONDAY, 22) and result.slots[0].end == at(
        MONDAY + timedelta(days=1), 6
    )
    assert result.slots[0].day == MONDAY
    check_invariants(inp, result)


# --- priority, several lines, several resources --------------------------------------------------------
def test_earlier_internal_date_is_planned_first_then_priority_then_entry_order():
    lines = [
        line(1, qty=300, internal=date(2026, 11, 20), priority="C", order=1),
        line(2, qty=300, internal=date(2026, 11, 20), priority="A", order=2),
        line(3, qty=300, internal=date(2026, 11, 20), priority="A", order=3),
        line(4, qty=300, internal=date(2026, 11, 10), priority="C", order=4),
    ]
    result = run_plan(plan_input(lines=lines))
    finish = {ln.line_id: ln.finish_at for ln in result.lines}
    assert (
        finish[4] < finish[2] < finish[3] < finish[1]
    )  # date first, then A before C, then entry order


def test_two_lines_share_capacity_without_exceeding_it():
    inp = plan_input(lines=[line(1, qty=600), line(2, qty=600)])
    result = run_plan(inp)
    check_invariants(inp, result)
    assert sum(by_day(result, "moulding").values()) == 630  # two lots of 315 moulds
    assert all(
        m <= 150 for m in by_day(result, "moulding").values()
    )  # F1 still pours 150 a day in total


def test_a_second_furnace_and_line_finish_the_lot_sooner():
    base = run_plan(plan_input())
    f2 = ResourceSpec(6, "F2", "furnace", efficiency_pct=D(85), heat_kg=D(1000), heat_minutes=D(75))
    line_b = ResourceSpec(7, "LINE-B", "moulding_line", efficiency_pct=D(85), rate_per_hour=D(40))
    part = h120()
    ops = tuple(
        replace(o, resource_ids=(F1, 6))
        if o.code == "melting"
        else replace(o, resource_ids=(LINE_A, 7))
        if o.code == "moulding"
        else o
        for o in part.ops
    )
    inp = plan_input(res=[*resources(), f2, line_b], parts={1: replace(part, ops=ops)})
    faster = run_plan(inp)
    assert op(faster, "moulding").finish_at < op(base, "moulding").finish_at
    assert {a.resource_id for a in faster.allocations if a.op_code == "melting"} == {F1, 6}
    check_invariants(inp, faster)


# --- coupling, cores, cooling, flow ----------------------------------------------------------------------
def test_without_same_shift_pouring_moulding_is_not_held_back_by_the_furnace():
    inp = plan_input(settings=PlanSettings(plan_from=MONDAY, pour_same_shift=False))
    result = run_plan(inp)
    assert by_day(result, "moulding")[MONDAY] > 150  # Line A runs at its own pace
    assert op(result, "melting").finish_at >= op(result, "moulding").finish_at  # pouring follows
    assert sum(by_day(result, "melting").values()) == 315
    check_invariants(inp, result)


def test_core_lead_time_delays_moulding():
    part = h120()
    core = replace(part.ops[0], extra={"cores_per_mould": 2, "lead_hours": 8})
    inp = plan_input(parts={1: replace(part, ops=(core, *part.ops[1:]))})
    result = run_plan(inp)
    assert op(result, "moulding").start_at >= at(MONDAY, 14)  # cores must be finished a shift ahead


def test_no_cooling_lets_knockout_start_in_the_same_shift_it_was_poured():
    result = run_plan(plan_input(parts={1: h120(cooling=0)}))
    assert op(result, "knockout").start_at == at(MONDAY, 14)


def test_whole_lot_flow_finishes_later_than_progressive_flow():
    prog = run_plan(plan_input())
    whole = run_plan(plan_input(settings=PlanSettings(plan_from=MONDAY, flow_mode="whole_lot")))
    assert op(whole, "knockout").start_at > op(prog, "knockout").start_at
    assert whole.lines[0].finish_at > prog.lines[0].finish_at
    check_invariants(plan_input(), whole)


# --- quantity basis and time bases -----------------------------------------------------------------------
def test_rejection_allowance_applies_up_to_the_booking_operation_only():
    part = replace(h120(), rejection_seq=40)  # booked after knockout
    rq = run_plan(plan_input(parts={1: part})).lines[0].requirement
    assert rq.minutes["knockout"] == 315  # 630 pieces to pour x 0.5
    assert rq.minutes["fettling"] == 1800  # 600 good pieces x 3


def test_per_mould_per_batch_and_fixed_time_bases():
    part = h120()
    extra = (
        OpSpec("painting", "Painting", "post", 55, D(2), "per_mould", resource_ids=(KO,)),
        OpSpec(
            "packing", "Packing", "post", 70, D(5), "per_batch", batch_size=50, resource_ids=(KO,)
        ),
        OpSpec(
            "inspection", "Inspection", "post", 80, D(30), "fixed_per_shift", resource_ids=(KO,)
        ),
    )
    rq = (
        run_plan(plan_input(parts={1: replace(part, ops=(*part.ops, *extra))})).lines[0].requirement
    )
    assert rq.minutes["painting"] == 630  # 315 moulds x 2
    assert rq.minutes["packing"] == 5 * 12  # ceil(600 / 50) = 12 batches
    assert rq.minutes["inspection"] == 30  # one block per lot


def test_outsourced_machining_takes_its_lead_time_and_no_capacity():
    part = h120()
    machining = OpSpec(
        "machining", "Machining", "post", 60, None, "per_piece", outsourced=True, lead_days=5
    )
    inp = plan_input(parts={1: replace(part, ops=(*part.ops, machining))})
    result = run_plan(inp)
    m, fettling = op(result, "machining"), op(result, "fettling")
    assert m.outsourced and not m.capacity_modelled
    assert m.finish_at == fettling.finish_at + timedelta(days=5)
    assert not [a for a in result.allocations if a.op_code == "machining"]
    check_invariants(inp, result)


def test_unconstrained_operation_takes_time_but_loads_no_resource_and_is_flagged():
    part = h120()
    packing = OpSpec("packing", "Packing", "post", 70, D("0.5"), "per_piece")  # no work centre
    inp = plan_input(parts={1: replace(part, ops=(*part.ops, packing))})
    result = run_plan(inp)
    packed = op(result, "packing")
    assert not packed.capacity_modelled and packed.finish_at > op(result, "fettling").start_at
    rows = [a for a in result.allocations if a.op_code == "packing"]
    assert rows and all(a.resource_id is None for a in rows)  # duration only
    assert sum(a.minutes for a in rows) == D(
        300
    )  # 600 good pieces x 0.5: after the rejection booking
    check_invariants(inp, result)


def test_a_day_bucket_operation_releases_its_output_at_the_end_of_the_working_day():
    part = h120()
    fettling = replace(part.ops[-1], bucket="day")
    packing = OpSpec("packing", "Packing", "post", 60, D("0.1"), "per_piece", resource_ids=(KO,))
    inp = plan_input(parts={1: replace(part, ops=(*part.ops[:-1], fettling, packing))})
    result = run_plan(inp)
    assert op(result, "fettling").finish_at.hour == 22  # whole-day release
    assert op(result, "packing").start_at >= at(MONDAY + timedelta(days=1), 6)
    check_invariants(inp, result)


# --- dates, status, backward pass --------------------------------------------------------------------------
def test_classification_thresholds():
    assert [classify(n) for n in (5, 2, 1, 0, -1)] == [
        "on_track",
        "on_track",
        "tight",
        "tight",
        "at_risk",
    ]


def test_a_line_due_before_it_can_be_made_is_at_risk_and_names_the_holding_operation():
    inp = plan_input(lines=[line(qty=600, internal=MONDAY + timedelta(days=2))])
    ln = run_plan(inp).lines[0]
    assert ln.status == "at_risk" and ln.slack_working_days < 0
    assert ln.holding_op in {"core", "moulding", "melting", "knockout", "fettling"}
    assert ln.holding_text


def test_the_operation_whose_work_waits_longest_for_capacity_is_the_one_held_up():
    part = h120()
    slow = replace(
        part.ops[-1], time_value=D(12)
    )  # fettling 12 min a piece on one unit: a real bottleneck
    one_unit = replace(resources()[4], units=1)
    inp = plan_input(res=[*resources()[:4], one_unit], parts={1: replace(part, ops=(*part.ops[:-1], slow))},
                     lines=[line(qty=600, internal=date(2026, 11, 12))])  # fmt: skip
    ln = run_plan(inp).lines[0]
    assert ln.status == "at_risk"
    assert ln.holding_op == "fettling" and "waited" in ln.holding_text


def test_the_furnace_is_named_when_it_holds_up_moulding():
    ln = run_plan(plan_input(lines=[line(qty=600, internal=MONDAY + timedelta(days=2))])).lines[0]
    assert ln.status == "at_risk" and ln.holding_op == "melting"  # F1 paces the moulding line


def test_a_line_already_past_its_date_is_planned_from_today_and_at_risk():
    ln = run_plan(plan_input(lines=[line(internal=MONDAY - timedelta(days=3))])).lines[0]
    assert ln.status == "at_risk" and ln.est_dispatch >= MONDAY


def test_a_lot_that_cannot_finish_inside_the_window_is_unscheduled():
    settings = PlanSettings(plan_from=MONDAY, horizon_days=3, max_window_days=3)
    ln = run_plan(plan_input(lines=[line(qty=20000)], settings=settings)).lines[0]
    assert ln.status == "unscheduled" and ln.est_dispatch is None and ln.notes


def test_a_part_without_a_route_is_unscheduled_with_a_reason():
    empty = replace(h120(), ops=())
    ln = run_plan(plan_input(parts={1: empty})).lines[0]
    assert ln.status == "unscheduled" and "route" in ln.notes[0]


def test_a_company_without_shifts_cannot_be_planned():
    ln = run_plan(plan_input(wk={})).lines[0]
    assert ln.status == "unscheduled"


def test_backward_pass_gives_latest_start_and_finish_ending_on_the_internal_date():
    result = run_plan(plan_input())
    fettling = op(result, "fettling")
    assert fettling.latest_finish == at(date(2026, 11, 20), 22)  # end of working time on the date
    order = ["core", "moulding", "melting", "knockout", "fettling"]
    starts = [op(result, c).latest_start for c in order]
    assert op(result, "knockout").latest_finish <= fettling.latest_finish
    assert starts[0] < starts[3] < starts[4]
    assert all(op(result, c).latest_start < op(result, c).latest_finish for c in order)


def test_required_load_shows_overload_when_the_deadline_is_too_close():
    inp = plan_input(lines=[line(qty=600, internal=MONDAY + timedelta(days=1))])
    result = run_plan(inp)
    over = [c for c in result.loads.values() if c.required > c.capacity > 0]
    assert over, "a lot due tomorrow must show required load above capacity"


# --- determinism, properties, performance ---------------------------------------------------------------------
def snapshot(result):
    return (
        [
            (a.line_id, a.op_code, a.resource_id, a.slot_idx, a.minutes, a.qty)
            for a in result.allocations
        ],
        [
            (ln.line_id, ln.status, ln.est_dispatch, ln.finish_at, ln.holding_op)
            for ln in result.lines
        ],
        [(b.day, b.resource_id, b.utilisation) for b in result.bottlenecks],
    )


def random_plant(seed, n_lines):
    rng = random.Random(seed)
    parts = {}
    for pid in range(1, 6):
        parts[pid] = h120(pid, f"P-{pid}", pour=rng.choice([20, 40, 60]), cavities=rng.choice([1, 2, 4]),
                          cores=rng.choice([0, 1, 2]), rejection=rng.choice([0, 3, 5]), cooling=rng.choice([0, 2, 4]),
                          mph=rng.choice([8, 15, 20]))  # fmt: skip
        if parts[pid].cores_per_mould == 0:
            parts[pid] = replace(parts[pid], ops=parts[pid].ops[1:])
    lines = [
        line(i, rng.randint(1, 5), rng.choice([50, 120, 300, 600]), MONDAY + timedelta(days=rng.randint(2, 28)),
             rng.choice("ABC"), i)
        for i in range(1, n_lines + 1)
    ]  # fmt: skip
    return plan_input(lines=lines, parts=parts, wk=week(S1, S2))


def test_two_runs_give_identical_plans():
    inp = random_plant(7, 40)
    assert snapshot(run_plan(inp)) == snapshot(run_plan(inp))


@pytest.mark.parametrize("seed", range(6))
def test_random_plants_always_respect_capacity_and_conserve_work(seed):
    inp = random_plant(seed, 25)
    check_invariants(inp, run_plan(inp))


def test_replanning_500_lines_takes_under_five_seconds():
    inp = random_plant(11, 500)
    started = time.perf_counter()
    result = run_plan(inp)
    elapsed = time.perf_counter() - started
    assert elapsed < 5, f"500 lines took {elapsed:.1f}s"
    assert len(result.lines) == 500
    check_invariants(inp, result)
