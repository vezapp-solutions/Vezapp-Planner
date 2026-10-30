"""Builders for engine tests: the PROMPT.md section 7.5 plant, and small variations of it."""

from datetime import date, datetime, time
from decimal import Decimal

from planning.calendar import ShiftSpec
from planning.model import (
    LineInput,
    OpSpec,
    PartSpec,
    PlanInput,
    PlanSettings,
    ResourceSpec,
)

S1 = ShiftSpec(1, "Shift 1", time(6, 0), time(14, 0), 30)  # 450 net minutes
S2 = ShiftSpec(2, "Shift 2", time(14, 0), time(22, 0), 30)
MONDAY = date(2026, 11, 2)

CM1, LINE_A, F1, KO, FT = 1, 2, 3, 4, 5
D = Decimal


def week(*shifts, days=range(6)):
    return {d: list(shifts) for d in days}  # Monday to Saturday; Sunday off


def resources(eff=85):
    e = D(eff)
    return [
        ResourceSpec(CM1, "CM1", "core_machine", efficiency_pct=e, rate_per_hour=D(60)),
        ResourceSpec(LINE_A, "LINE-A", "moulding_line", efficiency_pct=e, rate_per_hour=D(40)),
        ResourceSpec(F1, "F1", "furnace", efficiency_pct=e, heat_kg=D(1000), heat_minutes=D(75)),
        ResourceSpec(KO, "KO", "work_centre", efficiency_pct=e),
        ResourceSpec(FT, "FT", "work_centre", units=3, efficiency_pct=e),
    ]


def h120(
    pid=1,
    number="H-120",
    grade=10,
    pour=60,
    cavities=2,
    cores=2,
    rejection=5,
    cooling=4,
    mph=15,
    ops=None,
    **op_over,
):
    """Part H-120 of section 7.5: core 1.0, moulding 1.5, melting 75/heat, knockout 0.5, fettling 3."""
    default = [
        OpSpec("core", "Core", "core", 10, D(1), "per_core", resource_ids=(CM1,), extra={"cores_per_mould": cores}),
        OpSpec("moulding", "Moulding", "moulding", 20, D("1.5"), "per_mould", resource_ids=(LINE_A,)),
        OpSpec("melting", "Melting and pouring", "melting", 30, D(75), "per_heat", resource_ids=(F1,),
               extra={"moulds_per_heat": mph, "melt_loss_pct": 5, "cooling_hours": cooling}),
        OpSpec("knockout", "Knockout", "post", 40, D("0.5"), "per_piece", bucket="shift", resource_ids=(KO,)),
        OpSpec("fettling", "Fettling", "post", 50, D(3), "per_piece", bucket="shift", resource_ids=(FT,)),
    ]  # fmt: skip
    return PartSpec(
        pid, number, grade, "GG25", D(25), D(pour), cavities, cores, D(rejection),
        tuple(ops if ops is not None else default), rejection_seq=50,
    )  # fmt: skip


def line(lid=1, part=1, qty=600, internal=date(2026, 11, 20), priority="B", order=None):
    return LineInput(lid, part, qty, internal, 1, priority, order if order is not None else lid)


def plan_input(
    lines=None, parts=None, res=None, shifts=(S1, S2), settings=None, holidays=None, wk=None
):
    return PlanInput(
        settings or PlanSettings(plan_from=MONDAY),
        wk if wk is not None else week(*shifts),
        holidays or {},
        res if res is not None else resources(),
        parts if parts is not None else {1: h120()},
        lines if lines is not None else [line()],
    )


def at(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm)
