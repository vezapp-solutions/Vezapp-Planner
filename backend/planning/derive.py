"""Derived master-data values. Never stored, so they cannot drift from their inputs."""

import math
from decimal import Decimal

from .trace import Traced


def _d(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def usable_heat_kg(heat_kg, melt_loss_pct) -> Traced:
    heat, loss = _d(heat_kg), _d(melt_loss_pct)
    return Traced(
        value=heat * (1 - loss / 100),
        formula="heat size kg × (1 − melt loss% ÷ 100)",
        inputs={"heat_kg": heat, "melt_loss_pct": loss},
    )


def suggested_moulds_per_heat(heat_kg, melt_loss_pct, pour_kg_per_mould) -> Traced:
    usable = usable_heat_kg(heat_kg, melt_loss_pct).value
    pour = _d(pour_kg_per_mould)
    value = math.floor(usable / pour) if pour > 0 else 0
    return Traced(
        value=value,
        formula="floor(heat size kg × (1 − melt loss% ÷ 100) ÷ pouring weight per mould kg)",
        inputs={
            "heat_kg": _d(heat_kg),
            "melt_loss_pct": _d(melt_loss_pct),
            "pour_kg_per_mould": pour,
        },
    )


def minutes_per_piece(minutes_per_heat, moulds_per_heat, cavities_per_mould) -> Traced:
    heat, moulds, cavities = _d(minutes_per_heat), _d(moulds_per_heat), _d(cavities_per_mould)
    denominator = moulds * cavities
    return Traced(
        value=heat / denominator if denominator > 0 else None,
        formula="minutes per heat ÷ (moulds per heat × cavities per mould)",
        inputs={
            "minutes_per_heat": heat,
            "moulds_per_heat": moulds,
            "cavities_per_mould": cavities,
        },
    )


def moulding_minutes_per_mould(explicit, moulds_per_hour) -> Traced:
    if explicit:
        return Traced(
            value=_d(explicit), formula="entered on the part's moulding operation", inputs={}
        )
    if moulds_per_hour:
        mph = _d(moulds_per_hour)
        return Traced(
            value=Decimal(60) / mph,
            formula="60 ÷ moulds per hour of the line",
            inputs={"moulds_per_hour": mph},
            note="no time entered; using the line's rated speed",
        )
    return Traced(value=None, formula="no time entered and no allowed line has a rated speed")


def core_minutes_per_core(
    explicit, cores_per_hour=None, cycle_seconds=None, cores_per_shot=None
) -> Traced:
    if explicit:
        return Traced(value=_d(explicit), formula="entered on the part's core operation", inputs={})
    if cores_per_hour:
        cph = _d(cores_per_hour)
        return Traced(
            value=Decimal(60) / cph,
            formula="60 ÷ cores per hour of the machine",
            inputs={"cores_per_hour": cph},
            note="no time entered; using the machine's rated speed",
        )
    if cycle_seconds and cores_per_shot:
        cycle, shot = _d(cycle_seconds), _d(cores_per_shot)
        return Traced(
            value=cycle / 60 / shot,
            formula="cycle seconds per shot ÷ 60 ÷ cores per shot",
            inputs={"cycle_seconds": cycle, "cores_per_shot": shot},
            note="no time entered; using the machine's rated cycle",
        )
    return Traced(value=None, formula="no time entered and no allowed machine has a rated speed")
