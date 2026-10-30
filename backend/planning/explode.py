"""Requirement explosion, section 7.1: what one schedule line asks of the plant."""

import math
from collections.abc import Mapping
from decimal import Decimal

from .derive import core_minutes_per_core, suggested_moulds_per_heat
from .model import LineInput, OpSpec, PartSpec, PlanSettings, Requirement, ResourceSpec
from .trace import Traced

FIXED_BASES = {"fixed_per_shift", "fixed_per_day"}


def _ceil(value: Decimal) -> int:
    return int(math.ceil(value))


def op_of(part: PartSpec, kind: str) -> OpSpec | None:
    return next((o for o in part.ops if o.kind == kind), None)


def resources_of(op: OpSpec, res: Mapping[int, ResourceSpec]) -> list[ResourceSpec]:
    """The op's allowed resources that exist, in a fixed order (by code) so ties are deterministic."""
    return sorted((res[i] for i in op.resource_ids if i in res), key=lambda r: r.code)


def unit_minutes(op: OpSpec, resource: ResourceSpec | None) -> Decimal | None:
    """Minutes one unit takes: a core, a mould, a heat, a piece or a batch (a block for fixed bases).

    A step that times each machine type (a VMC takes longer than an HMC) uses the time of the
    machine's type, and the step's default time for a type with none of its own."""
    if resource is not None and op.time_by_type and resource.type_id in op.time_by_type:
        return op.time_by_type[resource.type_id]
    explicit = op.time_value
    if op.kind == "core":
        return core_minutes_per_core(
            explicit,
            resource.rate_per_hour if resource else None,
            resource.cycle_seconds if resource else None,
            resource.cores_per_shot if resource else None,
        ).value
    if op.kind == "moulding":
        if explicit:
            return explicit
        return Decimal(60) / resource.rate_per_hour if resource and resource.rate_per_hour else None
    if op.kind == "melting":
        if explicit:
            return explicit
        return resource.heat_minutes if resource else None
    if explicit:
        return explicit
    if resource and resource.rate_per_hour and op.time_basis == "per_piece":
        return Decimal(60) / resource.rate_per_hour
    return None


def moulds_per_heat(
    part: PartSpec, melting: OpSpec, res: Mapping[int, ResourceSpec], default_loss: Decimal
) -> Traced:
    entered = melting.extra.get("moulds_per_heat")
    if entered:
        return Traced(int(entered), "entered on the part's melting operation", {})
    loss = (
        Decimal(str(melting.extra["melt_loss_pct"]))
        if melting.extra.get("melt_loss_pct") is not None
        else default_loss
    )
    heats = [r for r in resources_of(melting, res) if r.heat_kg]
    if not heats:
        return Traced(None, "no allowed furnace with a heat size")
    smallest = min(heats, key=lambda r: (r.heat_kg, r.code))
    return suggested_moulds_per_heat(smallest.heat_kg, loss, part.pouring_weight_per_mould_kg)


def explode_line(
    line: LineInput, part: PartSpec, settings: PlanSettings, res: Mapping[int, ResourceSpec]
) -> Requirement:
    traces: dict[str, Traced] = {}
    q = Decimal(line.qty)
    rejection = part.rejection_pct

    pieces = _ceil(q * (1 + rejection / 100))
    traces["pieces_to_pour"] = Traced(
        pieces,
        "ceil(dispatch qty × (1 + rejection% ÷ 100))",
        {"dispatch_qty": q, "rejection_pct": rejection},
    )

    moulding = op_of(part, "moulding")
    cavities = (
        int(moulding.extra["cavities_per_mould"])
        if moulding and moulding.extra.get("cavities_per_mould")
        else part.cavities_per_mould
    )
    moulds = _ceil(Decimal(pieces) / cavities)
    traces["moulds"] = Traced(
        moulds,
        "ceil(pieces to pour ÷ cavities per mould)",
        {"pieces_to_pour": pieces, "cavities_per_mould": cavities},
    )

    core = op_of(part, "core")
    cores = 0
    if core:
        per_mould = (
            Decimal(str(core.extra["cores_per_mould"]))
            if core.extra.get("cores_per_mould") is not None
            else Decimal(part.cores_per_mould)
        )
        scrap = Decimal(str(core.extra.get("scrap_pct") or 0))
        cores = _ceil(Decimal(moulds) * per_mould * (1 + scrap / 100))
        traces["cores"] = Traced(
            cores, "ceil(moulds × cores per mould × (1 + core scrap% ÷ 100))",
            {"moulds": moulds, "cores_per_mould": per_mould, "scrap_pct": scrap},
        )  # fmt: skip

    metal = Decimal(moulds) * part.pouring_weight_per_mould_kg
    traces["metal_kg"] = Traced(
        metal,
        "moulds × pouring weight per mould kg",
        {"moulds": moulds, "pour_kg": part.pouring_weight_per_mould_kg},
    )

    melting = op_of(part, "melting")
    mph: int | None = None
    heats: int | None = None
    if melting:
        traced = moulds_per_heat(part, melting, res, settings.default_melt_loss_pct)
        mph = int(traced.value) if traced.value else None
        traces["moulds_per_heat"] = traced
        if mph:
            heats = _ceil(Decimal(moulds) / mph)
            traces["heats"] = Traced(
                heats, "ceil(moulds ÷ moulds per heat)", {"moulds": moulds, "moulds_per_heat": mph}
            )

    minutes: dict[str, Decimal] = {}
    units: dict[str, Decimal] = {}
    for op in part.ops:
        if op.outsourced:
            minutes[op.code], units[op.code] = Decimal(0), Decimal(0)
            continue
        allowed = resources_of(op, res)
        first = next(iter(allowed), None)
        mpu = unit_minutes(op, first)
        averaged = False
        if op.time_by_type:
            # Machines of different types take different times, so the requirement (and with it
            # the due-date load) uses their average. The allocation then uses each machine's own.
            times = [t for t in (unit_minutes(op, r) for r in allowed) if t]
            if times:
                mpu, averaged = sum(times, Decimal(0)) / len(times), True
        if op.kind == "core":
            u = Decimal(cores)
        elif op.kind == "moulding":
            u = Decimal(moulds)
        elif op.kind == "melting":
            u = Decimal(heats or 0)
        elif op.time_basis in FIXED_BASES:
            u = Decimal(1)
        else:
            basis = pieces if op.sequence <= part.rejection_seq else line.qty
            if op.time_basis == "per_mould":
                u = Decimal(moulds)
            elif op.time_basis == "per_batch":
                u = Decimal(_ceil(Decimal(basis) / (op.batch_size or 1)))
            else:
                u = Decimal(basis)
        units[op.code] = u
        minutes[op.code] = u * mpu if mpu else Decimal(0)
        inputs = {"units": u, "minutes_per_unit": mpu}
        formula = f"{op.time_basis.replace('_', ' ')}: units × minutes per unit"
        note = "" if mpu else "no time and no rated speed: nothing to load"
        if averaged:
            formula = f"{formula} (average over the allowed machines)"
        if op.setup_minutes and u > 0:
            minutes[op.code] += (
                op.setup_minutes
            )  # one setup; each further machine used adds its own
            inputs["setup_minutes"] = op.setup_minutes
            formula += " + setup minutes for one machine"
        traces[f"minutes.{op.code}"] = Traced(minutes[op.code], formula, inputs, note=note)

    return Requirement(line.id, pieces, moulds, cores, metal, mph, heats, minutes, units, traces)
