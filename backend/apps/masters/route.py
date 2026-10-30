"""A part's operation route: building the editable view (with derived values and advisories) and saving it."""

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.companies.models import CompanySettings
from apps.core.fields import CompanyPKField
from apps.resources.models import Kind, Resource, ResourceType
from planning.checks import RESOURCE_KIND_FOR, TIME_BASES_FOR, Issue, check_operation
from planning.derive import (
    core_minutes_per_core,
    minutes_per_piece,
    moulding_minutes_per_mould,
    suggested_moulds_per_heat,
)
from planning.model import step_code
from planning.trace import Traced

from .machines import (
    allowed_ids,
    engine_extra,
    engine_extra_of,
    except_ids,
    machines_by_type,
    times_by_type,
    type_ids,
)
from .models import Bucket, OperationType, PartOperation, TimeBasis

EXTRA_KEYS = {
    "core": {"cores_per_mould", "scrap_pct", "lead_hours"},
    "moulding": {"cavities_per_mould"},
    "melting": {"moulds_per_heat", "melt_loss_pct", "cooling_hours"},
    "post": set(),
}
DEFAULT_BASIS = {
    "core": "per_core",
    "moulding": "per_mould",
    "melting": "per_heat",
    "post": "per_piece",
}


def _part_data(part):
    return {
        "pouring_weight_per_mould_kg": part.pouring_weight_per_mould_kg,
        "casting_weight_kg": part.casting_weight_kg,
        "cavities_per_mould": part.cavities_per_mould,
        "cores_per_mould": part.cores_per_mould,
    }


def _number(value):
    return None if value is None else (float(value) if isinstance(value, Decimal) else value)


def _derive(row, part, resources, default_melt_loss):
    kind, extra = row["kind"], row["extra"]
    out = {}
    if kind == "core":
        machine = next(
            (r for r in resources if r.rate_per_hour or (r.cycle_seconds and r.cores_per_shot)),
            None,
        )
        out["minutes_per_core"] = core_minutes_per_core(
            row["time_value"],
            machine.rate_per_hour if machine else None,
            machine.cycle_seconds if machine else None,
            machine.cores_per_shot if machine else None,
        )
        out["cores_per_mould"] = (
            Traced(extra["cores_per_mould"], "entered on this operation")
            if extra.get("cores_per_mould") is not None
            else Traced(part.cores_per_mould, "taken from the Part Master")
        )
    elif kind == "moulding":
        line = next((r for r in resources if r.rate_per_hour), None)
        out["minutes_per_mould"] = moulding_minutes_per_mould(
            row["time_value"], line.rate_per_hour if line else None
        )
        out["cavities_per_mould"] = (
            Traced(extra["cavities_per_mould"], "entered on this operation")
            if extra.get("cavities_per_mould") is not None
            else Traced(part.cavities_per_mould, "taken from the Part Master")
        )
    elif kind == "melting":
        loss_entered = extra.get("melt_loss_pct")
        loss = loss_entered if loss_entered is not None else default_melt_loss
        out["melt_loss_pct"] = Traced(
            loss,
            "entered on this operation"
            if loss_entered is not None
            else "company default (none entered)",
        )
        furnaces = [r for r in resources if r.heat_kg]
        suggestions = [
            (r, suggested_moulds_per_heat(r.heat_kg, loss, part.pouring_weight_per_mould_kg))
            for r in furnaces
        ]
        out["per_furnace"] = [{"code": r.code, **s.as_dict()} for r, s in suggestions]
        smallest = min(suggestions, key=lambda rs: rs[0].heat_kg, default=None)
        suggested = smallest[1] if smallest else Traced(None, "no allowed furnace with a heat size")
        out["suggested_moulds_per_heat"] = suggested
        moulds = extra.get("moulds_per_heat")
        effective_moulds = moulds if moulds is not None else suggested.value
        minutes_heat = (
            row["time_value"]
            if row["time_value"] is not None
            else (smallest[0].heat_minutes if smallest else None)
        )
        out["minutes_per_heat"] = Traced(
            minutes_heat,
            "entered on this operation"
            if row["time_value"] is not None
            else "taken from the furnace",
        )
        cavities = extra.get("cavities_per_mould", part.cavities_per_mould)
        out["minutes_per_piece"] = (
            minutes_per_piece(minutes_heat, effective_moulds, cavities)
            if minutes_heat and effective_moulds
            else Traced(None, "needs minutes per heat and moulds per heat")
        )
    return {k: (v.as_dict() if isinstance(v, Traced) else v) for k, v in out.items()}


def _row(optype, saved, part, default_melt_loss, by_type=None, all_resources=None):
    """One route row as a dict: from a saved PartOperation, or a not-yet-saved template row."""
    by_type = by_type if by_type is not None else machines_by_type(part.company)
    if all_resources is None:
        all_resources = {
            r.pk: r
            for r in Resource.objects.for_company(part.company).select_related("resource_type")
        }
    if saved is not None:
        chosen = list(saved.resources.all())
        effective = [all_resources[i] for i in allowed_ids(saved, by_type) if i in all_resources]
        row = {
            "id": saved.pk, "enabled": saved.enabled, "sequence": saved.sequence,
            "time_value": _number(saved.time_value), "time_basis": saved.time_basis,
            "batch_size": saved.batch_size, "capacity_bucket": saved.capacity_bucket,
            "lag_hours": _number(saved.lag_hours), "outsourced": saved.outsourced,
            "lead_days": saved.lead_days, "extra": engine_extra(saved),
            "step": saved.step, "label": saved.label, "setup_minutes": _number(saved.setup_minutes),
            "machine_types": type_ids(saved), "except_ids": except_ids(saved),
            "time_by_type": {str(k): float(v) for k, v in times_by_type(saved).items()},
        }  # fmt: skip
    else:
        chosen, effective = [], []
        row = {
            "id": None,
            "enabled": optype.default_enabled and not (optype.kind == "core" and part.cores_per_mould == 0),
            "sequence": optype.default_sequence, "time_value": None,
            "time_basis": DEFAULT_BASIS[optype.kind], "batch_size": None,
            "capacity_bucket": optype.default_bucket if optype.kind == "post" else "",
            "lag_hours": 0, "outsourced": False, "lead_days": None, "extra": {},
            "step": 0, "label": "", "setup_minutes": 0, "machine_types": [], "except_ids": [],
            "time_by_type": {},
        }  # fmt: skip
    row.update(
        op_type=optype.pk, code=step_code(optype.code, row["step"]), type_code=optype.code,
        name=optype.name, kind=optype.kind, multi_step=optype.multi_step,
        resource_kind=RESOURCE_KIND_FOR[optype.kind], allowed_time_bases=list(TIME_BASES_FOR[optype.kind]),
        resource_ids=[r.pk for r in chosen], effective_resource_ids=[r.pk for r in effective],
    )  # fmt: skip
    issues = check_operation(
        {**row, "resource_count": len(effective)},
        _part_data(part),
        [{"heat_kg": r.heat_kg, "heat_minutes": r.heat_minutes} for r in effective if r.heat_kg],
    )
    if optype.multi_step and row["machine_types"]:
        for type_id in row["machine_types"]:
            if not by_type.get(type_id):
                issues.append(
                    Issue(
                        "warning",
                        "machine_types",
                        "There is no machine of one of the chosen types yet.",
                    )
                )
                break
        missing = [
            str(t) for t in row["machine_types"]
            if str(t) not in row["time_by_type"] and row["time_value"] is None
        ]  # fmt: skip
        if missing:
            issues.append(
                Issue(
                    "error",
                    "time_value",
                    "Give a time for every machine type, or a default time for the operation.",
                )
            )
    row["derived"] = _derive(row, part, effective, default_melt_loss)
    row["issues"] = [i.as_dict() for i in issues]
    row["capacity_modelled"] = (
        bool(effective) and not row["outsourced"] if row["kind"] == "post" else bool(effective)
    )
    return row


def describe_route(part) -> dict:
    default_loss = CompanySettings.objects.get_or_create(company=part.company)[
        0
    ].melt_loss_default_pct
    saved: dict[int, list[PartOperation]] = {}
    for op in (
        part.operations.select_related("op_type").prefetch_related("resources").order_by("step")
    ):
        saved.setdefault(op.op_type_id, []).append(op)
    by_type = machines_by_type(part.company)
    all_resources = {
        r.pk: r for r in Resource.objects.for_company(part.company).select_related("resource_type")
    }

    def build(optype, op):
        return _row(optype, op, part, default_loss, by_type, all_resources)

    types = OperationType.objects.for_company(part.company).filter(is_active=True)
    rows = []
    for t in types:
        # An operation that may be routed several times shows each saved step; the rest show one row.
        for op in saved.get(t.pk) or [None]:
            rows.append(build(t, op))
    # An operation switched off later still shows if the part has it saved.
    rows += [
        build(ops[0].op_type, op)
        for ops in saved.values()
        for op in ops
        if not ops[0].op_type.is_active
    ]
    rows.sort(key=lambda r: (r["sequence"], r["step"], r["name"]))
    return {"part": part.pk, "is_template": not saved, "operations": rows}


class RouteItemSerializer(serializers.Serializer):
    op_type = CompanyPKField(queryset=OperationType.objects.all())
    sequence = serializers.IntegerField(min_value=1, max_value=999)
    enabled = serializers.BooleanField()
    time_value = serializers.DecimalField(
        max_digits=10, decimal_places=4, required=False, allow_null=True
    )
    time_basis = serializers.ChoiceField(choices=TimeBasis.choices, required=False)
    batch_size = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    capacity_bucket = serializers.ChoiceField(
        choices=Bucket.choices, required=False, allow_blank=True
    )
    lag_hours = serializers.DecimalField(max_digits=7, decimal_places=2, required=False, default=0)
    outsourced = serializers.BooleanField(required=False, default=False)
    lead_days = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    extra = serializers.DictField(required=False, default=dict)
    resource_ids = CompanyPKField(queryset=Resource.objects.all(), many=True, required=False)
    # Several steps of one operation (machining) and the choice of machines for a step.
    step = serializers.IntegerField(min_value=0, max_value=999, required=False, default=0)
    label = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    setup_minutes = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=0, required=False, default=0
    )
    machine_types = CompanyPKField(queryset=ResourceType.objects.all(), many=True, required=False)
    except_ids = CompanyPKField(queryset=Resource.objects.all(), many=True, required=False)
    time_by_type = serializers.DictField(
        child=serializers.DecimalField(max_digits=10, decimal_places=4, min_value=0),
        required=False,
        default=dict,
    )

    def validate_extra(self, value):
        cleaned = {}
        for key, raw in value.items():
            if raw in (None, ""):
                continue
            try:
                number = float(raw)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(f"{key} must be a number.") from exc
            cleaned[key] = (
                int(number)
                if key in {"cores_per_mould", "cavities_per_mould", "moulds_per_heat"}
                and number == int(number)
                else number
            )
        return cleaned

    def validate(self, attrs):
        optype = attrs["op_type"]
        kind = optype.kind
        unknown = set(attrs.get("extra", {})) - EXTRA_KEYS[kind]
        if unknown:
            raise serializers.ValidationError(
                {"extra": f"Not a setting of this operation: {', '.join(sorted(unknown))}."}
            )
        attrs.setdefault("time_basis", DEFAULT_BASIS[kind])
        if kind != "post":
            attrs["capacity_bucket"] = ""
        else:
            attrs["capacity_bucket"] = attrs.get("capacity_bucket") or optype.default_bucket

        wrong = [
            r.code
            for r in attrs.get("resource_ids", [])
            if r.resource_type.kind != RESOURCE_KIND_FOR[kind]
        ]
        if wrong:
            raise serializers.ValidationError(
                {"resource_ids": f"{', '.join(wrong)} cannot be used for this operation."}
            )

        # --- steps and machine choice (machining) ---------------------------------------------
        types = list(attrs.get("machine_types", []))
        excluded = list(attrs.get("except_ids", []))
        by_type_time = dict(attrs.get("time_by_type", {}))
        if attrs.get("step") and not optype.multi_step:
            raise serializers.ValidationError(
                {"step": f"{optype.name} cannot be routed more than once."}
            )
        if kind != "post" and (
            types or excluded or by_type_time or attrs.get("setup_minutes") or attrs.get("label")
        ):
            raise serializers.ValidationError(
                {
                    "machine_types": "Machine types, setup and times by type belong to post-casting operations."
                }
            )
        bad_types = [t.name for t in types if t.kind != Kind.WORK_CENTRE]
        if bad_types:
            raise serializers.ValidationError(
                {
                    "machine_types": f"{', '.join(bad_types)} is not a work-centre type, so it has no machines to choose."
                }
            )
        valid_types = {
            str(t.pk)
            for t in ResourceType.objects.for_company(self.context["part"].company).filter(
                kind=Kind.WORK_CENTRE
            )
        }
        unknown = [k for k in by_type_time if str(k) not in valid_types]
        if unknown:
            raise serializers.ValidationError(
                {"time_by_type": "A time was given for a machine type that does not exist."}
            )
        part = self.context["part"]
        # Every machine type the step may use needs a time: its own, or the step's default.
        chosen_types = {t.pk: t.name for t in types} | {
            r.resource_type_id: r.resource_type.name for r in attrs.get("resource_ids", [])
        }
        uncovered = [
            name for pk, name in chosen_types.items()
            if str(pk) not in {str(k) for k in by_type_time} and attrs.get("time_value") is None
        ]  # fmt: skip
        if kind == "post" and not attrs["outsourced"] and by_type_time and uncovered:
            raise serializers.ValidationError(
                {
                    "time_by_type": f"Give a time for {', '.join(uncovered)}, or a default time for the operation."
                }
            )
        extra_keys = dict(attrs.get("extra", {}))
        if types:
            extra_keys["machine_types"] = sorted(t.pk for t in types)
        if excluded:
            extra_keys["except"] = sorted(r.pk for r in excluded)
        if by_type_time:
            extra_keys["time_by_type"] = {str(k): float(v) for k, v in by_type_time.items()}
        attrs["extra"] = extra_keys  # one place for the settings of a step: saved as it stands
        suitable = len(attrs.get("resource_ids", [])) + (
            Resource.objects.for_company(part.company)
            .filter(resource_type__in=types)
            .exclude(pk__in=[r.pk for r in excluded])
            .count()
            if types
            else 0
        )
        issues = check_operation(
            {
                "kind": kind, "code": optype.code, "enabled": attrs["enabled"],
                "time_value": attrs.get("time_value"), "time_basis": attrs["time_basis"],
                "batch_size": attrs.get("batch_size"), "lag_hours": attrs.get("lag_hours"),
                "outsourced": attrs["outsourced"], "lead_days": attrs.get("lead_days"),
                "extra": engine_extra_of(extra_keys), "resource_count": suitable,
                "time_by_type": by_type_time,
            },
            _part_data(part),
            [{"heat_kg": r.heat_kg} for r in attrs.get("resource_ids", []) if r.heat_kg],
        )  # fmt: skip
        errors = {}
        for issue in issues:
            if issue.level == "error":
                errors.setdefault(issue.field, []).append(issue.message)
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class RouteSerializer(serializers.Serializer):
    operations = RouteItemSerializer(many=True)

    def validate_operations(self, items):
        seen = [(i["op_type"].pk, i.get("step", 0)) for i in items]
        if len(seen) != len(set(seen)):
            raise serializers.ValidationError("An operation is listed twice with the same number.")
        return items


@transaction.atomic
def save_route(part, items):
    keep = []
    for item in items:
        op, _ = PartOperation.objects.update_or_create(
            part=part,
            op_type=item["op_type"],
            step=item.get("step", 0),
            defaults={
                "company": part.company,
                "sequence": item["sequence"],
                "enabled": item["enabled"],
                "time_value": item.get("time_value"),
                "time_basis": item["time_basis"],
                "batch_size": item.get("batch_size"),
                "capacity_bucket": item["capacity_bucket"],
                "lag_hours": item.get("lag_hours") or 0,
                "outsourced": item["outsourced"],
                "lead_days": item.get("lead_days"),
                "extra": item.get("extra", {}),
                "label": item.get("label", ""),
                "setup_minutes": item.get("setup_minutes") or 0,
            },
        )
        op.resources.set(item.get("resource_ids", []))
        keep.append(op.pk)
    part.operations.exclude(pk__in=keep).delete()


@transaction.atomic
def copy_route(source, target):
    target.operations.all().delete()
    for op in source.operations.prefetch_related("resources"):
        clone = PartOperation.objects.create(
            company=target.company, part=target, op_type=op.op_type, sequence=op.sequence,
            enabled=op.enabled, time_value=op.time_value, time_basis=op.time_basis,
            batch_size=op.batch_size, capacity_bucket=op.capacity_bucket, lag_hours=op.lag_hours,
            outsourced=op.outsourced, lead_days=op.lead_days, extra=dict(op.extra or {}),
            step=op.step, label=op.label, setup_minutes=op.setup_minutes,
        )  # fmt: skip
        clone.resources.set(op.resources.all())
