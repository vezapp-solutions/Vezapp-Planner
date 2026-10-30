from collections import defaultdict

from rest_framework import serializers

from .models import Plan, PlanLine, PlanOperation
from .service import stale_reasons


class PlanSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source="created_by.username", read_only=True, default=None
    )
    bottleneck = serializers.SerializerMethodField()
    stale_reasons = serializers.SerializerMethodField()
    stale = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = [
            "id", "version", "status", "plan_from", "calculated_at", "confirmed_at", "summary",
            "settings_snapshot", "bottleneck", "stale", "stale_reasons", "created_by_name", "created_at",
        ]  # fmt: skip

    def get_bottleneck(self, plan):
        r = plan.bottleneck_resource
        return {"id": r.pk, "code": r.code, "name": r.name} if r else None

    def _reasons(self, plan):
        cache = self.context.setdefault("_reasons", {})
        if plan.pk not in cache:
            cache[plan.pk] = stale_reasons(plan)
        return cache[plan.pk]

    def get_stale_reasons(self, plan):
        return self._reasons(plan)

    def get_stale(self, plan):
        return bool(self._reasons(plan))


class PlanLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanLine
        fields = [
            "id", "schedule_line", "customer_code", "customer_name", "part_number", "part_name",
            "qty", "internal_date", "priority", "status", "est_dispatch_date", "slack_working_days",
            "holding_op", "holding_text", "notes",
        ]  # fmt: skip


class PlanOperationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanOperation
        fields = [
            "code", "name", "kind", "sequence", "minutes", "units", "ready_at", "start_at", "finish_at",
            "latest_start", "latest_finish", "delay_days", "wait_hours", "capacity_modelled",
            "outsourced", "complete", "resource_codes",
        ]  # fmt: skip


class PlanLineDetailSerializer(PlanLineSerializer):
    finish_at = serializers.DateTimeField(read_only=True)
    requirement = serializers.JSONField(read_only=True)
    operations = PlanOperationSerializer(many=True, read_only=True)
    allocations = serializers.SerializerMethodField()

    class Meta(PlanLineSerializer.Meta):
        fields = [
            *PlanLineSerializer.Meta.fields,
            "finish_at",
            "requirement",
            "operations",
            "allocations",
        ]

    def get_allocations(self, line):
        """Where each operation ran: minutes and quantity per resource and shift."""
        grouped: dict[tuple, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        for a in line.allocations.all():
            s = a.slot
            key = (
                a.op_code,
                a.resource.code if a.resource else "",
                s.slot_date,
                s.shift_name,
                s.start,
                s.end,
            )
            grouped[key][0] += a.minutes
            grouped[key][1] += a.qty
            grouped[key][2] += a.setup_minutes
        return [
            {
                "op_code": op, "resource": res or None, "date": day, "shift": shift,
                "start": start, "end": end, "minutes": round(v[0], 2), "qty": round(v[1], 2),
                "setup_minutes": round(v[2], 2),
            }
            for (op, res, day, shift, start, end), v in sorted(grouped.items(), key=lambda kv: (kv[0][4], kv[0][0], kv[0][1]))
        ]  # fmt: skip
