"""Every derived number carries the formula and the inputs it was computed from."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class Traced:
    value: Decimal | int | None
    formula: str
    inputs: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        value = self.value
        if isinstance(value, Decimal):
            value = float(value.quantize(Decimal("0.0001")).normalize())
        return {
            "value": value,
            "formula": self.formula,
            "inputs": {
                k: (float(v) if isinstance(v, Decimal) else v) for k, v in self.inputs.items()
            },
            "note": self.note,
        }
