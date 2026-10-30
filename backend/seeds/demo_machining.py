"""Machine types, machines and two-operation machining routes for Foundry A (synthetic). Safe to re-run."""

from apps.companies.models import Plant, Shift
from apps.masters.models import OperationType, Part, PartOperation
from apps.resources.models import Resource, ResourceType

MACHINES = [
    # code, name, type, works only the first shift
    ("VMC-1", "Vertical machining centre 1", "VMC", False),
    ("VMC-2", "Vertical machining centre 2", "VMC", False),
    ("CNC-1", "CNC turning centre 1", "CNC", False),
    ("CNC-2", "CNC turning centre 2", "CNC", True),
    ("HMC-1", "Horizontal machining centre 1", "HMC", False),
]


def ensure_demo_machining(company):
    """The machines, and for each machined part OP10 rough milling (VMC or HMC) and OP20 finish
    bore (CNC), each with its own times and setup."""
    machining = OperationType.objects.filter(company=company, code="machining").first()
    if machining is None:
        return
    types = {
        name: ResourceType.objects.get_or_create(
            company=company, name=name, defaults={"kind": "work_centre"}
        )[0]
        for name in ("VMC", "CNC", "HMC")
    }
    plant = Plant.objects.filter(company=company).first()
    first_shift = Shift.objects.filter(company=company).order_by("start_time").first()
    for code, name, type_name, one_shift in MACHINES:
        machine, created = Resource.objects.get_or_create(
            company=company,
            code=code,
            defaults={
                "name": name,
                "resource_type": types[type_name],
                "plant": plant,
                "efficiency_pct": 85,
            },
        )
        if created and one_shift and first_shift:
            machine.shifts.set([first_shift])

    for part in Part.objects.filter(company=company):
        base = PartOperation.objects.filter(
            part=part, op_type=machining, step=0, enabled=True
        ).first()
        if base is None or part.operations.filter(op_type=machining, step__gt=0).exists():
            continue
        kg = float(part.casting_weight_kg)
        base.step, base.label, base.sequence, base.setup_minutes = 10, "Rough milling", 61, 40
        base.time_value = round(kg * 0.2, 2)
        base.extra = {
            "machine_types": sorted([types["VMC"].pk, types["HMC"].pk]),
            "time_by_type": {
                str(types["VMC"].pk): round(kg * 0.2, 2),
                str(types["HMC"].pk): round(kg * 0.12, 2),
            },
        }
        base.save()
        base.resources.clear()
        PartOperation.objects.create(
            company=company, part=part, op_type=machining, step=20, label="Finish bore", sequence=62,
            time_value=round(kg * 0.1, 2), time_basis="per_piece", capacity_bucket="shift", setup_minutes=25,
            extra={"machine_types": [types["CNC"].pk]},
        )  # fmt: skip
