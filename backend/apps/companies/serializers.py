from rest_framework import serializers

from apps.accounts.roles import Role
from apps.core.fields import CompanyPKField, CompanyUniqueMixin, GSTINField
from planning.calendar import shift_minutes

from .models import Company, CompanySettings, Holiday, Plant, Shift


class CompanySerializer(serializers.ModelSerializer):
    gstin = GSTINField()

    class Meta:
        model = Company
        fields = ["id", "name", "address", "gstin", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        user = self.context["request"].user
        if "is_active" in attrs and user.role != Role.VEZAPP_ADMIN:
            raise serializers.ValidationError(
                {"is_active": "Only a Vezapp Admin can activate or deactivate a company."}
            )
        return attrs


class PlantSerializer(CompanyUniqueMixin, serializers.ModelSerializer):
    class Meta:
        model = Plant
        fields = ["id", "name", "address", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value):
        return self._unique_in_company(
            Plant, "name", value, "A plant with this name already exists.", ignore_case=True
        )


class ShiftSerializer(CompanyUniqueMixin, serializers.ModelSerializer):
    net_minutes = serializers.IntegerField(read_only=True)
    crosses_midnight = serializers.BooleanField(read_only=True)

    class Meta:
        model = Shift
        fields = [
            "id",
            "name",
            "start_time",
            "end_time",
            "break_minutes",
            "net_minutes",
            "crosses_midnight",
        ]
        read_only_fields = ["id"]

    def validate_name(self, value):
        return self._unique_in_company(
            Shift, "name", value, "A shift with this name already exists.", ignore_case=True
        )

    def validate(self, attrs):
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))  # noqa: E731
        try:
            shift_minutes(get("start_time"), get("end_time"), get("break_minutes") or 0)
        except ValueError as exc:
            raise serializers.ValidationError({"end_time": str(exc)}) from exc
        return attrs


class HolidaySerializer(CompanyUniqueMixin, serializers.ModelSerializer):
    shifts_off = CompanyPKField(queryset=Shift.objects.all(), many=True, required=False)

    class Meta:
        model = Holiday
        fields = ["id", "date", "name", "full_day", "shifts_off"]
        read_only_fields = ["id"]

    def validate_date(self, value):
        return self._unique_in_company(Holiday, "date", value, "This date already has a holiday.")

    def validate(self, attrs):
        full_day = attrs.get("full_day", getattr(self.instance, "full_day", True))
        if full_day:
            attrs["shifts_off"] = []
            return attrs
        chosen = attrs.get("shifts_off")
        if chosen is None and self.instance is not None:
            chosen = list(self.instance.shifts_off.all())
        if not chosen:
            raise serializers.ValidationError({"shifts_off": "Pick the shifts that are off."})
        return attrs


class CompanySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanySettings
        fields = [
            "horizon_days",
            "default_bucket",
            "rejection_booked_at",
            "flow_mode",
            "pour_same_shift",
            "melt_loss_default_pct",
        ]

    def validate_rejection_booked_at(self, value):
        from apps.masters.models import OperationType

        company = self.context.get("company")
        if not OperationType.objects.for_company(company).filter(code=value).exists():
            raise serializers.ValidationError("Not an operation of this company.")
        return value
