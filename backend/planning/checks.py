"""Validation and sanity warnings for masters.

"error" blocks a save (impossible values). "warning" and "info" never block; the ranges come
from the domain research in PROMPT.md section 12 and are advisory only.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from .derive import suggested_moulds_per_heat

Level = Literal["error", "warning", "info"]

# Typical ranges (inclusive). Outside them is a warning, not a block.
CORE_MIN_PER_CORE = (Decimal("0.25"), Decimal(10))
MOULDING_MIN_PER_MOULD = (Decimal("0.2"), Decimal(30))
FURNACE_MIN_PER_HEAT = (Decimal(30), Decimal(240))
FETTLING_MIN_PER_PIECE = (Decimal("0.1"), Decimal(120))
COOLING_WARN_ABOVE_KG = Decimal(50)


@dataclass(frozen=True)
class Issue:
    level: Level
    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"level": self.level, "field": self.field, "message": self.message}


def _d(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _outside(issues: list[Issue], field: str, value: Decimal | None, bounds, label: str) -> None:
    if value is not None and not (bounds[0] <= value <= bounds[1]):
        issues.append(
            Issue(
                "warning",
                field,
                f"{label} of {value.normalize():f} is outside the typical range "
                f"{bounds[0].normalize():f} to {bounds[1].normalize():f}. Please check it.",
            )
        )


def check_part(part: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    casting, finished = _d(part.get("casting_weight_kg")), _d(part.get("finished_weight_kg"))
    pour, cavities = _d(part.get("pouring_weight_per_mould_kg")), _d(part.get("cavities_per_mould"))
    cores, rejection = _d(part.get("cores_per_mould")), _d(part.get("rejection_pct"))

    for field, value in (("casting_weight_kg", casting), ("pouring_weight_per_mould_kg", pour)):
        if value is None or value <= 0:
            issues.append(Issue("error", field, "Must be greater than zero."))
    if cavities is None or cavities < 1:
        issues.append(Issue("error", "cavities_per_mould", "A mould needs at least 1 cavity."))
    if cores is not None and cores < 0:
        issues.append(Issue("error", "cores_per_mould", "Cannot be negative."))
    if finished is not None and finished <= 0:
        issues.append(Issue("error", "finished_weight_kg", "Must be greater than zero."))
    if rejection is not None and not (0 <= rejection < 100):
        issues.append(Issue("error", "rejection_pct", "Must be at least 0 and less than 100."))

    if casting and pour and cavities and cavities >= 1 and pour < casting * cavities:
        issues.append(
            Issue(
                "warning",
                "pouring_weight_per_mould_kg",
                "Pouring weight per mould is less than cavities × casting weight. "
                "It should also include runners and risers.",
            )
        )
    if finished and casting and finished > casting:
        issues.append(
            Issue("warning", "finished_weight_kg", "Finished weight is above casting weight.")
        )
    return issues


def check_resource(resource: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    kind = resource.get("kind")
    units, efficiency = resource.get("units"), _d(resource.get("efficiency_pct"))
    if units is None or units < 1:
        issues.append(Issue("error", "units", "At least 1 unit is needed."))
    if efficiency is None or efficiency <= 0:
        issues.append(Issue("error", "efficiency_pct", "Must be greater than zero."))
    elif efficiency > 100:
        issues.append(
            Issue("warning", "efficiency_pct", "Planned efficiency above 100% is unusual.")
        )
    elif efficiency < 50:
        issues.append(
            Issue("warning", "efficiency_pct", "Planned efficiency below 50% is very low.")
        )

    for field in (
        "rate_per_hour",
        "cycle_seconds",
        "cores_per_shot",
        "heat_kg",
        "heat_minutes",
        "max_heats_per_shift",
    ):
        value = _d(resource.get(field))
        if value is not None and value <= 0:
            issues.append(Issue("error", field, "Must be greater than zero."))

    if kind == "core_machine":
        has_rate = resource.get("rate_per_hour")
        has_cycle = resource.get("cycle_seconds") and resource.get("cores_per_shot")
        if not (has_rate or has_cycle):
            issues.append(
                Issue(
                    "error",
                    "rate_per_hour",
                    "Enter cores per hour, or cycle seconds with cores per shot.",
                )
            )
    elif kind == "moulding_line":
        if not resource.get("rate_per_hour"):
            issues.append(Issue("error", "rate_per_hour", "Enter moulds per hour."))
    elif kind == "furnace":
        if not resource.get("heat_kg"):
            issues.append(Issue("error", "heat_kg", "Enter the heat size in kg."))
        if not resource.get("heat_minutes"):
            issues.append(
                Issue("error", "heat_minutes", "Enter the minutes per heat (tap to tap).")
            )
        _outside(
            issues,
            "heat_minutes",
            _d(resource.get("heat_minutes")),
            FURNACE_MIN_PER_HEAT,
            "Minutes per heat",
        )
    return issues


# Which resource kind each operation kind draws on.
RESOURCE_KIND_FOR = {
    "core": "core_machine",
    "moulding": "moulding_line",
    "melting": "furnace",
    "post": "work_centre",
}

# In the order a planner should see them.
TIME_BASES_FOR = {
    "core": ("per_core",),
    "moulding": ("per_mould",),
    "melting": ("per_heat",),
    "post": ("per_piece", "per_mould", "per_batch", "fixed_per_shift", "fixed_per_day"),
}


def check_operation(
    op: dict[str, Any], part: dict[str, Any], furnaces: list[dict[str, Any]]
) -> list[Issue]:
    """op: kind, code, enabled, time_value, time_basis, batch_size, lag_hours, outsourced, lead_days,
    extra, resource_count. furnaces: allowed furnaces as {heat_kg, heat_minutes}."""
    issues: list[Issue] = []
    if not op.get("enabled", True):
        return issues
    kind, code, extra = op["kind"], op.get("code", ""), op.get("extra") or {}
    time_value, basis = _d(op.get("time_value")), op.get("time_basis")

    if basis not in TIME_BASES_FOR[kind]:
        issues.append(
            Issue("error", "time_basis", "This time basis is not allowed for this operation.")
        )
    if time_value is not None and time_value <= 0:
        issues.append(Issue("error", "time_value", "Time must be greater than zero."))
    if basis == "per_batch" and (op.get("batch_size") or 0) < 1:
        issues.append(Issue("error", "batch_size", "Enter a batch size of at least 1."))
    lag = _d(op.get("lag_hours"))
    if lag is not None and lag < 0:
        issues.append(Issue("error", "lag_hours", "Lag cannot be negative."))
    for key in (
        "scrap_pct",
        "lead_hours",
        "cooling_hours",
        "melt_loss_pct",
        "cores_per_mould",
        "cavities_per_mould",
    ):
        value = _d(extra.get(key))
        if value is not None and value < 0:
            issues.append(Issue("error", f"extra.{key}", "Cannot be negative."))
    cavities = _d(extra.get("cavities_per_mould"))
    if cavities is not None and cavities < 1:
        issues.append(
            Issue("error", "extra.cavities_per_mould", "A mould needs at least 1 cavity.")
        )
    scrap, loss = _d(extra.get("scrap_pct")), _d(extra.get("melt_loss_pct"))
    if (scrap is not None and scrap >= 100) or (loss is not None and loss >= 100):
        issues.append(Issue("error", "extra", "A percentage must be below 100."))

    if op.get("outsourced") and not op.get("lead_days"):
        issues.append(
            Issue("error", "lead_days", "An outsourced operation needs a lead time in days.")
        )
    by_type = op.get("time_by_type") or {}
    if any((_d(v) or 0) <= 0 for v in by_type.values()):
        issues.append(
            Issue("error", "time_by_type", "Each machine type's time must be greater than zero.")
        )
    # A step that times each machine type needs no separate default time.
    if kind == "post" and not op.get("outsourced") and time_value is None and not by_type:
        issues.append(Issue("error", "time_value", "Enter the time in minutes."))

    if kind == "core":
        _outside(issues, "time_value", time_value, CORE_MIN_PER_CORE, "Core time per core")
    elif kind == "moulding":
        _outside(
            issues, "time_value", time_value, MOULDING_MIN_PER_MOULD, "Moulding time per mould"
        )
    elif kind == "melting":
        _outside(issues, "time_value", time_value, FURNACE_MIN_PER_HEAT, "Minutes per heat")
        _check_melting(issues, extra, part, furnaces)
    elif code == "fettling":
        _outside(issues, "time_value", time_value, FETTLING_MIN_PER_PIECE, "Fettling time")

    if kind != "melting" and not op.get("outsourced") and op.get("resource_count", 0) == 0:
        if kind == "post":
            issues.append(
                Issue(
                    "info",
                    "resources",
                    "No work centre is set, so capacity is not modelled for this operation.",
                )
            )
        else:
            issues.append(Issue("warning", "resources", "No allowed resource is selected."))
    return issues


def _check_melting(
    issues: list[Issue], extra: dict[str, Any], part: dict[str, Any], furnaces: list[dict[str, Any]]
) -> None:
    pour = _d(part.get("pouring_weight_per_mould_kg"))
    loss = _d(extra.get("melt_loss_pct"))
    moulds = _d(extra.get("moulds_per_heat"))

    if not furnaces:
        issues.append(Issue("warning", "resources", "No allowed furnace is selected."))
    if moulds is not None and moulds < 1:
        issues.append(
            Issue("error", "extra.moulds_per_heat", "Moulds per heat must be at least 1.")
        )
    if loss is None:
        issues.append(
            Issue(
                "warning",
                "extra.melt_loss_pct",
                "Melt loss is blank, so it is taken as the company default (0% unless set). "
                "Enter the real figure for a trustworthy heat size.",
            )
        )

    for furnace in furnaces:
        heat_kg = _d(furnace.get("heat_kg"))
        if heat_kg is None or not pour:
            continue
        suggested = suggested_moulds_per_heat(heat_kg, loss or Decimal(0), pour).value
        if suggested < 1:
            issues.append(
                Issue(
                    "error",
                    "resources",
                    f"A {heat_kg.normalize():f} kg heat cannot pour even one mould of {pour.normalize():f} kg.",
                )
            )
        elif moulds is not None and moulds > suggested:
            issues.append(
                Issue(
                    "warning",
                    "extra.moulds_per_heat",
                    f"{moulds.normalize():f} moulds need more metal than one {heat_kg.normalize():f} kg heat "
                    f"holds (about {suggested} moulds).",
                )
            )

    cooling, casting = _d(extra.get("cooling_hours")), _d(part.get("casting_weight_kg"))
    if (cooling is None or cooling == 0) and casting and casting > COOLING_WARN_ABOVE_KG:
        issues.append(
            Issue(
                "warning",
                "extra.cooling_hours",
                f"Cooling time is 0 for a {casting.normalize():f} kg casting. Heavy castings usually need hours in the mould.",
            )
        )
