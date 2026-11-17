"""Furnace (melt) planning that follows the mould plan. Pure: no Django, no database.

For every working day the metal the moulds need is worked out per material grade, and the grade is
poured in heats: one heat is one grade, never mixed, and a heat takes whole moulds up to what the
furnace can tap (its heat size less the melt loss). Heats are given to furnaces and shifts within each
furnace's capacity (heats per shift, heat minutes, shifts, holidays, downtime). The result lists the
heats, how full each is, and warnings for under-filled heats and for heats that no furnace can take.

The melt plan is a function of the mould plan, so when the moulds change it is recalculated and the
two cannot drift apart.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .ledger import Ledger
from .model import PlanInput, PlanResult, ResourceSpec
from .timeline import Timeline

MIN_HEAT_FILL_PCT = Decimal(70)
ZERO = Decimal(0)


@dataclass
class HeatPour:
    line_id: int
    part_id: int
    part_number: str
    moulds: int
    kg: Decimal


@dataclass
class Heat:
    day: date
    slot_idx: int | None  # the shift the heat runs in; None when no furnace has room
    shift_name: str
    furnace_id: int | None
    furnace_code: str
    heat_no: str
    grade: str
    kg: Decimal  # metal poured from this heat
    capacity_kg: (
        Decimal  # what the furnace can tap in one heat (after melt loss); 0 with no furnace
    )
    charge_kg: Decimal  # metal to melt, which covers the melt loss
    pours: list[HeatPour] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def fill_pct(self) -> Decimal:
        return (self.kg / self.capacity_kg * 100) if self.capacity_kg else ZERO


@dataclass
class MeltDay:
    day: date
    furnace_id: int
    furnace_code: str
    heats: int
    kg: Decimal
    capacity_heats: int
    used_pct: Decimal  # heats used of the heats the furnace could run that day


@dataclass
class MeltWarning:
    day: date
    kind: str  # under_filled | shortfall | heavy_mould | no_furnace
    text: str
    grade: str = ""


@dataclass
class MeltPlan:
    heats: list[Heat]
    days: list[MeltDay]
    warnings: list[MeltWarning]
    summary: dict[str, int | str]


@dataclass
class _Item:
    line_id: int
    part_id: int
    part_number: str
    grade: str
    moulds: int
    pour_kg: Decimal
    due: date
    loss_pct: Decimal


@dataclass
class _Bay:
    slot_idx: int
    furnace: ResourceSpec
    usable_kg: Decimal
    free: int


def _loss(inp: PlanInput, part) -> Decimal:
    if part.melt_loss_pct is not None:
        return part.melt_loss_pct
    melting = next((o for o in part.ops if o.kind == "melting"), None)
    if melting is not None and melting.extra.get("melt_loss_pct") is not None:
        return Decimal(str(melting.extra["melt_loss_pct"]))
    return inp.settings.default_melt_loss_pct


def _pours_by_day(inp: PlanInput, result: PlanResult) -> dict[date, list[_Item]]:
    """The moulds made on each day, from the moulding allocations of the mould plan."""
    slots = {s.idx: s for s in result.slots}
    lines = {ln.id: ln for ln in inp.lines}
    moulding_code = {
        pid: next((o.code for o in p.ops if o.kind == "moulding"), None)
        for pid, p in inp.parts.items()
    }
    made: dict[tuple[date, int], Decimal] = defaultdict(Decimal)
    for a in result.allocations:
        line = lines.get(a.line_id)
        if line is None or moulding_code.get(line.part_id) != a.op_code:
            continue
        made[(slots[a.slot_idx].day, a.line_id)] += a.qty
    out: dict[date, list[_Item]] = defaultdict(list)
    for (day, line_id), qty in sorted(made.items()):
        line = lines[line_id]
        part = inp.parts[line.part_id]
        moulds = int(math.floor(qty + Decimal("0.0001")))
        if moulds <= 0:
            continue
        out[day].append(
            _Item(
                line_id,
                part.id,
                part.part_number,
                part.grade_name or "No grade",
                moulds,
                part.pouring_weight_per_mould_kg,
                line.internal_date,
                _loss(inp, part),
            )
        )
    return out


def plan_melt(
    inp: PlanInput, result: PlanResult, min_fill_pct: Decimal = MIN_HEAT_FILL_PCT
) -> MeltPlan:
    """Plan the heats for the moulds in `result`. Deterministic for the same input."""
    timeline = Timeline(result.slots)
    furnaces = sorted(
        (
            r
            for r in inp.resources
            if r.kind == "furnace" and r.active and r.heat_kg and r.heat_minutes
        ),
        key=lambda r: r.code,
    )
    ledger = (
        Ledger(timeline, furnaces, inp.extra_shifts, inp.overtime)
        if furnaces and len(timeline)
        else None
    )
    slots = {s.idx: s for s in result.slots}
    heats: list[Heat] = []
    warnings: list[MeltWarning] = []
    days: dict[tuple[date, int], dict] = {}

    for day, items in sorted(_pours_by_day(inp, result).items()):
        # the furnace room of the day, by shift
        bays: list[_Bay] = []
        if ledger is not None:
            for idx in timeline.by_day.get(day, []):
                for f in furnaces:
                    cap_minutes = ledger.cap[f.id][idx]
                    n = int(math.floor(cap_minutes / f.heat_minutes))
                    if f.max_heats_per_shift:
                        n = min(n, f.max_heats_per_shift)
                    if n <= 0:
                        continue
                    loss = max(
                        (i.loss_pct for i in items), default=inp.settings.default_melt_loss_pct
                    )
                    bays.append(_Bay(idx, f, f.heat_kg * (1 - loss / 100), n))
                    days.setdefault((day, f.id), {"code": f.code, "cap": 0, "used": 0, "kg": ZERO})
                    days[(day, f.id)]["cap"] += n
        bays.sort(key=lambda b: (b.slot_idx, -b.usable_kg, b.furnace.code))

        by_grade: dict[str, list[_Item]] = defaultdict(list)
        for item in items:
            by_grade[item.grade].append(item)
        order = sorted(by_grade, key=lambda g: (min(i.due for i in by_grade[g]), g))
        count = 0
        for grade in order:
            todo = sorted(by_grade[grade], key=lambda i: (i.due, i.part_number, i.line_id))
            left = {i.line_id: i.moulds for i in todo}
            while any(left.values()):
                bay = next((b for b in bays if b.free > 0), None)
                capacity = (
                    bay.usable_kg
                    if bay
                    else (
                        max((b.usable_kg for b in bays), default=ZERO)
                        or _ref_capacity(furnaces, todo)
                    )
                )
                count += 1
                heat = Heat(
                    day,
                    bay.slot_idx if bay else None,
                    slots[bay.slot_idx].shift_name if bay else "",
                    bay.furnace.id if bay else None,
                    bay.furnace.code if bay else "",
                    f"H{day:%y%m%d}-{count:02d}",
                    grade,
                    ZERO,
                    capacity,
                    ZERO,
                )
                filled = ZERO
                for item in todo:
                    if not left[item.line_id]:
                        continue
                    room = capacity - filled
                    fits = (
                        int(math.floor(room / item.pour_kg))
                        if item.pour_kg > 0
                        else left[item.line_id]
                    )
                    if fits <= 0 and not heat.pours:
                        fits = 1  # a mould heavier than the heat still has to be poured somewhere
                        heat.warnings.append(
                            f"{item.part_number}: one mould needs {item.pour_kg:.1f} kg, more than the heat size"
                        )
                        warnings.append(MeltWarning(day, "heavy_mould", heat.warnings[-1], grade))
                    take = min(left[item.line_id], max(fits, 0))
                    if take <= 0:
                        continue
                    left[item.line_id] -= take
                    kg = item.pour_kg * take
                    filled += kg
                    heat.pours.append(
                        HeatPour(item.line_id, item.part_id, item.part_number, take, kg)
                    )
                heat.kg = filled
                loss = max((i.loss_pct for i in todo), default=ZERO)
                heat.charge_kg = filled / (1 - loss / 100) if loss < 100 else filled
                if bay:
                    bay.free -= 1
                    entry = days[(day, bay.furnace.id)]
                    entry["used"] += 1
                    entry["kg"] += filled
                    if heat.capacity_kg and heat.fill_pct < min_fill_pct:
                        text = f"Under-filled heat: {grade} at {heat.fill_pct:.0f}% of {heat.capacity_kg:.0f} kg"
                        heat.warnings.append(text)
                        warnings.append(MeltWarning(day, "under_filled", text, grade))
                else:
                    text = (
                        f"No furnace capacity for a {grade} heat ({filled:.0f} kg)"
                        if furnaces
                        else f"No furnace in the machine master for a {grade} heat ({filled:.0f} kg)"
                    )
                    heat.warnings.append(text)
                    warnings.append(
                        MeltWarning(day, "shortfall" if furnaces else "no_furnace", text, grade)
                    )
                heats.append(heat)

    melt_days = [
        MeltDay(
            day,
            fid,
            v["code"],
            v["used"],
            v["kg"],
            v["cap"],
            Decimal(v["used"]) * 100 / v["cap"] if v["cap"] else ZERO,
        )
        for (day, fid), v in sorted(days.items(), key=lambda kv: (kv[0][0], kv[1]["code"]))
        if v["used"] or v["cap"]
    ]
    summary = {
        "heats": len(heats),
        "under_filled": sum(1 for w in warnings if w.kind == "under_filled"),
        "shortfall_heats": sum(1 for h in heats if h.furnace_id is None),
        "grades": len({h.grade for h in heats}),
    }
    return MeltPlan(heats, melt_days, warnings, summary)


def _ref_capacity(furnaces: list[ResourceSpec], items: list[_Item]) -> Decimal:
    """A heat size to use when no furnace has room, so the missing heats can still be counted."""
    if furnaces:
        return max(f.heat_kg for f in furnaces)
    heaviest = max((i.pour_kg for i in items), default=ZERO)
    return max(Decimal(1000), heaviest)
