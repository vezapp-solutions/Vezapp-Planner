"""Engine helpers behind the masters: calendar minutes, derived values, sanity checks.
Pure Python, no database. Includes the master-data numbers of the section 7.5 worked example."""

from datetime import date, datetime, time
from decimal import Decimal

import pytest

from planning.calendar import (
    ShiftSpec,
    crosses_midnight,
    heats_per_bucket,
    overlap_minutes,
    shift_instances,
    shift_minutes,
    shift_window,
    usable_minutes,
)
from planning.checks import check_operation, check_part, check_resource
from planning.derive import (
    core_minutes_per_core,
    minutes_per_piece,
    moulding_minutes_per_mould,
    suggested_moulds_per_heat,
)

S1 = ShiftSpec(1, "Shift 1", time(6, 0), time(14, 0), 30)
S2 = ShiftSpec(2, "Shift 2", time(14, 0), time(22, 0), 30)
NIGHT = ShiftSpec(3, "Night", time(22, 0), time(6, 0), 30)


# --- section 7.5 worked example: master-data side -----------------------------------------
def test_worked_example_shift_and_day_minutes():
    assert shift_minutes(S1.start, S1.end, 30) == 450
    assert shift_minutes(S1.start, S1.end, 30) + shift_minutes(S2.start, S2.end, 30) == 900


def test_worked_example_usable_minutes_per_unit_and_for_fettling():
    one_unit_day = usable_minutes(900, units=1, efficiency_pct=85)
    assert one_unit_day.value == Decimal(765)
    assert usable_minutes(900, units=3, efficiency_pct=85).value == Decimal(2295)  # FT, 3 units
    assert "efficiency" in one_unit_day.formula


def test_worked_example_suggested_moulds_per_heat_is_15():
    traced = suggested_moulds_per_heat(heat_kg=1000, melt_loss_pct=5, pour_kg_per_mould=60)
    assert traced.value == 15  # floor(950 / 60) = floor(15.83)
    assert traced.inputs["melt_loss_pct"] == Decimal(5)


def test_worked_example_minutes_per_piece_is_2_5():
    assert minutes_per_piece(75, 15, 2).value == Decimal("2.5")


def test_worked_example_furnace_makes_10_heats_per_day():
    usable = usable_minutes(900, 1, 85).value
    assert heats_per_bucket(usable, Decimal(75)).value == 10  # floor(765 / 75)


# --- calendar ---------------------------------------------------------------------------------
def test_shift_crossing_midnight():
    assert crosses_midnight(NIGHT.start, NIGHT.end)
    assert shift_minutes(NIGHT.start, NIGHT.end, 30) == 450
    start, end = shift_window(date(2026, 11, 2), NIGHT)
    assert start == datetime(2026, 11, 2, 22, 0) and end == datetime(2026, 11, 3, 6, 0)


@pytest.mark.parametrize(
    "start, end, brk", [(time(6, 0), time(6, 0), 0), (time(6, 0), time(7, 0), 60)]
)
def test_impossible_shifts_are_rejected(start, end, brk):
    with pytest.raises(ValueError):
        shift_minutes(start, end, brk)


def test_shift_instances_respect_weekly_off_and_holidays():
    week = {d: [S1, S2] for d in range(6)}  # Monday to Saturday; Sunday off
    holidays = {date(2026, 11, 3): None, date(2026, 11, 4): frozenset({2})}
    days = shift_instances(week, holidays, date(2026, 11, 2), date(2026, 11, 8))
    seen = [(i.day.day, i.shift.id) for i in days]
    assert (3, 1) not in seen and (3, 2) not in seen  # full holiday
    assert (4, 1) in seen and (4, 2) not in seen  # only shift 2 off
    assert all(day != 8 for day, _ in seen)  # Sunday has no shifts
    assert sum(i.minutes for i in days if i.day.day == 2) == 900


def test_downtime_overlap_is_clipped_to_the_shift():
    start, end = shift_window(date(2026, 11, 2), S1)
    down_from, down_to = datetime(2026, 11, 2, 13, 0), datetime(2026, 11, 2, 16, 0)
    assert overlap_minutes(start, end, down_from, down_to) == Decimal(60)
    assert overlap_minutes(start, end, datetime(2026, 11, 3), datetime(2026, 11, 4)) == 0


def test_usable_minutes_never_goes_below_zero():
    assert usable_minutes(450, 1, 100, downtime_minutes=999).value == 0


# --- derived values ---------------------------------------------------------------------------
def test_moulding_time_falls_back_to_line_speed():
    assert moulding_minutes_per_mould(None, 90).value == Decimal(60) / 90
    assert moulding_minutes_per_mould("1.5", 90).value == Decimal("1.5")
    assert moulding_minutes_per_mould(None, None).value is None


def test_core_time_from_rate_or_cycle():
    assert core_minutes_per_core("1.0").value == Decimal("1.0")
    assert core_minutes_per_core(None, cores_per_hour=60).value == 1
    assert core_minutes_per_core(None, cycle_seconds=90, cores_per_shot=3).value == Decimal("0.5")


def test_trace_is_serialisable():
    data = minutes_per_piece(75, 15, 2).as_dict()
    assert data["value"] == 2.5 and data["inputs"]["cavities_per_mould"] == 2


# --- validation and warnings ------------------------------------------------------------------
def levels(issues):
    return {(i.level, i.field) for i in issues}


def test_part_blocks_impossible_values():
    got = levels(
        check_part(
            {"casting_weight_kg": 0, "pouring_weight_per_mould_kg": -1, "cavities_per_mould": 0}
        )
    )
    assert ("error", "casting_weight_kg") in got
    assert ("error", "pouring_weight_per_mould_kg") in got
    assert ("error", "cavities_per_mould") in got


def test_part_warns_when_pour_weight_is_below_cavities_times_casting():
    part = {"casting_weight_kg": 40, "pouring_weight_per_mould_kg": 60, "cavities_per_mould": 2}
    assert ("warning", "pouring_weight_per_mould_kg") in levels(check_part(part))
    part["pouring_weight_per_mould_kg"] = 100
    assert not check_part(part)


def test_resource_requirements_by_kind():
    assert ("error", "heat_kg") in levels(
        check_resource({"kind": "furnace", "units": 1, "efficiency_pct": 100})
    )
    assert ("error", "rate_per_hour") in levels(
        check_resource({"kind": "moulding_line", "units": 1, "efficiency_pct": 100})
    )
    assert not check_resource(
        {
            "kind": "core_machine",
            "units": 1,
            "efficiency_pct": 90,
            "cycle_seconds": 60,
            "cores_per_shot": 2,
        }
    )


def melting_op(**extra):
    return {
        "kind": "melting",
        "code": "melting",
        "enabled": True,
        "time_basis": "per_heat",
        "time_value": 75,
        "extra": extra,
        "resource_count": 1,
    }


PART = {"pouring_weight_per_mould_kg": 60, "casting_weight_kg": 30}


def test_melting_blocks_a_heat_too_small_for_one_mould():
    issues = check_operation(
        melting_op(melt_loss_pct=5, moulds_per_heat=1), PART, [{"heat_kg": 50}]
    )
    assert ("error", "resources") in levels(issues)


def test_melting_warns_on_blank_melt_loss_and_oversized_moulds_per_heat():
    issues = check_operation(melting_op(moulds_per_heat=20), PART, [{"heat_kg": 1000}])
    got = levels(issues)
    assert ("warning", "extra.melt_loss_pct") in got
    assert ("warning", "extra.moulds_per_heat") in got


def test_worked_example_melting_has_no_blocking_issue():
    issues = check_operation(
        melting_op(melt_loss_pct=5, moulds_per_heat=15, cooling_hours=4), PART, [{"heat_kg": 1000}]
    )
    assert not [i for i in issues if i.level == "error"]


def test_cooling_zero_on_heavy_casting_warns():
    heavy = {**PART, "casting_weight_kg": 80}
    got = levels(
        check_operation(
            melting_op(melt_loss_pct=5, moulds_per_heat=15, cooling_hours=0),
            heavy,
            [{"heat_kg": 1000}],
        )
    )
    assert ("warning", "extra.cooling_hours") in got


@pytest.mark.parametrize(
    "op, expected",
    [
        (
            {"kind": "core", "code": "core", "time_basis": "per_core", "time_value": 20},
            ("warning", "time_value"),
        ),
        (
            {"kind": "moulding", "code": "moulding", "time_basis": "per_mould", "time_value": 45},
            ("warning", "time_value"),
        ),
        (
            {"kind": "post", "code": "fettling", "time_basis": "per_piece", "time_value": 200},
            ("warning", "time_value"),
        ),
        (
            {"kind": "post", "code": "knockout", "time_basis": "per_piece", "time_value": 0},
            ("error", "time_value"),
        ),
        (
            {
                "kind": "post",
                "code": "packing",
                "time_basis": "per_batch",
                "time_value": 2,
                "batch_size": 0,
            },
            ("error", "batch_size"),
        ),
        (
            {"kind": "core", "code": "core", "time_basis": "per_piece", "time_value": 1},
            ("error", "time_basis"),
        ),
        (
            {"kind": "post", "code": "machining", "time_basis": "per_piece", "outsourced": True},
            ("error", "lead_days"),
        ),
    ],
)
def test_operation_ranges_and_blocks(op, expected):
    op = {"enabled": True, "extra": {}, "resource_count": 1, **op}
    assert expected in levels(check_operation(op, PART, []))


def test_post_operation_without_work_centre_is_flagged_as_not_modelled():
    op = {
        "kind": "post",
        "code": "knockout",
        "enabled": True,
        "time_basis": "per_piece",
        "time_value": 0.5,
        "resource_count": 0,
    }
    assert ("info", "resources") in levels(check_operation(op, PART, []))


def test_disabled_operations_are_not_checked():
    op = {
        "kind": "post",
        "code": "knockout",
        "enabled": False,
        "time_basis": "per_piece",
        "time_value": -5,
    }
    assert check_operation(op, PART, []) == []
