"""Forward pass: finite-capacity scheduling of one schedule line at a time.

Every operation consumes a *supply curve*: the cumulative share of the lot released by the
previous step, and when. In progressive mode each upstream shift releases its share; in whole_lot
mode the curve collapses to one step at the end. Both use the same allocator.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from .explode import op_of, resources_of, unit_minutes
from .ledger import EPS, ZERO, Ledger, window_fraction
from .model import (
    Allocation,
    LineInput,
    OpResult,
    OpSpec,
    PartSpec,
    PlanSettings,
    Requirement,
    ResourceSpec,
)
from .timeline import Timeline

ONE = Decimal(1)


@dataclass
class Curve:
    """Cumulative output of a step: (time the share is released, cumulative fraction of the lot)."""

    points: list[tuple[datetime, Decimal]]

    @property
    def finish(self) -> datetime:
        return self.points[-1][0]

    def collapsed(self) -> "Curve":
        return Curve([(self.finish, ONE)])

    def fraction_at(self, moment: datetime) -> Decimal:
        done = ZERO
        for t, f in self.points:
            if t <= moment:
                done = f
            else:
                break
        return done


@dataclass
class StepOut:
    curve: Curve
    ready: datetime | None
    start: datetime | None
    finish: datetime | None
    complete: bool = True
    note: str = ""
    wait_hours: Decimal = ZERO
    limiter: str = ""  # what held moulding back most: furnace, line or cores
    minutes: Decimal = ZERO  # machine minutes really allocated, setup included


@dataclass
class LineSchedule:
    ops: list[OpResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    complete: bool = True
    failed_op: str | None = None


def _increments(
    curve: Curve, lag_hours: Decimal, total: Decimal, whole_lot: bool
) -> list[tuple[datetime, Decimal]]:
    """Turn a supply curve into (ready time, units) pieces; the last takes the rounding remainder."""
    if whole_lot:
        curve = curve.collapsed()
    lag = timedelta(seconds=float(lag_hours * 3600))
    out: list[tuple[datetime, Decimal]] = []
    previous = ZERO
    given = ZERO
    for t, f in curve.points:
        units = total * (f - previous)
        previous = f
        if units > 0:
            out.append((t + lag, units))
            given += units
    if out and given != total:
        t, u = out[-1]
        out[-1] = (t, u + (total - given))
    return out


class Scheduler:
    def __init__(
        self,
        timeline: Timeline,
        ledger: Ledger,
        settings: PlanSettings,
        resources: dict[int, ResourceSpec],
    ):
        self.timeline = timeline
        self.ledger = ledger
        self.settings = settings
        self.res = resources
        self.alloc: dict[tuple[int, str, int | None, int], list[Decimal]] = {}
        self.whole_lot = settings.flow_mode == "whole_lot"
        self.plan_start = (
            timeline.slots[0].start
            if len(timeline)
            else datetime.combine(settings.plan_from, datetime.min.time())
        )

    # --- bookkeeping --------------------------------------------------------------------------------
    def _record(
        self,
        line_id: int,
        code: str,
        rid: int | None,
        idx: int,
        minutes: Decimal,
        qty: Decimal,
        setup: Decimal = ZERO,
    ) -> None:
        cell = self.alloc.setdefault((line_id, code, rid, idx), [ZERO, ZERO, ZERO])
        cell[0] += minutes + setup
        cell[1] += qty
        cell[2] += setup

    def allocations(self) -> list[Allocation]:
        return [
            Allocation(line, code, rid, idx, v[0], v[1], v[2])
            for (line, code, rid, idx), v in sorted(
                self.alloc.items(), key=lambda kv: (kv[0][3], kv[0][0], kv[0][1], kv[0][2] or 0)
            )
        ]

    def _release_time(self, idx: int, bucket: str) -> datetime:
        slot = self.timeline.slots[idx]
        return self.timeline.day_end(slot.day) if bucket == "day" else slot.end

    def _curve(
        self, per_slot: dict[int, Decimal], total: Decimal, bucket: str, fallback: datetime
    ) -> Curve:
        if not per_slot or total <= 0:
            return Curve([(fallback, ONE)])
        points: dict[datetime, Decimal] = {}
        running = ZERO
        for idx in sorted(per_slot):
            running += per_slot[idx]
            points[self._release_time(idx, bucket)] = min(ONE, running / total)
        ordered = sorted(points.items())
        ordered[-1] = (ordered[-1][0], ONE)
        return Curve(ordered)

    # --- generic allocation of an operation ---------------------------------------------------------
    def allocate(
        self,
        line_id: int,
        op: OpSpec,
        units_total: Decimal,
        release: list[tuple[datetime, Decimal]],
    ) -> StepOut:
        resources = resources_of(op, self.res)
        constrained = bool(resources)
        if constrained and release and all(unit_minutes(op, r) is None for r in resources):
            return StepOut(
                Curve([(self.plan_start, ONE)]),
                None,
                None,
                None,
                False,
                f"{op.name} has no time entered and no rated speed.",
            )
        n = len(self.timeline)
        per_slot: dict[int, Decimal] = {}
        start: datetime | None = None
        finish: datetime | None = None
        ready_first = release[0][0] if release else self.plan_start
        complete, note = True, ""
        wait_total = ZERO
        minutes_total = ZERO
        setup_each = op.setup_minutes if constrained else ZERO
        setup_paid: dict[int, Decimal] = {}  # setup minutes already spent, by machine, for this lot

        for ready, units in release:
            remaining = units
            idx = self.timeline.first_slot_after(ready)
            if constrained:
                idx = self.ledger.earliest_open([r.id for r in resources], idx)
            while remaining > EPS and idx < n:
                slot = self.timeline.slots[idx]
                if constrained:
                    options = []
                    for r in resources:
                        a = self.ledger.avail(r.id, idx, ready)
                        mpu = unit_minutes(op, r)
                        if a > EPS and mpu:
                            need = max(ZERO, setup_each - setup_paid.get(r.id, ZERO))
                            options.append((a, r, mpu, need))
                    # The machine that can make the most pieces now goes first (for machines of the
                    # same speed that is the one with most free time). A machine whose free time is
                    # all setup waits, unless no machine can make pieces in this shift.
                    options.sort(key=lambda o: (-(max(ZERO, o[0] - o[3]) / o[2]), o[1].code))
                    if any(o[0] > o[3] for o in options):
                        options = [o for o in options if o[0] > o[3]]
                else:
                    mpu = unit_minutes(op, None) or ZERO
                    frac = window_fraction(slot.start, slot.end, ready)
                    options = [(Decimal(slot.minutes) * frac, None, mpu, ZERO)]
                for a, r, mpu, need in options:
                    if need > 0 and r is not None:
                        spent = min(a, need)  # set the machine up before its first piece of the lot
                        self.ledger.take(r.id, idx, spent)
                        self._record(line_id, op.code, r.id, idx, ZERO, ZERO, setup=spent)
                        setup_paid[r.id] = setup_paid.get(r.id, ZERO) + spent
                        minutes_total += spent
                        begins = max(slot.start, ready)
                        start = begins if start is None else min(start, begins)
                        a -= spent
                        if a <= EPS:
                            continue
                    if mpu == 0:  # no duration to schedule
                        take_units, minutes = remaining, ZERO
                    else:
                        take_units = min(remaining, a / mpu)
                        minutes = take_units * mpu
                    if take_units <= EPS:
                        continue
                    if r is not None:
                        self.ledger.take(r.id, idx, minutes)
                    minutes_total += minutes
                    self._record(line_id, op.code, r.id if r else None, idx, minutes, take_units)
                    per_slot[idx] = per_slot.get(idx, ZERO) + take_units
                    s = max(slot.start, ready)
                    wait_total += take_units * Decimal((s - ready).total_seconds()) / 3600
                    start = s if start is None else min(start, s)
                    done = self._release_time(idx, op.bucket)
                    finish = done if finish is None else max(finish, done)
                    remaining -= take_units
                    if remaining <= EPS:
                        break
                idx += 1
            if remaining > EPS:
                complete, note = (
                    False,
                    f"{op.name} could not be fully scheduled inside the planning window.",
                )
                break

        if not constrained and not per_slot and release:
            finish = max(t for t, _ in release)  # nothing to load: done when released
            start = ready_first
        curve = self._curve(per_slot, units_total, op.bucket, finish or ready_first)
        wait = wait_total / units_total if units_total > 0 else ZERO
        return StepOut(
            curve, ready_first, start, finish, complete, note, wait, minutes=minutes_total
        )

    # --- core, moulding and melting together ----------------------------------------------------------
    def _mould_cap(
        self, op_lines: list[tuple[ResourceSpec, Decimal]], idx: int
    ) -> list[tuple[int, ResourceSpec, Decimal]]:
        out = []
        for r, mpu in op_lines:
            a = self.ledger.avail(r.id, idx)
            m = int(a / mpu) if a > EPS else 0
            if m > 0:
                out.append((m, r, mpu))
        return out

    def _furnace_room(
        self, f: ResourceSpec, hmin: Decimal, idx: int, line_id: int, mph: int, open_space: dict
    ) -> int:
        a = self.ledger.avail(f.id, idx)
        k = int(a / hmin) if a > EPS else 0
        if f.max_heats_per_shift is not None:
            k = max(0, min(k, f.max_heats_per_shift - self.ledger.heats_used.get((f.id, idx), 0)))
        return open_space.get((f.id, idx, line_id), 0) + k * mph

    def _pour(
        self,
        line_id: int,
        melting: OpSpec,
        f: ResourceSpec,
        hmin: Decimal,
        idx: int,
        m: int,
        mph: int,
        open_space: dict,
    ) -> None:
        space = open_space.get((f.id, idx, line_id), 0)
        into_open = min(space, m)
        fresh = m - into_open
        heats = math.ceil(fresh / mph) if fresh else 0
        if heats:
            self.ledger.take(f.id, idx, heats * hmin)
            self.ledger.heats_used[(f.id, idx)] = self.ledger.heats_used.get((f.id, idx), 0) + heats
        open_space[(f.id, idx, line_id)] = space - into_open + (heats * mph - fresh if heats else 0)
        self._record(line_id, melting.code, f.id, idx, heats * hmin, Decimal(m))

    def mould_and_pour(
        self,
        line_id: int,
        req: Requirement,
        moulding: OpSpec,
        melting: OpSpec,
        core_curve: Curve | None,
        lead_hours: Decimal,
    ) -> tuple[StepOut, StepOut, str]:
        """Make the moulds and pour them. Returns (moulding step, melting step, failure note)."""
        total = req.moulds
        mph = req.moulds_per_heat
        op_lines = [(r, unit_minutes(moulding, r)) for r in resources_of(moulding, self.res)]
        op_lines = [(r, m) for r, m in op_lines if m]
        furnaces = []
        for f in resources_of(melting, self.res):
            h = unit_minutes(melting, f)
            if h:
                furnaces.append((f, h))
        if not mph or not op_lines or not furnaces:
            why = (
                "moulds per heat is unknown (no furnace with a heat size)" if not mph
                else "no allowed moulding line has a speed" if not op_lines
                else "no allowed furnace has minutes per heat"
            )  # fmt: skip
            empty = StepOut(Curve([(self.plan_start, ONE)]), None, None, None, False)
            return empty, empty, f"Cannot plan moulding and melting: {why}."
        lead = timedelta(seconds=float(lead_hours * 3600))
        cores = core_curve.collapsed() if (core_curve and self.whole_lot) else core_curve
        coupled = self.settings.pour_same_shift
        open_space: dict = {}
        moulded: dict[int, Decimal] = {}
        poured: dict[int, Decimal] = {}
        done_moulds = 0
        done_poured = 0
        limits = {"furnace": 0, "line": 0, "cores": 0}
        wait_total = ZERO
        pour_wait_total = ZERO
        waiting: list[list] = []  # [slot end, moulds] made but not yet poured (not coupled)
        m_start = m_finish = p_start = p_finish = None
        n = len(self.timeline)
        idx = self.timeline.first_slot_after(self.plan_start)

        while (done_moulds < total or done_poured < total) and idx < n:
            slot = self.timeline.slots[idx]
            allowed = total if cores is None else int(cores.fraction_at(slot.end - lead) * total)
            can_make = max(0, allowed - done_moulds)
            while done_moulds < total and can_make > 0:
                line_opts = self._mould_cap(op_lines, idx)
                if not line_opts:
                    break
                if coupled:
                    cands = []
                    for m_line, r, mpu in line_opts:
                        for f, hmin in furnaces:
                            room = self._furnace_room(f, hmin, idx, line_id, mph, open_space)
                            m = min(m_line, room, can_make, total - done_moulds)
                            if m > 0:
                                cands.append((m, r, mpu, f, hmin, m_line, room))
                    if not cands:
                        break
                    cands.sort(key=lambda c: (-c[0], c[1].code, c[3].code))
                    m, r, mpu, f, hmin, m_line, room = cands[0]
                    limits["furnace" if m == room else "line" if m == m_line else "cores"] += m
                    self.ledger.take(r.id, idx, m * mpu)
                    self._record(line_id, moulding.code, r.id, idx, m * mpu, Decimal(m))
                    self._pour(line_id, melting, f, hmin, idx, m, mph, open_space)
                    poured[idx] = poured.get(idx, ZERO) + m
                    done_poured += m
                else:
                    m_line, r, mpu = max(line_opts, key=lambda o: (o[0], o[1].code))
                    m = min(m_line, can_make, total - done_moulds)
                    limits["line" if m == m_line else "cores"] += m
                    self.ledger.take(r.id, idx, m * mpu)
                    self._record(line_id, moulding.code, r.id, idx, m * mpu, Decimal(m))
                    waiting.append([slot.end, m])
                wait_total += m * Decimal((slot.start - self.plan_start).total_seconds()) / 3600
                m_start = slot.start if m_start is None else m_start
                m_finish = slot.end
                moulded[idx] = moulded.get(idx, ZERO) + m
                done_moulds += m
                can_make -= m
                if coupled:
                    p_start = slot.start if p_start is None else p_start
                    p_finish = slot.end
            if not coupled:
                # Pour what has been moulded (this shift or earlier), as far as the furnaces allow.
                queue = done_moulds - done_poured
                while queue > 0:
                    best = None
                    for f, hmin in furnaces:
                        room = self._furnace_room(f, hmin, idx, line_id, mph, open_space)
                        m = min(room, queue)
                        if m > 0 and (best is None or m > best[0]):
                            best = (m, f, hmin)
                    if best is None:
                        break
                    m, f, hmin = best
                    self._pour(line_id, melting, f, hmin, idx, m, mph, open_space)
                    poured[idx] = poured.get(idx, ZERO) + m
                    done_poured += m
                    queue -= m
                    left = m
                    while left > 0 and waiting:  # moulds are poured oldest first
                        take = min(left, waiting[0][1])
                        pour_wait_total += (
                            take
                            * Decimal(max(0, (slot.start - waiting[0][0]).total_seconds()))
                            / 3600
                        )
                        waiting[0][1] -= take
                        left -= take
                        if waiting[0][1] == 0:
                            waiting.pop(0)
                    p_start = slot.start if p_start is None else p_start
                    p_finish = slot.end
            idx += 1

        ok = done_moulds >= total and done_poured >= total
        total_d = Decimal(total)
        mould_out = StepOut(
            self._curve(moulded, total_d, "shift", self.plan_start),
            None,
            m_start,
            m_finish,
            done_moulds >= total,
        )
        pour_out = StepOut(
            self._curve(poured, total_d, "shift", self.plan_start), m_start, p_start, p_finish, ok
        )
        # The wait belongs to whatever held moulding back most: furnace, moulding line or cores.
        block_wait = wait_total / total_d if total else ZERO
        limiter = (
            max(limits, key=lambda k: (limits[k], k == "furnace", k == "line"))
            if any(limits.values())
            else ""
        )
        mould_out.limiter = limiter
        if coupled:
            if limiter == "furnace":
                pour_out.wait_hours = block_wait
            else:
                mould_out.wait_hours = block_wait
        else:
            mould_out.wait_hours = block_wait
            pour_out.wait_hours = pour_wait_total / total_d if total else ZERO
        note = (
            ""
            if ok
            else "Moulding and melting could not be fully scheduled inside the planning window."
        )
        return mould_out, pour_out, note

    # --- a whole line ------------------------------------------------------------------------------------
    def schedule_line(self, line: LineInput, part: PartSpec, req: Requirement) -> LineSchedule:
        out = LineSchedule()
        chain: Curve | None = None
        pending_lag = ZERO
        core_curve: Curve | None = None
        lead_hours = ZERO
        ops = list(part.ops)
        i = 0
        while i < len(ops):
            op = ops[i]
            result = OpResult(op.code, op.name, op.kind, op.sequence, req.minutes.get(op.code, ZERO), req.units.get(op.code, ZERO),
                              resource_ids=tuple(r.id for r in resources_of(op, self.res)), outsourced=op.outsourced)  # fmt: skip
            if op.kind == "core":
                lead_hours = Decimal(str(op.extra.get("lead_hours") or 0))
                step = self.allocate(
                    line.id,
                    op,
                    Decimal(req.cores),
                    [(self.plan_start, Decimal(req.cores))] if req.cores else [],
                )
                core_curve = chain = step.curve
                pending_lag = ZERO
                self._fill(result, step)
                result.capacity_modelled = bool(result.resource_ids)
                out.ops.append(result)
                if not step.complete:
                    return self._fail(out, op, step.note)
            elif op.kind == "moulding" and any(o.kind == "melting" for o in ops[i + 1 :]):
                j = next(k for k in range(i + 1, len(ops)) if ops[k].kind == "melting")
                melting = ops[j]
                m_step, p_step, note = self.mould_and_pour(
                    line.id, req, op, melting, core_curve, lead_hours
                )
                self._fill(result, m_step)
                result.units = Decimal(req.moulds)
                if m_step.limiter == "cores" and out.ops and out.ops[-1].kind == "core":
                    out.ops[-1].wait_hours = (out.ops[-1].wait_hours or ZERO) + m_step.wait_hours
                    result.wait_hours = ZERO  # the cores were the slow part, not the moulding line
                out.ops.append(result)
                melt = OpResult(melting.code, melting.name, "melting", melting.sequence, req.minutes.get(melting.code, ZERO), Decimal(req.moulds),
                                resource_ids=tuple(r.id for r in resources_of(melting, self.res)))  # fmt: skip
                self._fill(melt, p_step)
                out.ops.append(melt)
                if not (m_step.complete and p_step.complete):
                    return self._fail(out, melting if m_step.complete else op, note)
                cooling = Decimal(str(melting.extra.get("cooling_hours") or 0))
                chain = p_step.curve
                pending_lag = cooling + melting.lag_hours
                i = j  # melting handled with moulding
            else:
                if op.outsourced:
                    base = (
                        chain.finish + timedelta(seconds=float(pending_lag * 3600))
                        if chain
                        else self.plan_start
                    )
                    finish = base + timedelta(days=op.lead_days or 0)
                    step = StepOut(Curve([(finish, ONE)]), base, base, finish)
                    result.capacity_modelled = False
                else:
                    if chain is None:
                        release = (
                            [(self.plan_start, req.units.get(op.code, ZERO))]
                            if req.units.get(op.code, ZERO) > 0
                            else []
                        )
                    else:
                        release = _increments(
                            chain, pending_lag, req.units.get(op.code, ZERO), self.whole_lot
                        )
                    step = self.allocate(line.id, op, req.units.get(op.code, ZERO), release)
                    result.capacity_modelled = bool(result.resource_ids)
                    if op.setup_minutes or op.time_by_type:
                        result.minutes = step.minutes  # the machines' own times and setups
                if op.kind == "melting":
                    result.units = Decimal(req.moulds)
                self._fill(result, step)
                out.ops.append(result)
                if not step.complete:
                    return self._fail(out, op, step.note)
                chain = step.curve
                pending_lag = op.lag_hours
            i += 1
        return out

    @staticmethod
    def _fill(result: OpResult, step: StepOut) -> None:
        result.ready_at, result.start_at, result.finish_at, result.complete = (
            step.ready,
            step.start,
            step.finish,
            step.complete,
        )
        result.wait_hours = step.wait_hours

    @staticmethod
    def _fail(out: LineSchedule, op: OpSpec, note: str) -> LineSchedule:
        out.complete, out.failed_op = False, op.code
        out.notes.append(note)
        return out


__all__ = ["Curve", "LineSchedule", "Scheduler", "op_of"]
