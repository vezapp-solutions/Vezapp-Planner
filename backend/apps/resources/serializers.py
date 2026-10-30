from rest_framework import serializers

from apps.companies.models import Plant, Shift
from apps.core.fields import CompanyPKField, CompanyUniqueMixin
from apps.core.validation import advisories, raise_on_errors
from planning.checks import check_resource

from .adjustments import MAX_RANGE_DAYS, extra_shift_problem
from .models import AdjustmentKind, CapacityAdjustment, Downtime, Kind, Resource, ResourceType

RATED_FIELDS = [
    "rate_per_hour",
    "cycle_seconds",
    "cores_per_shot",
    "heat_kg",
    "heat_minutes",
    "max_heats_per_shift",
]


def _n(value):
    return f"{value.normalize():f}" if value is not None else ""


def rated_summary(resource: Resource) -> str:
    kind = resource.resource_type.kind
    if kind == Kind.FURNACE:
        return f"{_n(resource.heat_kg)} kg heat · {_n(resource.heat_minutes)} min/heat"
    if kind == Kind.MOULDING_LINE and resource.rate_per_hour:
        return f"{_n(resource.rate_per_hour)} moulds/h"
    if kind == Kind.CORE_MACHINE:
        if resource.rate_per_hour:
            return f"{_n(resource.rate_per_hour)} cores/h"
        if resource.cycle_seconds and resource.cores_per_shot:
            return f"{_n(resource.cycle_seconds)} s/shot × {resource.cores_per_shot} cores"
    if kind == Kind.WORK_CENTRE:
        return f"{_n(resource.rate_per_hour)} pcs/h" if resource.rate_per_hour else "time-based"
    return ""


def resource_issues(resource: Resource):
    data = {f: getattr(resource, f) for f in RATED_FIELDS}
    data.update(
        kind=resource.resource_type.kind,
        units=resource.units,
        efficiency_pct=resource.efficiency_pct,
    )
    return check_resource(data)


class ResourceTypeSerializer(CompanyUniqueMixin, serializers.ModelSerializer):
    class Meta:
        model = ResourceType
        fields = ["id", "name", "kind", "is_default"]
        read_only_fields = ["id", "is_default"]

    def validate_name(self, value):
        return self._unique_in_company(
            ResourceType, "name", value, "This name is already used.", ignore_case=True
        )

    def validate_kind(self, value):
        if (
            self.instance is not None
            and self.instance.kind != value
            and self.instance.resources.exists()
        ):
            raise serializers.ValidationError(
                "The kind cannot change while resources use this type."
            )
        return value


class ResourceSerializer(CompanyUniqueMixin, serializers.ModelSerializer):
    resource_type = CompanyPKField(queryset=ResourceType.objects.all())
    plant = CompanyPKField(queryset=Plant.objects.all(), required=False, allow_null=True)
    shifts = CompanyPKField(queryset=Shift.objects.all(), many=True, required=False)
    type_name = serializers.CharField(source="resource_type.name", read_only=True)
    kind = serializers.CharField(source="resource_type.kind", read_only=True)
    rated_summary = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()

    class Meta:
        model = Resource
        fields = [
            "id", "code", "name", "resource_type", "type_name", "kind", "plant", "units", "status",
            "efficiency_pct", "remarks", *RATED_FIELDS, "shifts", "rated_summary", "warnings",
        ]  # fmt: skip
        read_only_fields = ["id"]

    def validate_code(self, value):
        return self._unique_in_company(
            Resource, "code", value, "This code is already used.", ignore_case=True
        )

    def validate(self, attrs):
        def get(key, default=None):
            return attrs.get(key, getattr(self.instance, key, default))

        resource_type = get("resource_type")
        data = {f: get(f) for f in RATED_FIELDS}
        data.update(
            kind=resource_type.kind,
            units=get("units", 1),
            efficiency_pct=get("efficiency_pct", 100),
        )
        raise_on_errors(check_resource(data))
        return attrs

    def get_rated_summary(self, resource):
        return rated_summary(resource)

    def get_warnings(self, resource):
        return advisories(resource_issues(resource))


class DowntimeSerializer(serializers.ModelSerializer):
    resource = CompanyPKField(queryset=Resource.objects.all())

    class Meta:
        model = Downtime
        fields = ["id", "resource", "start_at", "end_at", "reason"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        start = attrs.get("start_at", getattr(self.instance, "start_at", None))
        end = attrs.get("end_at", getattr(self.instance, "end_at", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end_at": "The end must be after the start."})
        return attrs


class CapacityAdjustmentSerializer(serializers.ModelSerializer):
    shift = CompanyPKField(queryset=Shift.objects.all(), required=False, allow_null=True)
    resources = CompanyPKField(queryset=Resource.objects.all(), many=True, required=False)
    summary = serializers.SerializerMethodField()

    class Meta:
        model = CapacityAdjustment
        fields = [
            "id", "kind", "day_from", "day_to", "name", "start_time", "end_time", "break_minutes",
            "shift", "minutes", "resources", "note", "summary",
        ]  # fmt: skip
        read_only_fields = ["id"]

    def get_summary(self, adj):
        days = f"{adj.day_from:%d-%m-%Y}" + (
            f" to {adj.day_to:%d-%m-%Y}" if adj.day_to != adj.day_from else ""
        )
        if adj.kind == AdjustmentKind.EXTRA_SHIFT:
            return f"{adj.name}, {adj.start_time:%H:%M}-{adj.end_time:%H:%M}, {days}"
        return f"Overtime of {adj.minutes} min, {days}"

    def validate(self, attrs):
        def get(key, default=None):
            return attrs.get(key, getattr(self.instance, key, default))

        kind, day_from, day_to = get("kind"), get("day_from"), get("day_to")
        if day_to < day_from:
            raise serializers.ValidationError(
                {"day_to": "The last day cannot be before the first day."}
            )
        if (day_to - day_from).days + 1 > MAX_RANGE_DAYS:
            raise serializers.ValidationError({"day_to": f"Choose at most {MAX_RANGE_DAYS} days."})
        if kind == AdjustmentKind.EXTRA_SHIFT:
            if not get("name"):
                raise serializers.ValidationError({"name": "Give the shift a name."})
            if not get("start_time") or not get("end_time"):
                raise serializers.ValidationError({"start_time": "Give the start and end time."})
            problem = extra_shift_problem(
                self.context.get("company"), day_from, day_to, get("start_time"), get("end_time"),
                get("break_minutes") or 0, exclude_id=getattr(self.instance, "pk", None),
            )  # fmt: skip
            if problem:
                raise serializers.ValidationError({"end_time": problem})
            attrs.update(shift=None, minutes=None)
        else:
            minutes = get("minutes")
            if not minutes or not (1 <= minutes <= 480):
                raise serializers.ValidationError({"minutes": "Enter 1 to 480 minutes."})
            attrs.update(name="", start_time=None, end_time=None, break_minutes=0)
        return attrs
