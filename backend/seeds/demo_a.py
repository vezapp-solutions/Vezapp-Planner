"""A synthetic mid-size iron foundry for the demo company: all names and figures are invented."""

from datetime import time

from apps.companies.models import Plant, Shift, WeekdayShift
from apps.masters.models import Customer, Grade, OperationType, Part, PartCustomer, PartOperation
from apps.resources.models import Resource, ResourceType
from planning.derive import suggested_moulds_per_heat

# code, name, kind, plant index, fields
RESOURCES = [
    (
        "CM1",
        "Cold-box core shooter 1",
        "core_machine",
        0,
        {"cycle_seconds": 60, "cores_per_shot": 2},
    ),
    ("CM2", "Cold-box core shooter 2", "core_machine", 0, {"rate_per_hour": 45}),
    ("LINE-A", "Automatic moulding line A", "moulding_line", 0, {"rate_per_hour": 90}),
    ("LINE-B", "Jolt-squeeze line B", "moulding_line", 0, {"rate_per_hour": 28}),
    ("F1", "Induction furnace 1", "furnace", 0, {"heat_kg": 1000, "heat_minutes": 75}),
    ("F2", "Induction furnace 2", "furnace", 0, {"heat_kg": 500, "heat_minutes": 60}),
    ("KO", "Knockout station", "work_centre", 0, {}),
    ("FT", "Fettling bay", "work_centre", 0, {"units": 4}),
    ("MC", "Machining cell", "work_centre", 0, {"units": 3}),
    ("PK", "Packing table", "work_centre", 0, {"units": 2}),
]

CUSTOMERS = [
    ("C-101", "Aarav Pumps (synthetic)", "A", "Gujarat"),
    ("C-102", "Bharat Valves (synthetic)", "B", "Maharashtra"),
    ("C-103", "Kaveri Auto Components (synthetic)", "A", "Tamil Nadu"),
    ("C-104", "Himal Engineering (synthetic)", "C", "Punjab"),
]

# number, name, grade, customer, casting kg, pour kg/mould, cavities, cores, rejection %, machined, line
PARTS = [
    ("PMP-201", "Pump casing", "GG25", "C-101", 18, 46, 2, 2, 4, True, "LINE-A"),
    ("PMP-202", "Pump cover", "GG25", "C-101", 6.5, 17, 2, 1, 3, True, "LINE-A"),
    ("VLV-310", "Valve body", "SG500", "C-102", 12, 32, 2, 2, 6, True, "LINE-B"),
    ("VLV-311", "Valve bonnet", "SG500", "C-102", 4.2, 11, 4, 0, 3, False, "LINE-A"),
    ("AUT-420", "Brake drum", "GG25", "C-103", 9.5, 21, 2, 0, 2, True, "LINE-A"),
    ("ENG-505", "Gearbox housing", "GG25", "C-104", 42, 95, 1, 3, 5, True, "LINE-B"),
]


def build_demo_foundry(company):
    plants = [Plant.objects.get_or_create(company=company, name=n)[0] for n in ("Plant 1 - Iron",)]
    shifts = [
        Shift.objects.get_or_create(
            company=company,
            name=name,
            defaults={"start_time": start, "end_time": end, "break_minutes": 30},
        )[0]
        for name, start, end in (
            ("Shift 1", time(6, 0), time(14, 0)),
            ("Shift 2", time(14, 0), time(22, 0)),
        )
    ]
    for weekday in range(6):
        for shift in shifts:
            WeekdayShift.objects.get_or_create(company=company, weekday=weekday, shift=shift)

    kinds = {t.kind: t for t in ResourceType.objects.filter(company=company, is_default=True)}
    res = {}
    for code, name, kind, plant, fields in RESOURCES:
        res[code] = Resource.objects.get_or_create(
            company=company,
            code=code,
            defaults={
                "name": name,
                "resource_type": kinds[kind],
                "plant": plants[plant],
                "efficiency_pct": 85,
                **fields,
            },
        )[0]

    grades = {
        n: Grade.objects.get_or_create(company=company, name=n, defaults={"description": d})[0]
        for n, d in (("GG25", "Grey iron"), ("SG500", "Spheroidal graphite iron 500/7"))
    }
    customers = {
        code: Customer.objects.get_or_create(
            company=company,
            code=code,
            defaults={"name": name, "priority": prio, "state": state},
        )[0]
        for code, name, prio, state in CUSTOMERS
    }
    ops = {o.code: o for o in OperationType.objects.filter(company=company)}

    for number, name, grade, cust, kg, pour, cav, cores, rej, machined, line in PARTS:
        part, created = Part.objects.get_or_create(
            company=company,
            part_number=number,
            defaults=dict(
                name=name,
                grade=grades[grade],
                casting_weight_kg=kg,
                pouring_weight_per_mould_kg=pour,
                cavities_per_mould=cav,
                cores_per_mould=cores,
                rejection_pct=rej,
            ),
        )
        if not created:
            continue
        PartCustomer.objects.create(
            company=company, part=part, customer=customers[cust], is_default=True
        )

        def add(code, resources, _part=part, **fields):
            row = PartOperation.objects.create(
                company=company,
                part=_part,
                op_type=ops[code],
                sequence=ops[code].default_sequence,
                **fields,
            )
            row.resources.set(resources)

        furnaces = [res["F1"]] if kg > 20 else [res["F1"], res["F2"]]
        smallest = min(f.heat_kg for f in furnaces)
        per_heat = suggested_moulds_per_heat(smallest, 5, pour).value
        add(
            "core",
            [res["CM1"], res["CM2"]],
            enabled=cores > 0,
            time_value="0.8",
            time_basis="per_core",
            extra={"cores_per_mould": cores, "scrap_pct": 2},
        )
        add("moulding", [res[line]], time_basis="per_mould")
        add(
            "melting",
            furnaces,
            time_basis="per_heat",
            extra={
                "moulds_per_heat": per_heat,
                "melt_loss_pct": 5,
                "cooling_hours": 6 if kg > 20 else 3,
            },
        )
        add(
            "knockout",
            [res["KO"]],
            time_value="0.4",
            time_basis="per_piece",
            capacity_bucket="shift",
        )
        add(
            "fettling",
            [res["FT"]],
            time_value=round(kg * 0.25, 2),
            time_basis="per_piece",
            capacity_bucket="shift",
        )
        add(
            "machining",
            [res["MC"]] if machined else [],
            enabled=machined,
            time_value=round(kg * 0.15, 2),
            time_basis="per_piece",
            capacity_bucket="shift",
        )
        add(
            "packing",
            [res["PK"]],
            time_value="0.5",
            time_basis="per_piece",
            capacity_bucket="shift",
        )
        # No work centre on purpose: shows how an unconstrained operation is flagged.
        add("dispatch", [], time_value="0.1", time_basis="per_piece", capacity_bucket="day")
