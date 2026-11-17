"""The mould plan and the melt plan as the screens and the Excel export read them.

Both come from the stored plan: the mould plan from the moulding allocations and machine load, the melt
plan from the heats the heat planner stored. Nothing here recalculates anything.
"""

from datetime import date

from django.db.models import Q

from .models import Plan, PlanAllocation, PlanHeat, PlanLoad

AT_RISK = ("at_risk", "unscheduled")


def _is_moulding():
    return Q(op_code="moulding") | Q(op_code__startswith="moulding~")


def mould_plan(plan: Plan, start: date, end: date) -> dict:
    """Per day, per shift, per machine: which parts are moulded, how many moulds and castings, and how
    full the machine is. Plus a warning for every order that cannot make its dispatch date."""
    allocs = list(
        PlanAllocation.objects.filter(plan=plan, slot__slot_date__range=(start, end))
        .filter(_is_moulding())
        .exclude(resource__isnull=True)
        .select_related("plan_line", "slot", "resource")
        .order_by("slot__start", "resource__code", "plan_line__internal_date", "plan_line_id")
    )
    loads = {
        (rid, sid): (load, cap)
        for rid, sid, load, cap in PlanLoad.objects.filter(
            plan=plan, slot__slot_date__range=(start, end)
        ).values_list("resource_id", "slot_id", "load", "capacity")
    }
    days: dict[date, dict] = {}
    for a in allocs:
        slot, line = a.slot, a.plan_line
        req = line.requirement or {}
        pieces, moulds_total = req.get("pieces_to_pour") or 0, req.get("moulds") or 0
        castings = round(a.qty * pieces / moulds_total) if moulds_total else 0
        day = days.setdefault(
            slot.slot_date, {"date": slot.slot_date, "shifts": {}, "moulds": 0.0, "castings": 0}
        )
        shift = day["shifts"].setdefault(
            slot.pk,
            {"slot": slot.pk, "shift": slot.shift_name, "start": slot.start, "machines": {}},
        )
        load, cap = loads.get((a.resource_id, slot.pk), (0.0, 0.0))
        machine = shift["machines"].setdefault(
            a.resource_id,
            {
                "id": a.resource_id,
                "code": a.resource.code,
                "load_minutes": round(load, 1),
                "capacity_minutes": round(cap, 1),
                "used_pct": round(load / cap * 100, 1) if cap else None,
                "moulds": 0.0,
                "castings": 0,
                "items": [],
            },
        )
        machine["moulds"] += a.qty
        machine["castings"] += castings
        machine["items"].append(
            {
                "line_id": line.pk,
                "part_number": line.part_number,
                "part_name": line.part_name,
                "customer_code": line.customer_code,
                "moulds": round(a.qty, 1),
                "castings": castings,
                "minutes": round(a.minutes, 1),
                "due": line.internal_date,
                "status": line.status,
            }
        )
        day["moulds"] += a.qty
        day["castings"] += castings

    out_days = []
    for d in sorted(days):
        day = days[d]
        shifts = []
        for shift in sorted(day["shifts"].values(), key=lambda s: s["start"]):
            machines = sorted(shift["machines"].values(), key=lambda m: m["code"])
            for m in machines:
                m["moulds"] = round(m["moulds"], 1)
            shifts.append({**shift, "machines": machines})
        out_days.append(
            {
                "date": d,
                "moulds": round(day["moulds"], 1),
                "castings": day["castings"],
                "shifts": shifts,
            }
        )

    warnings = [
        {
            "line_id": ln.pk,
            "part_number": ln.part_number,
            "customer_code": ln.customer_code,
            "due": ln.internal_date,
            "est_dispatch": ln.est_dispatch_date,
            "status": ln.status,
            "text": _at_risk_text(ln),
        }
        for ln in plan.lines.filter(status__in=AT_RISK).order_by("internal_date", "id")
    ]
    return {"from": start, "to": end, "days": out_days, "warnings": warnings}


def _at_risk_text(line) -> str:
    if line.status == "unscheduled":
        return (line.notes[0] if line.notes else "It does not fit the planning window.")[:200]
    late = -(line.slack_working_days or 0)
    base = "Cannot be met"
    if line.est_dispatch_date:
        base = f"Estimated {line.est_dispatch_date:%d-%m-%Y}, {late} working day(s) late"
    return base + (f". {line.holding_text}" if line.holding_text else ".")


def melt_plan(plan: Plan, start: date, end: date) -> dict:
    """Per day: the heats (grade, kg, fill, what they pour) by furnace, with the furnace's use of the
    day and the warnings (under-filled heats, heats no furnace can take)."""
    melt = (plan.summary or {}).get("melt")
    if melt is None:
        return {"enabled": False, "from": start, "to": end, "days": [], "summary": {}}
    heats = list(
        PlanHeat.objects.filter(plan=plan, day__range=(start, end))
        .prefetch_related("pours")
        .order_by("day", "sequence")
    )
    days: dict[date, dict] = {}
    for h in heats:
        day = days.setdefault(
            h.day, {"date": h.day, "heats": [], "kg": 0.0, "furnaces": [], "warnings": []}
        )
        day["heats"].append(
            {
                "id": h.pk,
                "heat_no": h.heat_no,
                "furnace": h.furnace_code or None,
                "shift": h.shift_name,
                "grade": h.grade,
                "kg": round(h.kg, 1),
                "capacity_kg": round(h.capacity_kg, 1),
                "charge_kg": round(h.charge_kg, 1),
                "fill_pct": h.fill_pct,
                "warnings": h.warnings,
                "pours": [
                    {"part_number": p.part_number, "moulds": p.moulds, "kg": round(p.kg, 1)}
                    for p in sorted(h.pours.all(), key=lambda p: p.pk)
                ],
            }
        )
        day["kg"] += h.kg
    for entry in melt.get("days", []):
        d = date.fromisoformat(entry["day"])
        if d in days:
            days[d]["furnaces"].append(entry)
    for w in melt.get("warnings", []):
        d = date.fromisoformat(w["day"])
        if d in days:
            days[d]["warnings"].append(w)
    for day in days.values():
        day["kg"] = round(day["kg"], 1)
    return {
        "enabled": True,
        "from": start,
        "to": end,
        "days": [days[d] for d in sorted(days)],
        "summary": {k: v for k, v in melt.items() if k not in ("warnings", "days")},
    }
