"""Machining as several operations per part, timed per machine type, with setup, on the machines
that are free. Pure engine tests: no database."""

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from planning.engine import run_plan
from planning.model import OpSpec, PartSpec, ResourceSpec, step_code, type_of
from planning.whatif import BlockResource, apply_changes
from tests.engine_fixtures import MONDAY, S1, D, at, line, plan_input

VMC, CNC, HMC = 101, 102, 103  # resource types
VMC1, VMC2, CNC1, HMC1 = 11, 12, 13, 14


def machines(eff=85):
    e = D(eff)
    return [
        ResourceSpec(VMC1, "VMC-1", "work_centre", efficiency_pct=e, type_id=VMC),
        ResourceSpec(VMC2, "VMC-2", "work_centre", efficiency_pct=e, type_id=VMC),
        ResourceSpec(CNC1, "CNC-1", "work_centre", efficiency_pct=e, type_id=CNC),
        ResourceSpec(HMC1, "HMC-1", "work_centre", efficiency_pct=e, type_id=HMC),
    ]


def step(number, name, rids, time="12", by_type=None, setup="0", seq=60):
    return OpSpec(
        step_code("machining", number), f"Machining OP{number} {name}".strip(), "post", seq + number // 10,
        D(time), "per_piece", bucket="shift", resource_ids=tuple(rids), step=number,
        setup_minutes=D(setup), time_by_type={k: D(v) for k, v in (by_type or {}).items()},
    )  # fmt: skip


def part(*ops):
    return PartSpec(1, "H-120", 10, "GG25", D(25), D(60), 2, 0, D(0), tuple(ops), rejection_seq=50)


def plan(*ops, qty=200, res=None, lines=None, wk_shifts=(S1,)):
    return plan_input(
        lines=lines or [line(qty=qty)],
        parts={1: part(*ops)},
        res=res or machines(),
        shifts=wk_shifts,
    )


def pieces_by_machine_and_day(result, code):
    out = defaultdict(Decimal)
    for a in result.allocations:
        if a.op_code == code:
            out[(a.resource_id, result.slots[a.slot_idx].day)] += a.qty
    return dict(out)


def op(result, code, line_id=1):
    return next(
        o for o in next(ln for ln in result.lines if ln.line_id == line_id).ops if o.code == code
    )


def snapshot(result):
    return [
        (a.line_id, a.op_code, a.resource_id, a.slot_idx, a.minutes, a.qty)
        for a in result.allocations
    ]


# --- codes ------------------------------------------------------------------------------------------------
def test_step_codes_are_unique_and_map_back_to_the_operation_type():
    assert step_code("machining", 0) == "machining" and step_code("machining", 20) == "machining~20"
    assert type_of("machining~20") == "machining" and type_of("fettling") == "fettling"


def test_two_machining_steps_of_one_part_are_planned_separately():
    ops = (step(10, "Rough", [VMC1, VMC2, HMC1]), step(20, "Finish", [CNC1], time="8"))
    result = run_plan(plan(*ops, qty=100))
    line_result = result.lines[0]
    assert [o.code for o in line_result.ops] == ["machining~10", "machining~20"]
    assert [o.name for o in line_result.ops] == ["Machining OP10 Rough", "Machining OP20 Finish"]
    rough = {a.resource_id for a in result.allocations if a.op_code == "machining~10"}
    finish = {a.resource_id for a in result.allocations if a.op_code == "machining~20"}
    assert rough <= {VMC1, VMC2, HMC1} and finish == {CNC1}  # each step stays on its own machines
    assert (
        op(result, "machining~20").start_at >= op(result, "machining~10").start_at
    )  # pieces flow on
    assert op(result, "machining~20").finish_at >= op(result, "machining~10").finish_at


# --- time per machine type --------------------------------------------------------------------------------------
def test_a_faster_machine_type_makes_more_pieces_in_the_same_shift():
    # VMC 12 min a piece, HMC 6: in a 382.5 minute shift a VMC makes 31.875 pieces and an HMC 63.75.
    result = run_plan(plan(step(10, "", [VMC1, HMC1], by_type={HMC: "6"}), qty=500))
    first = pieces_by_machine_and_day(result, "machining~10")
    assert first[(HMC1, MONDAY)] == pytest.approx(63.75)
    assert first[(VMC1, MONDAY)] == pytest.approx(31.875)


def test_the_default_time_applies_to_a_type_without_its_own():
    ops = step(10, "", [VMC1, CNC1], time="10", by_type={CNC: "5"})
    result = run_plan(plan(ops, qty=500))
    first = pieces_by_machine_and_day(result, "machining~10")
    assert first[(CNC1, MONDAY)] == pytest.approx(76.5)  # 382.5 ÷ 5
    assert first[(VMC1, MONDAY)] == pytest.approx(38.25)  # 382.5 ÷ 10, the default


def test_the_requirement_uses_the_average_time_of_the_allowed_machines():
    result = run_plan(plan(step(10, "", [VMC1, HMC1], by_type={VMC: "12", HMC: "6"}), qty=200))
    requirement = result.lines[0].requirement
    assert requirement.minutes["machining~10"] == 200 * 9  # (12 + 6) ÷ 2
    assert "average" in requirement.traces["minutes.machining~10"].formula


# --- machine availability ---------------------------------------------------------------------------------------
def test_work_goes_to_a_machine_that_is_free_when_another_is_down():
    inp = plan(step(10, "", [VMC1, VMC2]), qty=60)
    down = [
        ResourceSpec(
            VMC1,
            "VMC-1",
            "work_centre",
            efficiency_pct=D(85),
            type_id=VMC,
            downtimes=((at(MONDAY, 0), at(MONDAY, 23, 59)),),
        )
    ]
    inp.resources[:] = [*down, *(r for r in machines() if r.id != VMC1)]
    result = run_plan(inp)
    first_day = {
        m for (m, day) in pieces_by_machine_and_day(result, "machining~10") if day == MONDAY
    }
    assert first_day == {VMC2}  # VMC-1 was blocked on Monday


def test_blocking_a_machine_for_a_day_moves_the_lines_that_needed_it():
    base = plan(step(10, "", [VMC1, VMC2]), qty=120)  # two VMCs: 63.75 pieces on Monday
    before = run_plan(base)
    after = run_plan(
        apply_changes(
            base,
            [
                BlockResource(VMC2, at(MONDAY, 0), at(MONDAY, 23, 59)),
                BlockResource(VMC1, at(MONDAY, 0), at(MONDAY, 23, 59)),
            ],
        )
    )
    assert op(after, "machining~10").finish_at > op(before, "machining~10").finish_at


def test_a_machine_that_is_not_allowed_never_takes_the_work():
    result = run_plan(plan(step(10, "", [VMC1]), qty=500))
    assert {a.resource_id for a in result.allocations} == {VMC1}


def test_machines_are_chosen_by_pieces_so_the_fast_one_is_used_first():
    result = run_plan(plan(step(10, "", [VMC1, HMC1], by_type={HMC: "4"}), qty=20))
    assert {a.resource_id for a in result.allocations} == {
        HMC1
    }  # 20 pieces fit on the HMC in the first shift


# --- setup ---------------------------------------------------------------------------------------------------------
def test_setup_is_taken_from_the_machine_before_its_first_piece():
    result = run_plan(plan(step(10, "", [VMC1], setup="60"), qty=20))
    rows = [a for a in result.allocations if a.op_code == "machining~10"]
    assert {a.resource_id for a in rows} == {VMC1} and sum(a.setup for a in rows) == 60
    assert sum(a.qty for a in rows) == pytest.approx(20)
    assert sum(a.minutes for a in rows) == pytest.approx(20 * 12 + 60)
    assert op(result, "machining~10").minutes == pytest.approx(
        20 * 12 + 60
    )  # setup shows in the minutes


def test_each_machine_used_for_a_lot_is_set_up_once():
    result = run_plan(plan(step(10, "", [VMC1, VMC2], setup="30"), qty=300))
    rows = [a for a in result.allocations if a.op_code == "machining~10"]
    setup = defaultdict(Decimal)
    for a in rows:
        setup[a.resource_id] += a.setup
    assert dict(setup) == {VMC1: 30, VMC2: 30}  # both used, one setup each, however many shifts


def test_a_setup_longer_than_a_shift_carries_into_the_next():
    result = run_plan(plan(step(10, "", [VMC1], setup="500"), qty=10))
    per_day = defaultdict(Decimal)
    for a in result.allocations:
        per_day[result.slots[a.slot_idx].day] += a.setup
    assert dict(per_day) == {MONDAY: Decimal("382.5"), MONDAY + timedelta(days=1): Decimal("117.5")}


def test_setup_makes_a_small_lot_take_longer():
    plain = run_plan(plan(step(10, "", [VMC1]), qty=30))
    with_setup = run_plan(plan(step(10, "", [VMC1], setup="400"), qty=30))
    assert op(with_setup, "machining~10").finish_at > op(plain, "machining~10").finish_at


def test_a_step_without_setup_or_type_times_is_planned_as_before():
    result = run_plan(plan(step(10, "", [VMC1]), qty=40))
    assert all(a.setup == 0 for a in result.allocations)  # no setup
    assert op(result, "machining~10").minutes == 40 * 12


# --- the whole plan ---------------------------------------------------------------------------------------------------
def test_machining_plans_are_deterministic_and_respect_capacity():
    ops = (
        step(10, "Rough", [VMC1, VMC2, HMC1], by_type={HMC: "7"}, setup="45"),
        step(20, "Finish", [CNC1, HMC1], time="9", by_type={HMC: "6"}, setup="20"),
    )
    inp = plan(*ops, lines=[line(1, qty=150), line(2, qty=90), line(3, qty=60)])
    first, second = run_plan(inp), run_plan(inp)
    assert snapshot(first) == snapshot(second)
    used = defaultdict(Decimal)
    for a in first.allocations:
        used[(a.resource_id, a.slot_idx)] += a.minutes
    for key, minutes in used.items():
        assert minutes <= first.loads[key].capacity + Decimal("0.0001"), key
    for ln in first.lines:
        assert ln.status != "unscheduled"
        rough, finish = (
            next(o for o in ln.ops if o.code == c) for c in ("machining~10", "machining~20")
        )
        assert finish.finish_at >= rough.finish_at


def test_a_machining_step_after_the_original_one_keeps_both():
    ops = (
        OpSpec(
            "machining",
            "Machining",
            "post",
            60,
            D(10),
            "per_piece",
            bucket="shift",
            resource_ids=(VMC1,),
        ),
        step(20, "Bore", [HMC1], time="5"),
    )
    result = run_plan(plan(*ops, qty=40))
    assert [o.code for o in result.lines[0].ops] == ["machining", "machining~20"]
    assert {a.resource_id for a in result.allocations if a.op_code == "machining"} == {VMC1}


def test_the_what_if_input_copy_keeps_step_fields():
    inp = plan(step(10, "", [VMC1], setup="30", by_type={VMC: "11"}), qty=10)
    changed = apply_changes(inp, [])
    spec = changed.parts[1].ops[0]
    assert (spec.step, spec.setup_minutes, dict(spec.time_by_type)) == (10, D(30), {VMC: D(11)})
    assert datetime(MONDAY.year, MONDAY.month, MONDAY.day) == at(MONDAY, 0)
