"""Ranking, trends against the previous run, and the daily digest."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from . import rules
from .format import fmt_date
from .model import Card

SEVERITY_LABEL = {"critical": "Critical", "warning": "Warning", "info": "Info"}


def ranked(cards: Sequence[Card]) -> list[Card]:
    return sorted(cards, key=lambda c: (-c.rank, c.key))


def trend(card: Card, previous: Mapping[str, float]) -> str:
    """new, worse, better or same, by comparing impact with the same card in the previous run."""
    if card.key not in previous:
        return "new"
    before = previous[card.key]
    change = card.impact - before
    if abs(change) < max(rules.TREND_MIN_CHANGE * max(before, 1.0), 0.5):
        return "same"
    return "worse" if change > 0 else "better"


def resolved(cards: Sequence[Card], previous: Mapping[str, Any]) -> list[str]:
    """Keys that were in the previous run and are gone now."""
    now = {c.key for c in cards}
    return sorted(k for k in previous if k not in now)


def digest(cards: Sequence[Card], today: date, company_name: str = "") -> dict[str, Any]:
    """The top cards as a short summary: structured for the screen and PDF, text for email."""
    top = ranked(cards)[: rules.DIGEST_SIZE]
    heading = f"Daily digest, {fmt_date(today)}" + (f", {company_name}" if company_name else "")
    items = [
        {
            "severity": c.severity,
            "title": c.title,
            "message": c.message,
            "action": c.action,
            "key": c.key,
        }
        for c in top
    ]
    lines = [heading, ""]
    if not items:
        lines.append("Nothing needs attention today.")
    for n, i in enumerate(items, start=1):
        lines += [
            f"{n}. [{SEVERITY_LABEL[i['severity']]}] {i['title']}",
            f"   {i['message']}",
            f"   Next: {i['action']}",
            "",
        ]
    return {
        "title": heading,
        "date": today.isoformat(),
        "items": items,
        "text": "\n".join(lines).rstrip() + "\n",
    }
