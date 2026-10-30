"""What each kind of what-if change must carry, validated against the company's own rows."""

from datetime import date, datetime, time
from typing import Any

from rest_framework import serializers

from apps.companies.models import Shift
from apps.core.fields import CompanyPKField
from apps.resources.adjustments import MAX_RANGE_DAYS, extra_shift_problem
from apps.resources.models import Resource
from apps.scheduler.models import LineStatus, ScheduleLine

from .models import ChangeKind

PLANNABLE = ScheduleLine.objects.filter(status__in=[LineStatus.PLANNED, LineStatus.IN_PROGRESS])


class BlockParams(serializers.Serializer):
    resource = CompanyPKField(queryset=Resource.objects.all())
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")

    def validate(self, attrs):
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError({"end": "The end must be after the start."})
        return attrs


class QtyParams(serializers.Serializer):
    line = CompanyPKField(queryset=PLANNABLE)
    qty = serializers.IntegerField(min_value=1, max_value=10_000_000)


class DateParams(serializers.Serializer):
    line = CompanyPKField(queryset=PLANNABLE)
    date = serializers.DateField()


class _Range(serializers.Serializer):
    day_from = serializers.DateField()
    day_to = serializers.DateField()

    def validate(self, attrs):
        if attrs["day_to"] < attrs["day_from"]:
            raise serializers.ValidationError(
                {"day_to": "The last day cannot be before the first day."}
            )
        if (attrs["day_to"] - attrs["day_from"]).days + 1 > MAX_RANGE_DAYS:
            raise serializers.ValidationError({"day_to": f"Choose at most {MAX_RANGE_DAYS} days."})
        return attrs


class ExtraShiftParams(_Range):
    name = serializers.CharField(max_length=60)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    break_minutes = serializers.IntegerField(min_value=0, max_value=240, default=0)
    resources = CompanyPKField(queryset=Resource.objects.all(), many=True, required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        problem = extra_shift_problem(
            self.context.get("company"), attrs["day_from"], attrs["day_to"], attrs["start_time"],
            attrs["end_time"], attrs["break_minutes"],
        )  # fmt: skip
        if problem:
            raise serializers.ValidationError({"end_time": problem})
        return attrs


class OvertimeParams(_Range):
    minutes = serializers.IntegerField(min_value=1, max_value=480)
    shift = CompanyPKField(queryset=Shift.objects.all(), required=False, allow_null=True)
    resources = CompanyPKField(queryset=Resource.objects.all(), many=True, required=False)


PARAMS = {
    ChangeKind.BLOCK_RESOURCE: BlockParams,
    ChangeKind.CHANGE_QTY: QtyParams,
    ChangeKind.CHANGE_DATE: DateParams,
    ChangeKind.EXTRA_SHIFT: ExtraShiftParams,
    ChangeKind.OVERTIME: OvertimeParams,
}


def to_storage(value: Any) -> Any:
    """Plain JSON for the database: ids instead of rows, ISO text instead of dates and times."""
    if hasattr(value, "pk"):
        return value.pk
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [to_storage(v) for v in value]
    if isinstance(value, dict):
        return {k: to_storage(v) for k, v in value.items()}
    return value
