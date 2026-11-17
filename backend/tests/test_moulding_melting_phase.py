"""The moulding-and-melting phase: deadline and release window, per-machine mould rate, plannability,
and the grade-wise heat planner that follows the mould plan."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from planning.checks import plannability
from planning.engine import run_plan
from planning.melt import plan_melt
from planning.model import OpSpec, PartSpec, PlanSettings
from tests.engine_fixtures import F1, LINE_A, MONDAY, D, line, plan_input, resources


def mould_only(
    pid=1, number="M-1", grade="GG25", pour=60, cavities=2, rejection=0, time=None, **over
):
    ops = (
        OpSpec(
            "moulding",
            "Moulding",
            "moulding",
            20,
            time,
            "per_mould",
            resource_ids=(LINE_A,),
            **over,
        ),
    )
    return PartSpec(pid, number, pid, grade, D(25), D(pour), cavities, 0, D(rejection), ops)


def run(inp):
    return run_plan(inp)


def first_allocation_day(result, line_id=1):
    slots = {s.idx: s.day for s in result.slots}
    return min(slots[a.slot_idx] for a in result.allocations if a.line_id == line_id)


# --- deadline, release window, per-machine rate -------------------------------------------------------
def test_post_pour_days_move_the_deadline_earlier_and_the_estimate_later():
    parts = {1: mould_only()}
    base = run(plan_input(parts=parts, lines=[line(qty=400, internal=date(2026, 11, 20))]))
    spaced = run(
        plan_input(
            parts=parts,
            lines=[line(qty=400, internal=date(2026, 11, 20))],
            settings=PlanSettings(plan_from=MONDAY, post_pour_days=3),
        )
    )
    a, b = base.lines[0], spaced.lines[0]
    assert b.est_dispatch > a.est_dispatch
    assert b.slack_working_days == a.slack_working_days - 3
    # the work itself is planned in the same place; only the reading of dispatch moves
    assert b.finish_at == a.finish_at


def test_a_line_is_not_started_before_its_release_window():
    parts = {1: mould_only()}
    due = date(2026, 12, 18)  # a Friday, about six weeks out
    early = run(plan_input(parts=parts, lines=[line(qty=300, internal=due)]))
    windowed = run(
        plan_input(
            parts=parts,
            lines=[line(qty=300, internal=due)],
            settings=PlanSettings(plan_from=MONDAY, max_lead_days=3, post_pour_days=0),
        )
    )
    assert first_allocation_day(early) == MONDAY
    assert first_allocation_day(windowed) >= date(2026, 12, 15)  # 3 working days before the 18th


def test_release_window_keeps_earliest_dispatch_first():
    parts = {1: mould_only()}
    lines = [
        line(1, qty=2000, internal=date(2026, 12, 4)),
        line(2, qty=2000, internal=date(2026, 12, 1)),
    ]
    result = run(
        plan_input(
            parts=parts,
            lines=lines,
            settings=PlanSettings(plan_from=MONDAY, max_lead_days=5),
        )
    )
    by_id = {r.line_id: r for r in result.lines}
    assert by_id[2].finish_at < by_id[1].finish_at


def test_a_part_can_have_its_own_mould_rate_on_a_machine():
    slow = {1: mould_only(time_by_resource={LINE_A: D(3)})}
    fast = {1: mould_only()}
    ln = [line(qty=600, internal=date(2026, 12, 4))]
    r_slow = run(plan_input(parts=slow, lines=ln)).lines[0].requirement
    r_fast = run(plan_input(parts=fast, lines=ln)).lines[0].requirement
    assert r_slow.moulds == r_fast.moulds
    assert r_slow.minutes["moulding"] == r_fast.minutes["moulding"] * 2


# --- plannability -----------------------------------------------------------------------------------------
def test_plannability_names_what_is_missing():
    ok = mould_only()
    assert plannability(ok, resources()) == []

    no_route = replace(ok, ops=())
    assert any("moulding operation" in r for r in plannability(no_route, resources()))

    no_machine = replace(ok, ops=(replace(ok.ops[0], resource_ids=()),))
    assert any("moulding machine" in r for r in plannability(no_machine, resources()))

    no_rate = replace(ok, ops=(replace(ok.ops[0], time_value=None),))
    bare = [r if r.id != LINE_A else replace(r, rate_per_hour=None) for r in resources()]
    assert any("moulding rate" in r for r in plannability(no_rate, bare))

    assert any(
        "pouring weight" in r
        for r in plannability(replace(ok, pouring_weight_per_mould_kg=D(0)), resources())
    )
    assert any("grade" in r for r in plannability(replace(ok, grade_name=""), resources()))
    no_furnace = [r for r in resources() if r.kind != "furnace"]
    assert any("furnace" in r for r in plannability(ok, no_furnace))


# --- the heat planner --------------------------------------------------------------------------------------
def melt_for(parts, lines, res=None, **kw):
    inp = plan_input(parts=parts, lines=lines, res=res)
    result = run(inp)
    return inp, result, plan_melt(inp, result, **kw)


def poured_by_grade(inp, result):
    lines = {ln.id: ln for ln in inp.lines}
    totals: dict[str, Decimal] = {}
    for a in result.allocations:
        part = inp.parts[lines[a.line_id].part_id]
        if a.op_code == "moulding":
            totals[part.grade_name] = (
                totals.get(part.grade_name, D(0)) + a.qty * part.pouring_weight_per_mould_kg
            )
    return totals


def two_grades():
    parts = {
        1: mould_only(1, "GG-1", "GG25", pour=60, cavities=2),
        2: mould_only(2, "SG-1", "SG500", pour=100, cavities=1),
    }
    lines = [
        line(1, 1, qty=500, internal=date(2026, 11, 13)),
        line(2, 2, qty=150, internal=date(2026, 11, 13)),
    ]
    return parts, lines


def test_a_heat_is_one_grade_and_never_mixes():
    parts, lines = two_grades()
    inp, result, melt = melt_for(parts, lines)
    assert melt.heats
    for heat in melt.heats:
        assert {
            inp.parts[next(ln.part_id for ln in inp.lines if ln.id == p.line_id)].grade_name
            for p in heat.pours
        } == {heat.grade}
        assert heat.kg <= heat.capacity_kg


def test_metal_in_the_heats_equals_metal_the_moulds_need():
    parts, lines = two_grades()
    inp, result, melt = melt_for(parts, lines)
    needed = poured_by_grade(inp, result)
    planned: dict[str, Decimal] = {}
    for heat in melt.heats:
        planned[heat.grade] = planned.get(heat.grade, D(0)) + heat.kg
    assert planned == needed


def test_parts_of_one_grade_share_heats_on_a_day():
    parts = {
        1: mould_only(1, "GG-1", "GG25", pour=40, cavities=2),
        2: mould_only(2, "GG-2", "GG25", pour=40, cavities=2),
    }
    lines = [
        line(1, 1, qty=20, internal=date(2026, 11, 13)),
        line(2, 2, qty=20, internal=date(2026, 11, 13)),
    ]
    _, _, melt = melt_for(parts, lines)
    first_day = melt.heats[0].day
    same_day = [h for h in melt.heats if h.day == first_day]
    assert len(same_day) == 1  # one pooled heat, not one per part
    assert {p.part_number for p in same_day[0].pours} == {"GG-1", "GG-2"}


def test_a_small_last_heat_is_reported_as_under_filled():
    parts = {1: mould_only(1, "GG-1", "GG25", pour=60, cavities=2)}
    _, _, melt = melt_for(parts, [line(qty=40, internal=date(2026, 11, 13))])
    assert [w.kind for w in melt.warnings] == ["under_filled"]
    assert melt.summary["under_filled"] == 1


def test_a_full_heat_is_not_under_filled():
    parts = {1: mould_only(1, "GG-1", "GG25", pour=50, cavities=1)}
    _, _, melt = melt_for(
        parts, [line(qty=19, internal=date(2026, 11, 13))]
    )  # 19 x 50 = 950 kg = full heat
    assert melt.warnings == []


def test_more_metal_than_the_furnace_can_run_is_a_shortfall_not_a_crash():
    one_heat = [
        replace(r, max_heats_per_shift=1) if r.id == F1 else r for r in resources()
    ]  # one heat a shift, two shifts: two heats a day
    parts = {1: mould_only(1, "GG-1", "GG25", pour=60, cavities=1)}
    _, _, melt = melt_for(parts, [line(qty=1200, internal=date(2026, 11, 13))], res=one_heat)
    short = [h for h in melt.heats if h.furnace_id is None]
    assert short
    assert all("No furnace capacity" in h.warnings[0] for h in short)
    assert melt.summary["shortfall_heats"] == len(short)
    per_day: dict = {}
    for h in melt.heats:
        if h.furnace_id is not None:
            per_day[h.day] = per_day.get(h.day, 0) + 1
    assert max(per_day.values()) <= 2


def test_no_furnace_at_all_flags_every_heat():
    no_furnace = [r for r in resources() if r.kind != "furnace"]
    parts = {1: mould_only()}
    _, _, melt = melt_for(parts, [line(qty=100, internal=date(2026, 11, 13))], res=no_furnace)
    assert melt.heats and all(h.furnace_id is None for h in melt.heats)
    assert {w.kind for w in melt.warnings} == {"no_furnace"}


def test_heats_are_numbered_by_day_and_the_plan_is_deterministic():
    parts, lines = two_grades()
    inp, result, first = melt_for(parts, lines)
    second = plan_melt(inp, result)
    assert [(h.heat_no, h.grade, h.kg, h.furnace_id) for h in first.heats] == [
        (h.heat_no, h.grade, h.kg, h.furnace_id) for h in second.heats
    ]
    assert first.heats[0].heat_no.startswith("H261102-")


def test_the_melt_plan_follows_the_mould_plan():
    parts = {1: mould_only(1, "GG-1", "GG25", pour=60, cavities=2)}
    small = melt_for(parts, [line(qty=300, internal=date(2026, 11, 13))])[2]
    large = melt_for(parts, [line(qty=900, internal=date(2026, 11, 13))])[2]
    assert sum((h.kg for h in large.heats), D(0)) == 3 * sum((h.kg for h in small.heats), D(0))


def test_furnace_days_report_how_much_of_the_capacity_is_used():
    parts = {1: mould_only(1, "GG-1", "GG25", pour=50, cavities=1)}
    _, _, melt = melt_for(parts, [line(qty=40, internal=date(2026, 11, 13))])
    day = melt.days[0]
    assert day.furnace_code == "F1" and day.heats >= 1
    assert 0 < day.used_pct <= 100
