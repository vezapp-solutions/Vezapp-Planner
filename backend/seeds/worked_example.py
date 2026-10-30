"""The PROMPT.md section 7.5 worked example as master data (synthetic).

2 shifts of 8 h with a 30 min break (900 min a day), efficiency 85%, part H-120 "Housing":
2 cavities, 2 cores per mould, 60 kg poured per mould, furnace F1 of 1,000 kg and 75 min per heat,
5% melt loss, knockout 0.5 min per piece, fettling 3 min per piece on 3 units, 4 h cooling.
"""

from datetime import time

from apps.companies.models import CompanySettings, Plant, Shift, WeekdayShift
from apps.masters.models import Customer, Grade, OperationType, Part, PartCustomer, PartOperation
from apps.resources.models import Resource, ResourceType


def build_worked_example(company):
    plant, _ = Plant.objects.get_or_create(company=company, name="Main Plant")
    CompanySettings.objects.get_or_create(company=company)

    shifts = [
        Shift.objects.get_or_create(
            company=company, name=name,
            defaults={"start_time": start, "end_time": end, "break_minutes": 30},
        )[0]
        for name, start, end in (("Shift 1", time(6, 0), time(14, 0)), ("Shift 2", time(14, 0), time(22, 0)))
    ]  # fmt: skip
    for weekday in range(6):  # Monday to Saturday; Sunday is the weekly off
        for shift in shifts:
            WeekdayShift.objects.get_or_create(company=company, weekday=weekday, shift=shift)

    types = {t.kind: t for t in ResourceType.objects.filter(company=company, is_default=True)}

    def resource(code, name, kind, **fields):
        return Resource.objects.get_or_create(
            company=company, code=code,
            defaults={"name": name, "resource_type": types[kind], "plant": plant, "efficiency_pct": 85, **fields},
        )[0]  # fmt: skip

    cm1 = resource("CM1", "Core machine 1", "core_machine", rate_per_hour=60)
    line_a = resource("LINE-A", "Moulding line A", "moulding_line", rate_per_hour=40)
    f1 = resource("F1", "Induction furnace 1", "furnace", heat_kg=1000, heat_minutes=75)
    ko = resource("KO", "Knockout", "work_centre")
    ft = resource("FT", "Fettling", "work_centre", units=3)

    grade, _ = Grade.objects.get_or_create(
        company=company, name="GG25", defaults={"description": "Grey iron"}
    )
    customer, _ = Customer.objects.get_or_create(
        company=company, code="CUST-01",
        defaults={"name": "Demo Pumps Pvt Ltd (synthetic)", "priority": "A", "state": "Gujarat"},
    )  # fmt: skip
    part, created = Part.objects.get_or_create(
        company=company, part_number="H-120",
        defaults=dict(
            name="Housing", grade=grade, casting_weight_kg=25, finished_weight_kg=23,
            pouring_weight_per_mould_kg=60, cavities_per_mould=2, cores_per_mould=2, rejection_pct=5,
        ),
    )  # fmt: skip
    if created:
        PartCustomer.objects.create(company=company, part=part, customer=customer, is_default=True)
        ops = {o.code: o for o in OperationType.objects.filter(company=company)}

        def op(code, resources, **fields):
            row = PartOperation.objects.create(
                company=company,
                part=part,
                op_type=ops[code],
                sequence=ops[code].default_sequence,
                **fields,
            )
            row.resources.set(resources)

        op("core", [cm1], time_value=1, time_basis="per_core", extra={"cores_per_mould": 2})
        op("moulding", [line_a], time_value="1.5", time_basis="per_mould")
        op("melting", [f1], time_value=75, time_basis="per_heat",
           extra={"moulds_per_heat": 15, "melt_loss_pct": 5, "cooling_hours": 4})  # fmt: skip
        op("knockout", [ko], time_value="0.5", time_basis="per_piece", capacity_bucket="shift")
        op("fettling", [ft], time_value=3, time_basis="per_piece", capacity_bucket="shift")
        for code in ("machining", "packing", "dispatch"):
            op(
                code,
                [],
                enabled=False,
                time_basis="per_piece",
                capacity_bucket=ops[code].default_bucket,
            )
    return {
        "part": part,
        "furnace": f1,
        "line": line_a,
        "fettling": ft,
        "knockout": ko,
        "core": cm1,
        "shifts": shifts,
    }


def ensure_worked_example_line(company, today=None):
    """The section 7.5 order itself: 600 pieces of H-120, due two weeks from today. Safe to re-run."""
    from datetime import date, timedelta

    from apps.scheduler.models import ScheduleLine

    part = Part.objects.get(company=company, part_number="H-120")
    customer = Customer.objects.get(company=company, code="CUST-01")
    remark = "Section 7.5 worked example"
    if ScheduleLine.objects.filter(company=company, remarks=remark).exists():
        return
    due = (today or date.today()) + timedelta(days=14)
    ScheduleLine.objects.create(
        company=company, customer=customer, part=part, dispatch_qty=600,
        internal_dispatch_date=due, remarks=remark,
    )  # fmt: skip
