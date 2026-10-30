"""Data health: gaps in the masters and schedule that make a plan wrong or unfinished."""

from collections import defaultdict
from collections.abc import Sequence

from .format import plural
from .model import Card, HealthItem, scaled

KIND_TITLE = {
    "no_route": "Parts without a route",
    "route_gap": "Route steps missing a time or a resource",
    "no_capacity": "Operations with no capacity modelled",
    "past_due": "Past internal dates with no actual dispatch",
    "unrealistic": "Unrealistic values",
}


def data_health(items: Sequence[HealthItem]) -> list[Card]:
    grouped: dict[str, list[HealthItem]] = defaultdict(list)
    for item in items:
        grouped[item.kind].append(item)
    cards = []
    for kind, found in grouped.items():
        affected = sum(i.lines_affected for i in found)
        if any(i.severity == "error" for i in found) and affected:
            severity = "critical"
        elif any(i.severity in ("error", "warning") for i in found):
            severity = "warning"
        else:
            severity = "info"
        found = sorted(found, key=lambda i: (-i.lines_affected, i.subject))
        cards.append(
            Card(
                key=f"data_health:{kind}", type="data_health", severity=severity,
                title=f"{KIND_TITLE.get(kind, kind)}: {len(found)}",
                message=(
                    f"{plural(len(found), 'item')}"
                    + (f", touching {plural(affected, 'schedule line')}" if affected else "")
                    + f". First: {found[0].subject}, {found[0].detail}"
                ),
                numbers={"items": len(found), "lines_affected": affected},
                entities={"items": [
                    {"subject": i.subject, "detail": i.detail, "why": i.why, "severity": i.severity, "link": i.link,
                     "lines_affected": i.lines_affected}
                    for i in found
                ]},
                action=found[0].why if len(found) == 1 else "Open Data health and work down the list, biggest effect first.",
                why=tuple(dict.fromkeys(i.why for i in found)),
                impact=scaled(affected, 10),
            )
        )  # fmt: skip
    return cards
