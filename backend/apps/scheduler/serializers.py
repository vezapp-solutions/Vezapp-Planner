from django.utils import timezone
from rest_framework import serializers

from apps.core.fields import CompanyPKField
from apps.masters.models import Customer, Part, PartCustomer

from .models import LineStatus, ScheduleLine, UploadBatch
from .state import order_states


class ScheduleLineSerializer(serializers.ModelSerializer):
    customer = CompanyPKField(queryset=Customer.objects.all())
    part = CompanyPKField(queryset=Part.objects.all())
    customer_code = serializers.CharField(source="customer.code", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    part_number = serializers.CharField(source="part.part_number", read_only=True)
    part_name = serializers.CharField(source="part.name", read_only=True)
    grade_name = serializers.CharField(source="part.grade.name", read_only=True, default=None)
    month = serializers.CharField(read_only=True)
    tonnes = serializers.SerializerMethodField()
    value = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()
    balance = serializers.IntegerField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    plan_state = serializers.SerializerMethodField()
    plan_reasons = serializers.SerializerMethodField()
    est_dispatch_date = serializers.SerializerMethodField()

    class Meta:
        model = ScheduleLine
        fields = [
            "id", "customer", "customer_code", "customer_name", "part", "part_number", "part_name",
            "grade_name", "dispatch_qty", "internal_dispatch_date", "actual_dispatch_date",
            "actual_dispatched_qty", "wip_qty", "fg_qty", "balance", "is_open", "plan_state",
            "plan_reasons", "est_dispatch_date", "remarks", "status", "month", "tonnes", "value",
            "warnings", "upload_batch",
        ]  # fmt: skip
        read_only_fields = ["id", "upload_batch"]

    def _links(self) -> set[tuple[int, int]]:
        cache = self.context.setdefault("_links", None)
        if cache is None:
            company = self.context.get("company")
            cache = set(
                PartCustomer.objects.for_company(company).values_list("part_id", "customer_id")
            )
            self.context["_links"] = cache
        return cache

    def _states(self, line):
        """Order states are worked out once for the whole list being serialised."""
        cache = self.context.setdefault("_states", {})
        if line.pk not in cache:
            siblings = getattr(self.parent, "instance", None) if self.parent is not None else None
            batch = list(siblings) if isinstance(siblings, (list, tuple)) else [line]
            company = self.context.get("company") or line.company
            cache.update(order_states(company, batch))
            cache.setdefault(line.pk, order_states(company, [line])[line.pk])
        return cache[line.pk]

    def get_plan_state(self, line):
        return self._states(line).state

    def get_plan_reasons(self, line):
        return self._states(line).reasons

    def get_est_dispatch_date(self, line):
        return self._states(line).est_dispatch

    def get_tonnes(self, line):
        return round(float(line.part.casting_weight_kg) * line.dispatch_qty / 1000, 3)

    def get_value(self, line):
        price = line.part.selling_price
        return None if price is None else round(float(price) * line.dispatch_qty, 2)

    def get_warnings(self, line):
        out = []
        if (line.part_id, line.customer_id) not in self._links():
            out.append("This part is not linked to this customer in the Part Master.")
        if not line.customer.is_active:
            out.append("This customer is marked inactive.")
        if not line.part.is_active:
            out.append("This part is marked inactive.")
        return out

    def validate(self, attrs):
        def get(key):
            return attrs.get(key, getattr(self.instance, key, None))

        actual_date, actual_qty, status = (
            get("actual_dispatch_date"),
            get("actual_dispatched_qty"),
            get("status") or LineStatus.PLANNED,
        )
        if actual_date and actual_date > timezone.localdate():
            raise serializers.ValidationError(
                {"actual_dispatch_date": "The actual dispatch date cannot be in the future."}
            )
        # Entering an actual date means the order has shipped, unless only part of it has gone;
        # clearing it undoes that. A dispatched quantity can be kept without a date (cumulative).
        if "actual_dispatch_date" in attrs and "status" not in attrs:
            qty = get("dispatch_qty")
            whole = actual_qty is None or (qty is not None and actual_qty >= qty)
            if actual_date and status in (LineStatus.PLANNED, LineStatus.IN_PROGRESS):
                attrs["status"] = LineStatus.DISPATCHED if whole else LineStatus.IN_PROGRESS
            elif not actual_date and status == LineStatus.DISPATCHED:
                attrs["status"] = LineStatus.PLANNED
        elif status == LineStatus.DISPATCHED and not actual_date:
            raise serializers.ValidationError(
                {"status": "A dispatched line needs an actual dispatch date."}
            )
        return attrs


class UploadBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadBatch
        fields = [
            "id", "file_name", "mode", "username", "created_at", "rows_total", "rows_inserted",
            "rows_updated", "rows_unchanged", "rows_skipped", "rows_error", "rows_warning",
            "skipped_errors",
        ]  # fmt: skip
