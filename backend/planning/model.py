"""Plain data the planning engine reads and writes. No Django, no database.

An adapter (apps/plans/inputs.py) turns masters and schedule lines into a PlanInput; the engine
returns a PlanResult; another adapter stores it. Phase 4 what-if edits a PlanInput and diffs two
results, so everything here is immutable or a simple dataclass.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from .calendar import ShiftSpec
from .trace import Traced

FlowMode = Literal["progressive", "whole_lot"]
LineStatus = Literal["on_track", "tight", "at_risk", "unscheduled"]
PRIORITY_RANK = {"A": 0, "B": 1, "C": 2}


@dataclass(frozen=True)
class ResourceSpec:
    id: int
    code: str
    kind: str  # core_machine | moulding_line | furnace | work_centre
    units: int = 1
    efficiency_pct: Decimal = Decimal(100)
    active: bool = True
    shift_ids: frozenset[int] = frozenset()  # empty = works every company shift
    downtimes: tuple[tuple[datetime, datetime], ...] = ()
    rate_per_hour: Decimal | None = None
    cycle_seconds: Decimal | None = None
    cores_per_shot: int | None = None
    heat_kg: Decimal | None = None
    heat_minutes: Decimal | None = None
    max_heats_per_shift: int | None = None
    type_id: int = 0  # the resource type (VMC, CNC, HMC...), so a step can time each type


@dataclass(frozen=True)
class OpSpec:
    """One enabled step of a part's route.

    `code` identifies the step and is unique within a part: the operation type's code for the
    first (or only) step, and `type~step` for further steps of a multi-step operation such as
    machining (`machining~20`). Use `type_of` for the operation type behind a code.
    """

    code: str
    name: str
    kind: str  # core | moulding | melting | post
    sequence: int
    time_value: Decimal | None = None
    time_basis: str = "per_piece"
    batch_size: int | None = None
    bucket: str = "shift"  # shift | day
    lag_hours: Decimal = Decimal(0)
    outsourced: bool = False
    lead_days: int | None = None
    resource_ids: tuple[int, ...] = ()
    extra: Mapping[str, float] = field(default_factory=dict)
    step: int = 0
    setup_minutes: Decimal = Decimal(0)  # per lot, on each machine used for it
    time_by_type: Mapping[int, Decimal] = field(
        default_factory=dict
    )  # minutes per unit by resource type


STEP_SEPARATOR = "~"


def type_of(code: str) -> str:
    """The operation type behind a step code: `machining~20` is machining."""
    return code.split(STEP_SEPARATOR, 1)[0]


def step_code(type_code: str, step: int) -> str:
    return type_code if not step else f"{type_code}{STEP_SEPARATOR}{step}"


@dataclass(frozen=True)
class PartSpec:
    id: int
    part_number: str
    grade_id: int | None
    grade_name: str
    casting_weight_kg: Decimal
    pouring_weight_per_mould_kg: Decimal
    cavities_per_mould: int
    cores_per_mould: int
    rejection_pct: Decimal
    ops: tuple[OpSpec, ...]  # enabled operations only, in sequence order
    rejection_seq: int = 50  # operations up to this sequence use the pieces-to-pour quantity


@dataclass(frozen=True)
class LineInput:
    id: int
    part_id: int
    qty: int
    internal_date: date
    customer_id: int = 0
    priority: str = "B"
    entry_order: int = 0


@dataclass(frozen=True)
class PlanSettings:
    plan_from: date
    horizon_days: int = 30
    flow_mode: FlowMode = "progressive"
    pour_same_shift: bool = True
    default_melt_loss_pct: Decimal = Decimal(0)
    max_window_days: int = 400


@dataclass(frozen=True)
class ExtraShift:
    """A one-off shift on each day of a range, for named resources (None: every resource that
    works all shifts). It may fall on a weekly off or a holiday."""

    day_from: date
    day_to: date
    shift: ShiftSpec
    resource_ids: frozenset[int] | None = None


@dataclass(frozen=True)
class Overtime:
    """Extra working minutes in the shifts of a date range (one shift, or all), for named
    resources (None: all). Adds capacity of minutes × units × efficiency to each shift."""

    day_from: date
    day_to: date
    minutes: int
    shift_id: int | None = None
    resource_ids: frozenset[int] | None = None


@dataclass
class PlanInput:
    settings: PlanSettings
    week: Mapping[int, Sequence[ShiftSpec]]
    holidays: Mapping[date, frozenset[int] | None]
    resources: Sequence[ResourceSpec]
    parts: Mapping[int, PartSpec]
    lines: Sequence[LineInput]
    extra_shifts: Sequence[ExtraShift] = ()
    overtime: Sequence[Overtime] = ()


# --- results -------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Slot:
    idx: int
    day: date
    shift_id: int
    shift_name: str
    start: datetime
    end: datetime
    minutes: int  # net working minutes of the shift


@dataclass
class Requirement:
    """What one schedule line asks of the plant, section 7.1. Every number carries its formula."""

    line_id: int
    pieces_to_pour: int
    moulds: int
    cores: int
    metal_kg: Decimal
    moulds_per_heat: int | None
    heats: int | None
    # per operation code: total minutes (and the unit it is counted in)
    minutes: dict[str, Decimal]
    units: dict[str, Decimal]
    traces: dict[str, Traced]


@dataclass
class OpResult:
    code: str
    name: str
    kind: str
    sequence: int
    minutes: Decimal
    units: Decimal
    ready_at: datetime | None = None
    start_at: datetime | None = None
    finish_at: datetime | None = None
    latest_start: datetime | None = None
    latest_finish: datetime | None = None
    resource_ids: tuple[int, ...] = ()
    capacity_modelled: bool = True
    outsourced: bool = False
    complete: bool = True
    delay_days: int | None = None  # working days after the latest finish (negative = early)
    wait_hours: Decimal | None = None  # average time the work waited for capacity once it was ready


@dataclass
class Allocation:
    line_id: int
    op_code: str
    resource_id: int | None  # None for unconstrained or outsourced steps
    slot_idx: int
    minutes: Decimal  # all machine minutes, setup included
    qty: Decimal  # cores, moulds, pieces or batches, whichever the step counts
    setup: Decimal = Decimal(0)  # the part of `minutes` spent setting the machine up


@dataclass
class LineResult:
    line_id: int
    status: LineStatus
    est_dispatch: date | None
    finish_at: datetime | None
    slack_working_days: int | None
    holding_op: str | None
    holding_text: str
    requirement: Requirement | None
    ops: list[OpResult]
    notes: list[str]


@dataclass
class LoadCell:
    load: Decimal = Decimal(0)
    capacity: Decimal = Decimal(0)
    required: Decimal = Decimal(0)


@dataclass
class DayBottleneck:
    day: date
    resource_id: int | None
    utilisation: Decimal
    load: Decimal
    capacity: Decimal


@dataclass
class PlanResult:
    slots: list[Slot]
    lines: list[LineResult]
    allocations: list[Allocation]
    loads: dict[tuple[int, int], LoadCell]
    bottlenecks: list[DayBottleneck]
    bottleneck_overall: int | None
    summary: dict[str, Any]
