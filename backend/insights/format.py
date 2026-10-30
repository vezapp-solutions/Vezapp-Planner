"""Indian-context wording for card messages: DD-MM-YYYY, 1,00,000 grouping, tonnes."""

from datetime import date


def indian(value: float | int, digits: int = 0) -> str:
    """Group digits the Indian way: 1234567 -> 12,34,567."""
    negative = value < 0
    text = f"{abs(value):.{digits}f}"
    whole, _, frac = text.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    out = whole + (f".{frac}" if frac else "")
    return f"-{out}" if negative else out


def fmt_date(value: date | str) -> str:
    d = date.fromisoformat(value) if isinstance(value, str) else value
    return d.strftime("%d-%m-%Y")


def pct(share: float) -> str:
    return f"{round(share * 100)}%"


def tonnes(kg: float) -> str:
    return f"{indian(kg / 1000, 1)} t"


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{indian(n)} {one if n == 1 else (many or one + 's')}"


def month_name(year: int, month: int) -> str:
    return date(year, month, 1).strftime("%B %Y")
