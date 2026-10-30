"""The facts the rules read and the cards they write. Plain data, JSON-friendly on the way out."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .rules import IMPACT_CAP, SEVERITY_WEIGHT


@dataclass(frozen=True)
class Card:
    key: str  # stable across runs, so a card can be compared with its earlier self
    type: str
    severity: str  # critical | warning | info
    title: str
    message: str  # one plain-English line
    numbers: dict[str, Any] = field(default_factory=dict)
    entities: dict[str, Any] = field(default_factory=dict)
    action: str = ""
    why: tuple[str, ...] = ()  # the calculation trace
    impact: float = 0.0  # 0 to 10

    @property
    def rank(self) -> float:
        return SEVERITY_WEIGHT[self.severity] * (1 + min(max(self.impact, 0.0), IMPACT_CAP))

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "type": self.type, "severity": self.severity, "title": self.title,
            "message": self.message, "numbers": self.numbers, "entities": self.entities,
            "action": self.action, "why": list(self.why), "impact": round(self.impact, 2),
            "rank": round(self.rank, 2),
        }  # fmt: skip


def scaled(value: float, reference: float) -> float:
    """Impact on a 0 to 10 scale: `reference` or more is the maximum."""
    if reference <= 0:
        return 0.0
    return min(IMPACT_CAP, IMPACT_CAP * max(value, 0.0) / reference)


@dataclass(frozen=True)
class LineFact:
    """One planned dispatch line with its planned outcome."""

    line_id: int
    customer_code: str
    customer_name: str
    part_id: int
    part_number: str
    part_name: str
    grade: str
    qty: int
    internal_date: date
    status: str  # on_track | tight | at_risk | unscheduled
    est_date: date | None
    slack_working_days: int | None
    holding: str  # the operation holding it up, by name; blank when none
    holding_text: str
    tonnes: float  # casting weight × quantity
    price: float | None  # selling price per piece


@dataclass(frozen=True)
class DayBottleneck:
    day: date
    resource_code: str | None
    utilisation: float


@dataclass(frozen=True)
class LoadRow:
    """Load, capacity and required minutes of one resource in one shift."""

    resource_id: int
    code: str
    name: str
    day: date
    load: float
    capacity: float
    required: float


@dataclass(frozen=True)
class MeltRow:
    day: date
    grade: str
    kg: float


@dataclass(frozen=True)
class FurnaceDay:
    code: str
    day: date
    load: float
    capacity: float


@dataclass(frozen=True)
class BalanceCandidate:
    """A route step allowed only on an overloaded resource, with a quieter alternative of its kind."""

    part_id: int
    part_number: str
    op_code: str
    op_name: str
    from_id: int
    from_code: str
    from_util: float
    to_id: int
    to_code: str
    to_util: float
    pieces: int


@dataclass(frozen=True)
class DispatchRow:
    """A line that has a recorded actual dispatch date."""

    line_id: int
    customer_code: str
    customer_name: str
    part_number: str
    internal_date: date
    actual_date: date
    qty: int

    @property
    def delay_days(self) -> int:
        return max(0, (self.actual_date - self.internal_date).days)

    @property
    def on_time(self) -> bool:
        return self.actual_date <= self.internal_date


@dataclass(frozen=True)
class HealthItem:
    kind: str
    subject: str
    detail: str
    why: str
    severity: str  # error | warning | info
    link: str = ""  # where to fix it
    lines_affected: int = 0
