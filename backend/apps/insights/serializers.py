from rest_framework import serializers

from .models import Insight, InsightRun


class InsightRunSerializer(serializers.ModelSerializer):
    plan_version = serializers.IntegerField(source="plan.version", read_only=True, default=None)
    plan_status = serializers.CharField(source="plan.status", read_only=True, default=None)

    class Meta:
        model = InsightRun
        fields = ["id", "created_at", "trigger", "counts", "plan", "plan_version", "plan_status"]


class InsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insight
        fields = [
            "id", "key", "type", "severity", "title", "message", "numbers", "entities", "action",
            "why", "impact", "rank", "trend", "run", "created_at",
        ]  # fmt: skip
