from datetime import date, datetime, time

from django.utils import timezone
from rest_framework import serializers

from apps.resources.models import Resource
from apps.scheduler.models import ScheduleLine

from .models import ChangeKind, Scenario, ScenarioChange
from .params import PARAMS, to_storage
from .service import result_state


def _day(text: str) -> str:
    return date.fromisoformat(text).strftime("%d-%m-%Y")


def _stamp(text: str) -> str:
    return timezone.localtime(datetime.fromisoformat(text)).strftime("%d-%m-%Y %H:%M")


def describe(change: ScenarioChange, resources: dict[int, str], lines: dict[int, str]) -> str:
    """The change in plain words, for the list on the scenario page and the apply confirmation."""
    p = change.params
    names = ", ".join(resources.get(i, f"#{i}") for i in p.get("resources", [])) or "all resources"
    if change.kind == ChangeKind.BLOCK_RESOURCE:
        return f"Block {resources.get(p['resource'], '?')} from {_stamp(p['start'])} to {_stamp(p['end'])}"
    if change.kind == ChangeKind.CHANGE_QTY:
        return f"Make {lines.get(p['line'], 'a line')} {p['qty']:,} pieces"
    if change.kind == ChangeKind.CHANGE_DATE:
        return f"Move {lines.get(p['line'], 'a line')} to {_day(p['date'])}"
    span = _day(p["day_from"]) + (
        f" to {_day(p['day_to'])}" if p["day_to"] != p["day_from"] else ""
    )
    if change.kind == ChangeKind.EXTRA_SHIFT:
        return f"Extra shift “{p['name']}” {p['start_time'][:5]}-{p['end_time'][:5]} on {span} for {names}"
    return f"Overtime of {p['minutes']} min on {span} for {names}"


class ChangeSerializer(serializers.ModelSerializer):
    text = serializers.SerializerMethodField()

    class Meta:
        model = ScenarioChange
        fields = ["id", "kind", "params", "text"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        kind = attrs["kind"]
        inner = PARAMS[ChangeKind(kind)](data=attrs.get("params") or {}, context=self.context)
        if not inner.is_valid():
            raise serializers.ValidationError({"params": inner.errors})
        attrs["params"] = to_storage(inner.validated_data)
        return attrs

    def get_text(self, change):
        cache = self.context.get("_labels")
        if cache is None:
            company = change.scenario.company
            cache = (
                {r.pk: r.code for r in Resource.objects.for_company(company)},
                {
                    ln.pk: f"{ln.part.part_number} for {ln.customer.code} (due {ln.internal_dispatch_date:%d-%m-%Y})"
                    for ln in ScheduleLine.objects.for_company(company).select_related(
                        "part", "customer"
                    )
                },
            )
            self.context["_labels"] = cache
        return describe(change, *cache)


class ScenarioSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source="created_by.username", read_only=True, default=None
    )
    applied_by_name = serializers.CharField(
        source="applied_by.username", read_only=True, default=None
    )
    state = serializers.SerializerMethodField()
    change_count = serializers.SerializerMethodField()
    headline = serializers.SerializerMethodField()

    class Meta:
        model = Scenario
        fields = [
            "id", "name", "notes", "status", "state", "created_by_name", "created_at", "last_run_at",
            "applied_at", "applied_by_name", "change_count", "headline",
        ]  # fmt: skip
        read_only_fields = ["status", "last_run_at", "applied_at"]

    def get_state(self, scenario):
        return result_state(scenario)

    def get_change_count(self, scenario):
        return len(scenario.changes.all())

    def get_headline(self, scenario):
        diff = (scenario.result or {}).get("diff")
        return diff["counts"] if diff else None


class ScenarioDetailSerializer(ScenarioSerializer):
    changes = serializers.SerializerMethodField()
    result = serializers.JSONField(read_only=True)

    class Meta(ScenarioSerializer.Meta):
        fields = [*ScenarioSerializer.Meta.fields, "changes", "result"]

    def get_changes(self, scenario):
        context = self.context
        return ChangeSerializer(
            scenario.changes.all().order_by("order", "id"), many=True, context=context
        ).data


__all__ = ["ScenarioSerializer", "ScenarioDetailSerializer", "ChangeSerializer", "time"]
