"""Basic mode: keyword and intent matching, with answers worded like a person and filled from the tools.

It answers a fixed set of questions and says so. Every number in an answer is copied from a tool
result, the same rule the Claude layer is held to.
"""

import re
from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.resources.models import Resource
from insights.format import fmt_date, indian

from .tools import Toolbox, customer_codes, part_numbers

BASIC_NOTICE = "Basic mode: I answer a fixed set of questions from your plan. Add an AI key to ask anything else."

STATUS_WORDS = {
    "on_track": "on track",
    "tight": "tight",
    "at_risk": "at risk",
    "unscheduled": "not scheduled",
}

HELP = (
    "I can help with things like these:\n"
    "- Which lines are at risk? (add a customer, for example “at risk for C-101”)\n"
    "- How is the plan overall? What is planned today or tomorrow?\n"
    "- Where is the bottleneck? Do we have a capacity gap?\n"
    "- Which machines are free? (add VMC, CNC, HMC or a machine code)\n"
    "- How is a customer doing? What is the status of a part?\n"
    "- What is the month forecast? Summarise this month.\n"
    "- Do we have any data problems?\n"
    "For what-if trials, use the What-if screen."
)


def _words(text: str) -> str:
    return re.sub(r"[^a-z0-9\-\. ]+", " ", text.lower())


def _find(text: str, table: dict[str, str]) -> str | None:
    padded = f" {_words(text)} "
    for key in sorted(table, key=len, reverse=True):
        if f" {key} " in padded:
            return table[key]
    return None


def _has(text: str, *needles: str) -> bool:
    low = text.lower()
    return any(n in low for n in needles)


def _has_word(text: str, *words: str) -> bool:
    found = set(_words(text).split())
    return any(w in found for w in words)


def _machine_words(company) -> tuple[dict[str, str], dict[str, str]]:
    """Machine codes and machine type names, lower case to their proper spelling."""
    codes = {r.code.lower(): r.code for r in Resource.objects.for_company(company)}
    types = {
        t.lower(): t
        for t in Resource.objects.for_company(company)
        .filter(resource_type__kind="work_centre")
        .values_list("resource_type__name", flat=True)
        .distinct()
    }
    return codes, types


# --- answers ------------------------------------------------------------------------------------------
def _no_plan(r: dict) -> str:
    return f"{r['note']} Calculate one on the Plan screen and I can tell you a lot more."


def _at_risk(box: Toolbox, customer: str | None) -> str:
    r = box.call("get_at_risk_lines", {"customer": customer} if customer else {})
    if "error" in r:
        return r["error"]
    if r.get("plan_version") is None:
        return _no_plan(r)
    scope = f" for {customer}" if customer else ""
    if not r["total_at_risk"]:
        return f"Good news: no lines{scope} are at risk in plan v{r['plan_version']}."
    out = [
        f"{indian(r['total_at_risk'])} line(s){scope} are at risk in plan v{r['plan_version']}. These are the worst:"
    ]
    for ln in r["lines"]:
        late = (
            "does not fit the planning window, which usually means a data problem"
            if ln["status"] == "unscheduled"
            else f"estimated {fmt_date(ln['estimated_date'])}, {ln['working_days_late']} working day(s) late"
        )
        held = f", held up by {ln['held_up_by']}" if ln["held_up_by"] else ""
        out.append(
            f"- {ln['part']} for {ln['customer']}: {indian(ln['qty'])} pieces due {fmt_date(ln['internal_date'])}, {late}{held}."
        )
    if r["total_at_risk"] > len(r["lines"]):
        out.append(f"That's {len(r['lines'])} of {indian(r['total_at_risk'])}.")
    return "\n".join(out)


def _overview(box: Toolbox) -> str:
    r = box.call("get_plan_overview", {})
    if r.get("plan_version") is None:
        return _no_plan(r)
    by = r["by_status"]
    parts = [
        f"{indian(by[k])} {STATUS_WORDS[k]}"
        for k in ("on_track", "tight", "at_risk", "unscheduled")
        if by.get(k)
    ]
    state = "confirmed" if r["status"] == "confirmed" else "a draft"
    out = [
        f"Plan v{r['plan_version']} is {state} and covers {indian(r['lines'] or 0)} lines: {', '.join(parts) or 'nothing planned yet'}."
    ]
    if r["overall_bottleneck"]:
        out.append(f"The bottleneck overall is {r['overall_bottleneck']}.")
    if r["out_of_date"]:
        out.append(
            "It is out of date, so it is worth recalculating: " + " ".join(r["out_of_date_because"])
        )
    return "\n".join(out)


def _bottleneck(box: Toolbox) -> str:
    r = box.call("get_bottlenecks", {})
    if r.get("plan_version") is None:
        return _no_plan(r)
    busy = [d for d in r["days"] if d["busiest_resource"]]
    if not busy:
        return "Nothing is planned in the next working days, so there is no bottleneck to speak of."
    top = max(busy, key=lambda d: (d["utilisation_percent"], d["date"]))
    out = [f"{r['overall_bottleneck']} is the bottleneck in plan v{r['plan_version']}."]
    out.append(
        f"The busiest day coming up is {fmt_date(top['date'])}, when {top['busiest_resource']} is at {top['utilisation_percent']}%."
    )
    out.append("Day by day, the busiest resource is:")
    out += [
        f"- {fmt_date(d['date'])}: {d['busiest_resource']} at {d['utilisation_percent']}%"
        for d in busy
    ]
    return "\n".join(out)


def _capacity(box: Toolbox) -> str:
    r = box.call("get_capacity_gap", {})
    if not r["cards"]:
        return r["note"]
    return "Here is what I see on capacity:\n" + "\n".join(f"- {c['message']}" for c in r["cards"])


def _performance(box: Toolbox, customer: str | None, part: str | None) -> str:
    args = {k: v for k, v in (("customer", customer), ("part_number", part)) if v}
    r = box.call("get_dispatch_performance", args)
    who = customer or part or "all customers"
    if "error" in r:
        return r["error"]
    if not r["lines"]:
        return f"I don't have any dispatched lines with an actual date for {who}, so I can't give an on-time record yet."
    out = [
        f"For {who}, {r['on_time_percent']}% of lines went out on time ({indian(r['on_time'])} of {indian(r['lines'])}). "
        f"The late ones were {r['average_delay_days_of_late_lines']} days late on average, and the worst was {r['worst_delay_days']} days."
    ]
    out += [
        f"- {m['month']}: {m['on_time_percent']}% on time ({indian(m['lines'])} lines)"
        for m in r["by_month"]
    ]
    out.append(r["definition"])
    return "\n".join(out)


def _customer(box: Toolbox, customer: str) -> str:
    r = box.call("get_customer_status", {"customer": customer})
    if "error" in r:
        return r["error"]
    c = r["customer"]
    out = [f"Here is where {c['name']} ({c['code']}) stands."]
    if r.get("plan_version") is None:
        out.append(_no_plan(r))
    else:
        by = r["by_status"]
        parts = [
            f"{indian(by[k])} {STATUS_WORDS[k]}"
            for k in ("on_track", "tight", "at_risk", "unscheduled")
            if by.get(k)
        ]
        out.append(
            f"Plan v{r['plan_version']} has {indian(r['lines_in_plan'])} line(s) for them: {', '.join(parts) or 'none'}."
        )
        for ln in r["lines"]:
            est = fmt_date(ln["estimated_date"]) if ln["estimated_date"] else "no estimate"
            held = f", held up by {ln['held_up_by']}" if ln["held_up_by"] else ""
            out.append(
                f"- {ln['part']}: {indian(ln['qty'])} pieces due {fmt_date(ln['internal_date'])}, estimated {est} ({STATUS_WORDS[ln['status']]}){held}."
            )
    d = r["dispatch_record"]
    if d:
        out.append(
            f"Their dispatch record: {d['on_time_percent']}% on time ({indian(d['on_time'])} of {indian(d['lines_dispatched'])} lines)."
        )
    return "\n".join(out)


def _part(box: Toolbox, part: str) -> str:
    r = box.call("get_part_status", {"part_number": part})
    if "error" in r:
        return r["error"]
    out = [f"{r['part']} is {r['name']}, grade {r['grade'] or 'not set'}."]
    out.append(
        "Its route is "
        + (
            ", ".join(f"{o['operation']} on {o['resources'] or 'no resource'}" for o in r["route"])
            or "empty so far"
        )
        + "."
    )
    if not r["lines"]:
        out.append("It has no lines in the latest plan.")
    for ln in r["lines"]:
        est = fmt_date(ln["estimated_date"]) if ln["estimated_date"] else "not scheduled"
        out.append(
            f"- {ln['customer']}: {indian(ln['qty'])} pieces due {fmt_date(ln['internal_date'])}, estimated {est} ({STATUS_WORDS[ln['status']]})."
        )
    return "\n".join(out)


def _month(box: Toolbox) -> str:
    r = box.call("get_month_forecast", {})
    return r.get("note") or f"{r['title']}\n{r['message']}\nA good next step: {r['action']}"


def _machines(box: Toolbox, machine: str | None, machine_type: str | None) -> str:
    args = {k: v for k, v in (("machine", machine), ("machine_type", machine_type)) if v}
    r = box.call("get_machine_availability", args)
    if "error" in r:
        return r["error"]
    if r.get("plan_version") is None or "types" not in r:
        return r.get("note") or "I can't see any machines yet."
    out = [
        f"Here is the machine picture from {fmt_date(r['from'])} to {fmt_date(r['to'])} (plan v{r['plan_version']}):"
    ]
    for t in r["types"]:
        out.append(f"{t['type']}: {t['free_hours']} h free, {t['utilisation_percent']}% used.")
        for m in t["machines"]:
            blocked = (
                f" It is blocked from {fmt_date(m['blocked'][0]['from'][:10])}."
                if m["blocked"]
                else ""
            )
            out.append(
                f"- {m['machine']}: {m['free_hours']} h free, {m['utilisation_percent']}% used.{blocked}"
            )
    return "\n".join(out)


def _day(box: Toolbox, when: str | None, label: str) -> str:
    r = box.call("get_day_plan", {"date": when} if when else {})
    if "error" in r:
        return r["error"]
    if r.get("plan_version") is None:
        return _no_plan(r)
    out = [f"{label} ({r['weekday']} {fmt_date(r['date'])}), the plan has:"]
    if not r["work"]:
        out.append("- nothing scheduled")
    for w in r["work"]:
        setup = f", of which {w['setup_hours']} h setup" if w["setup_hours"] else ""
        out.append(
            f"- {w['operation']}: {indian(w['quantity'], 1)} {w['unit']} for {indian(w['lines'])} line(s), {w['hours']} h{setup}"
        )
    if r["busiest_resources"]:
        top = r["busiest_resources"][0]
        out.append(f"The busiest resource is {top['resource']} at {top['utilisation_percent']}%.")
    return "\n".join(out)


def _data_health(box: Toolbox) -> str:
    r = box.call("get_data_health", {})
    if not r["items"]:
        return r["note"]
    out = [f"I found {indian(r['items'])} thing(s) worth fixing. The biggest:"]
    for i in r["worst"]:
        effect = (
            f" It touches {indian(i['lines_affected'])} line(s)." if i["lines_affected"] else ""
        )
        out.append(f"- {i['subject']}: {i['problem']}.{effect} {i['why_it_matters']}")
    return "\n".join(out)


def summary(box: Toolbox) -> str:
    """The monthly summary in basic mode: what needs attention first, then the record, then the forecast."""
    parts = [_at_risk(box, None), _performance(box, None, None), _month(box)]
    return "\n\n".join(parts)


# --- small talk ---------------------------------------------------------------------------------------------
def _greeting(box: Toolbox) -> str:
    r = box.call("get_plan_overview", {})
    if r.get("plan_version") is None:
        return "Hello! I'm your planning assistant. No plan has been calculated yet; once there is one I can tell you what is at risk and what to look at first. What would you like to know?"
    by = r["by_status"]
    risky = by.get("at_risk", 0) + by.get("unscheduled", 0)
    news = f"{indian(risky)} line(s) are at risk" if risky else "nothing is at risk"
    return f"Hello! I'm your planning assistant. Plan v{r['plan_version']} is the latest and {news}. What would you like to look at?"


def _date_in(text: str) -> str | None:
    found = re.search(r"\b(\d{2})-(\d{2})-(\d{4})\b", text)
    if found:
        return f"{found.group(3)}-{found.group(2)}-{found.group(1)}"
    found = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    return found.group(0) if found else None


def answer(box: Toolbox, question: str) -> dict[str, Any]:
    customer = _find(question, customer_codes(box.company))
    part = _find(question, part_numbers(box.company))
    machine_codes, machine_types = _machine_words(box.company)
    machine = _find(question, machine_codes)
    machine_type = _find(question, machine_types)
    q = question.strip()

    if _has_word(q, "thanks", "thank", "thx", "cheers") or q.lower().startswith("thank"):
        intent, text = (
            "thanks",
            "You're welcome! Ask me anything else about the plan whenever you like.",
        )
    elif re.match(r"^(hi|hello|hey|namaste|good (morning|afternoon|evening))\b", q.lower()):
        intent, text = "greeting", _greeting(box)
    elif _has(q, "what can you", "what do you do", "help", "who are you", "how do you work"):
        intent, text = (
            "help",
            "I'm the planning assistant for this plant, and I answer from your own plan and schedule.\n"
            + HELP,
        )
    elif _has(q, "what if", "what happens if", "suppose"):
        intent, text = (
            "what_if",
            "Trying a what-if is something I can only do in AI mode. For now the What-if screen lets you block a machine, change a quantity or date, or add a shift and see exactly which lines move.",
        )
    elif _has(q, "bottleneck", "busiest", "congest", "overloaded"):
        intent, text = "bottleneck", _bottleneck(box)
    elif (
        machine
        or machine_type
        or (_has(q, "machine", "free hours", "availab", "idle") and not customer)
    ):
        intent, text = "machines", _machines(box, machine, machine_type)
    elif _has(q, "capacity", "extra shift", "spare", "short of"):
        intent, text = "capacity_gap", _capacity(box)
    elif _has(q, "forecast", "month", "slip"):
        intent, text = "month_forecast", _month(box)
    elif _has(
        q, "data problem", "data health", "missing", "no route", "data quality", "problems with"
    ):
        intent, text = "data_health", _data_health(box)
    elif _has(q, "today", "tomorrow", "this morning") or _date_in(q):
        when = _date_in(q) or (
            (timezone.localdate() + timedelta(days=1)).isoformat()
            if "tomorrow" in q.lower()
            else None
        )
        label = (
            "Tomorrow"
            if "tomorrow" in q.lower()
            else ("Today" if not _date_in(q) else "On that day")
        )
        intent, text = "day_plan", _day(box, when, label)
    elif _has(q, "risk", "late", "delay", "miss", "behind") and not _has(
        q, "on time", "on-time", "performance", "record"
    ):
        intent, text = "at_risk", _at_risk(box, customer)
    elif _has(q, "on time", "on-time", "performance", "record", "dispatched"):
        intent, text = (
            "customer_performance",
            _performance(box, customer, part if not customer else None),
        )
    elif _has(
        q,
        "overall",
        "overview",
        "status of the plan",
        "how is the plan",
        "how's the plan",
        "plan status",
        "how are we doing",
        "how are we",
    ):
        intent, text = "overview", _overview(box)
    elif customer:
        intent, text = "customer_status", _customer(box, customer)
    elif part:
        intent, text = "part_status", _part(box, part)
    else:
        intent, text = "help", "I'm not sure I understood that, sorry. " + HELP
    return {"answer": text, "intent": intent}
