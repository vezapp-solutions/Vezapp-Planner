"""The number guard: a model's answer may only contain numbers that appear in this turn's tool
results (or in the user's own question). Anything else is treated as invented and blocked."""

import re
from datetime import date
from typing import Any

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
ENUMERATOR = re.compile(r"(?m)^\s*(?:[-*]\s*)?\d{1,2}[.)]\s")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def canon(token: str) -> str:
    """One spelling per number: no commas, no leading zeros, no trailing zero decimals."""
    token = token.replace(",", "")
    if "." in token:
        whole, _, frac = token.partition(".")
        frac = frac.rstrip("0")
        token = whole.lstrip("0") or "0"
        return f"{token}.{frac}" if frac else token
    return token.lstrip("0") or "0"


def numbers_in(text: str) -> list[str]:
    """Every number in a piece of text, in canonical form. List numbering ("1. ") is not counted."""
    return [canon(m) for m in NUMBER.findall(ENUMERATOR.sub(" ", text))]


def _add_number(allowed: set[str], value: float) -> None:
    for digits in (0, 1, 2):
        allowed.add(canon(f"{abs(value):.{digits}f}"))
    allowed.add(canon(repr(abs(value))))
    if 0 <= abs(value) <= 1.5:  # a share, which a reply is likely to give as a percentage
        for digits in (0, 1):
            allowed.add(canon(f"{abs(value) * 100:.{digits}f}"))


def _walk(node: Any, allowed: set[str]) -> None:
    if isinstance(node, bool) or node is None:
        return
    if isinstance(node, (int, float)):
        _add_number(allowed, float(node))
    elif isinstance(node, str):
        allowed.update(canon(t) for t in NUMBER.findall(node))
        for y, m, d in ISO_DATE.findall(node):  # a reply writes the date as DD-MM-YYYY
            try:
                date(int(y), int(m), int(d))
            except ValueError:
                continue
            allowed.update({canon(y), canon(m), canon(d)})
    elif isinstance(node, dict):
        for value in node.values():
            _walk(value, allowed)
    elif isinstance(node, (list, tuple)):
        allowed.add(str(len(node)))  # "3 lines" is a count of what the tool returned
        for value in node:
            _walk(value, allowed)


def allowed_numbers(results: list[Any], question: str = "") -> set[str]:
    allowed: set[str] = set()
    for result in results:
        _walk(result, allowed)
    allowed.update(numbers_in(question))  # numbers the user said themselves
    return allowed


def unverified(reply: str, results: list[Any], question: str = "") -> list[str]:
    """Numbers in the reply that no tool result (or the question) contains. Empty means it passes."""
    allowed = allowed_numbers(results, question)
    seen: list[str] = []
    for number in numbers_in(reply):
        if number not in allowed and number not in seen:
            seen.append(number)
    return seen
