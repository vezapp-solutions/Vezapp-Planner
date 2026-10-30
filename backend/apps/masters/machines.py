"""Which machines may run a route step, what the step is called, and how long each machine type takes.

A step's machines are the ones chosen one by one, plus every machine of the allowed machine types,
minus the machines marked as not suitable. A machine added later to an allowed type is picked up
automatically.
"""

from collections import defaultdict
from decimal import Decimal

from apps.resources.models import Resource
from planning.model import step_code

# Keys of PartOperation.extra that belong to machine choice, not to the engine's own settings.
MACHINE_KEYS = ("machine_types", "except", "time_by_type")


def machines_by_type(company) -> dict[int, list[int]]:
    out: dict[int, list[int]] = defaultdict(list)
    for pk, type_id in Resource.objects.for_company(company).values_list("pk", "resource_type_id"):
        out[type_id].append(pk)
    return out


def type_ids(op) -> list[int]:
    return [int(t) for t in (op.extra or {}).get("machine_types") or []]


def except_ids(op) -> list[int]:
    return [int(m) for m in (op.extra or {}).get("except") or []]


def allowed_ids(op, by_type: dict[int, list[int]]) -> list[int]:
    ids = {r.pk for r in op.resources.all()}
    for type_id in type_ids(op):
        ids.update(by_type.get(type_id, ()))
    ids.difference_update(except_ids(op))
    return sorted(ids)


def times_by_type(op) -> dict[int, Decimal]:
    raw = (op.extra or {}).get("time_by_type") or {}
    return {int(k): Decimal(str(v)) for k, v in raw.items() if v not in (None, "")}


def code_of(op) -> str:
    """The step's unique code: `machining` for the original step, `machining~20` for OP20."""
    return step_code(op.op_type.code, op.step)


def name_of(op) -> str:
    """For example "Machining OP10 Rough milling"."""
    parts = [op.op_type.name]
    if op.step:
        parts.append(f"OP{op.step}")
    if op.label:
        parts.append(op.label)
    return " ".join(parts)


def engine_extra_of(extra: dict | None) -> dict:
    """The settings the engine reads, without the machine-choice keys."""
    return {k: v for k, v in (extra or {}).items() if k not in MACHINE_KEYS}


def engine_extra(op) -> dict:
    return engine_extra_of(op.extra)
