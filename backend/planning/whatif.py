"""What-if: edit a copy of the plan's input, plan it again, and diff the two results.

Nothing here touches real data. `apply_changes` returns a new PlanInput; the originals are never
changed, so the baseline and the scenario can be planned from the same starting point.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .kpis import peak_utilisation
from .model import ExtraShift, LineInput, Overtime, PlanInput, PlanResult
from .timeline import Timeline


@dataclass(frozen=True)
class BlockResource:
    resource_id: int
    start: datetime
    end: datetime


@dataclass(frozen=True)
class ChangeQty:
    line_id: int
    qty: int


@dataclass(frozen=True)
class ChangeDate:
    line_id: int
    internal_date: date


@dataclass(frozen=True)
class AllowResource:
    """Let one more resource do a step of a part's route (used to test a load-balancing idea)."""

    part_id: int
    op_code: str
    resource_id: int


Change = BlockResource | ChangeQty | ChangeDate | ExtraShift | Overtime | AllowResource


def apply_changes(inp: PlanInput, changes: Sequence[Change]) -> PlanInput:
    """A copy of the input with the changes made."""
    resources = {r.id: r for r in inp.resources}
    lines = {ln.id: ln for ln in inp.lines}
    parts = dict(inp.parts)
    extra_shifts = list(inp.extra_shifts)
    overtime = list(inp.overtime)

    for change in changes:
        if isinstance(change, BlockResource):
            r = resources.get(change.resource_id)
            if r is not None:
                resources[r.id] = replace(r, downtimes=(*r.downtimes, (change.start, change.end)))
        elif isinstance(change, ChangeQty):
            if change.line_id in lines:
                lines[change.line_id] = replace(lines[change.line_id], qty=change.qty)
        elif isinstance(change, ChangeDate):
            if change.line_id in lines:
                lines[change.line_id] = replace(
                    lines[change.line_id], internal_date=change.internal_date
                )
        elif isinstance(change, ExtraShift):
            extra_shifts.append(change)
        elif isinstance(change, Overtime):
            overtime.append(change)
        elif isinstance(change, AllowResource):
            part = parts.get(change.part_id)
            if part is not None:
                parts[part.id] = replace(
                    part,
                    ops=tuple(
                        replace(
                            op, resource_ids=tuple(sorted({*op.resource_ids, change.resource_id}))
                        )
                        if op.code == change.op_code
                        else op
                        for op in part.ops
                    ),
                )

    return replace(
        inp,
        parts=parts,
        resources=[resources[r.id] for r in inp.resources],
        lines=[lines[ln.id] for ln in inp.lines],
        extra_shifts=tuple(extra_shifts),
        overtime=tuple(overtime),
    )


# --- the diff --------------------------------------------------------------------------------------
@dataclass
class LineDiff:
    line_id: int
    status_before: str
    status_after: str
    est_before: date | None
    est_after: date | None
    slack_before: int | None
    slack_after: int | None
    moved_working_days: int | None  # positive = later
    holding_after: str | None
    holding_text_after: str
    tags: list[str]
    internal_date_before: date
    internal_date_after: date
    qty_before: int
    qty_after: int

    def as_dict(self) -> dict[str, Any]:
        out = {k: getattr(self, k) for k in self.__dataclass_fields__}
        for key in ("est_before", "est_after", "internal_date_before", "internal_date_after"):
            out[key] = out[key].isoformat() if out[key] else None
        return out


@dataclass
class Diff:
    lines: list[LineDiff] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    status_before: dict[str, int] = field(default_factory=dict)
    status_after: dict[str, int] = field(default_factory=dict)
    bottleneck_before: int | None = None
    bottleneck_after: int | None = None
    day_bottlenecks: list[dict[str, Any]] = field(
        default_factory=list
    )  # days whose busiest resource differs
    peak_utilisation: dict[int, tuple[float, float]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "lines": [ln.as_dict() for ln in self.lines],
            "counts": self.counts,
            "status_before": self.status_before,
            "status_after": self.status_after,
            "bottleneck_before": self.bottleneck_before,
            "bottleneck_after": self.bottleneck_after,
            "day_bottlenecks": self.day_bottlenecks,
            "peak_utilisation": {str(k): list(v) for k, v in self.peak_utilisation.items()},
        }


BAD = {"at_risk", "unscheduled"}


def _status_counts(result: PlanResult) -> dict[str, int]:
    out: dict[str, int] = {}
    for ln in result.lines:
        out[ln.status] = out.get(ln.status, 0) + 1
    return out


def diff_results(
    before: PlanResult,
    after: PlanResult,
    lines_before: Mapping[int, LineInput],
    lines_after: Mapping[int, LineInput],
) -> Diff:
    """What a scenario changes: every line whose date, status, slack, quantity or due date differs."""
    timeline = Timeline(after.slots) if after.slots else None
    prev = {ln.line_id: ln for ln in before.lines}
    diff = Diff()
    counts = {"later": 0, "earlier": 0, "newly_at_risk": 0, "recovered": 0, "changed": 0}

    for new in after.lines:
        old = prev.get(new.line_id)
        if old is None:
            continue
        lb, la = lines_before[new.line_id], lines_after[new.line_id]
        same = (
            old.status == new.status
            and old.est_dispatch == new.est_dispatch
            and old.slack_working_days == new.slack_working_days
            and lb.qty == la.qty
            and lb.internal_date == la.internal_date
        )
        if same:
            continue

        tags: list[str] = []
        moved = None
        if old.est_dispatch and new.est_dispatch and timeline is not None:
            moved = timeline.working_days_between(old.est_dispatch, new.est_dispatch)
            if new.est_dispatch > old.est_dispatch:
                tags.append("later")
            elif new.est_dispatch < old.est_dispatch:
                tags.append("earlier")
        if new.status in BAD and old.status not in BAD:
            tags.append("newly_at_risk")
        if old.status in BAD and new.status not in BAD:
            tags.append("recovered")
        if not tags:
            tags.append("changed")
        for tag in tags:
            counts[tag] += 1
        diff.lines.append(
            LineDiff(
                new.line_id, old.status, new.status, old.est_dispatch, new.est_dispatch,
                old.slack_working_days, new.slack_working_days, moved, new.holding_op,
                new.holding_text, tags, lb.internal_date, la.internal_date, lb.qty, la.qty,
            )
        )  # fmt: skip

    order = {"newly_at_risk": 0, "later": 1, "recovered": 2, "earlier": 3, "changed": 4}
    diff.lines.sort(key=lambda d: (order[d.tags[0]], d.est_after or date.max, d.line_id))
    diff.counts = {**counts, "total": len(diff.lines)}
    diff.status_before, diff.status_after = _status_counts(before), _status_counts(after)
    diff.bottleneck_before, diff.bottleneck_after = (
        before.bottleneck_overall,
        after.bottleneck_overall,
    )

    b_days = {b.day: b.resource_id for b in before.bottlenecks}
    a_days = {b.day: b.resource_id for b in after.bottlenecks}
    for day in sorted(set(b_days) | set(a_days)):
        if b_days.get(day) != a_days.get(day):
            diff.day_bottlenecks.append(
                {"date": day.isoformat(), "before": b_days.get(day), "after": a_days.get(day)}
            )

    peaks_before = peak_utilisation(Timeline(before.slots), before.loads) if before.slots else {}
    peaks_after = peak_utilisation(timeline, after.loads) if timeline else {}
    zero = Decimal(0)
    for rid in sorted(set(peaks_before) | set(peaks_after)):
        diff.peak_utilisation[rid] = (
            round(float(peaks_before.get(rid, zero)), 4),
            round(float(peaks_after.get(rid, zero)), 4),
        )
    return diff
