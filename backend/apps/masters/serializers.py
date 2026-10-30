from django.db import transaction
from rest_framework import serializers

from apps.core.fields import CompanyPKField, CompanyUniqueMixin, GSTINField
from apps.core.validation import advisories, raise_on_errors
from planning.checks import check_part

from .models import Customer, Grade, OperationType, OpKind, Part, PartCustomer

SLUG_ERROR = "Use lowercase letters, digits and underscores only."


class GradeSerializer(CompanyUniqueMixin, serializers.ModelSerializer):
    part_count = serializers.IntegerField(source="parts.count", read_only=True)

    class Meta:
        model = Grade
        fields = ["id", "name", "description", "part_count"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        return self._unique_in_company(
            Grade, "name", value, "This grade already exists.", ignore_case=True
        )


class CustomerSerializer(CompanyUniqueMixin, serializers.ModelSerializer):
    gstin = GSTINField()

    class Meta:
        model = Customer
        fields = [
            "id", "code", "name", "contact_person", "phone", "email", "billing_address",
            "shipping_address", "gstin", "state", "priority", "is_active",
        ]  # fmt: skip
        read_only_fields = ["id"]

    def validate_code(self, value):
        return self._unique_in_company(
            Customer, "code", value, "This code is already used.", ignore_case=True
        )


class PartCustomerLinkSerializer(serializers.Serializer):
    customer = CompanyPKField(queryset=Customer.objects.all())
    is_default = serializers.BooleanField(default=False)


class PartSerializer(CompanyUniqueMixin, serializers.ModelSerializer):
    grade = CompanyPKField(queryset=Grade.objects.all(), required=False, allow_null=True)
    grade_name = serializers.CharField(source="grade.name", read_only=True, default=None)
    customer_links = PartCustomerLinkSerializer(many=True, write_only=True, required=False)
    customers = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()

    class Meta:
        model = Part
        fields = [
            "id", "part_number", "name", "description", "grade", "grade_name", "material_grade",
            "drawing_number", "drawing_revision", "casting_weight_kg", "finished_weight_kg",
            "pouring_weight_per_mould_kg", "cavities_per_mould", "cores_per_mould", "pattern_number",
            "rejection_pct", "selling_price", "is_active", "customer_links", "customers", "warnings",
        ]  # fmt: skip
        read_only_fields = ["id"]

    def validate_part_number(self, value):
        return self._unique_in_company(
            Part, "part_number", value, "This part number is already used.", ignore_case=True
        )

    def validate_customer_links(self, links):
        for link in links:  # a partial update (PATCH) skips field defaults
            link.setdefault("is_default", False)
        ids = [link["customer"].pk for link in links]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("A customer is listed twice.")
        if sum(1 for link in links if link["is_default"]) > 1:
            raise serializers.ValidationError("Only one customer can be the default.")
        if links and not any(link["is_default"] for link in links):
            links[0]["is_default"] = True
        return links

    def validate(self, attrs):
        data = {
            key: attrs.get(key, getattr(self.instance, key, None))
            for key in (
                "casting_weight_kg", "finished_weight_kg", "pouring_weight_per_mould_kg",
                "cavities_per_mould", "cores_per_mould", "rejection_pct",
            )
        }  # fmt: skip
        raise_on_errors(check_part(data))
        return attrs

    def get_customers(self, part):
        return [
            {
                "id": l.customer_id,
                "code": l.customer.code,
                "name": l.customer.name,
                "is_default": l.is_default,
            }
            for l in part.customer_links.all()  # noqa: E741
        ]

    def get_warnings(self, part):
        return advisories(check_part({
            "casting_weight_kg": part.casting_weight_kg,
            "finished_weight_kg": part.finished_weight_kg,
            "pouring_weight_per_mould_kg": part.pouring_weight_per_mould_kg,
            "cavities_per_mould": part.cavities_per_mould,
            "cores_per_mould": part.cores_per_mould,
            "rejection_pct": part.rejection_pct,
        }))  # fmt: skip

    def _save_links(self, part, links):
        company = part.company
        existing = {l.customer_id: l for l in part.customer_links.all()}  # noqa: E741
        wanted = {link["customer"].pk: link for link in links}
        for customer_id, row in existing.items():
            if customer_id not in wanted:
                row.delete()
        # Clear the old default first so the one-default constraint is never violated mid-way.
        PartCustomer.objects.filter(part=part, is_default=True).exclude(
            customer_id__in=[c for c, l in wanted.items() if l["is_default"]]  # noqa: E741
        ).update(is_default=False)
        for link in wanted.values():
            PartCustomer.objects.update_or_create(
                part=part,
                customer=link["customer"],
                defaults={"company": company, "is_default": link["is_default"]},
            )

    @transaction.atomic
    def create(self, validated_data):
        links = validated_data.pop("customer_links", [])
        part = super().create(validated_data)
        self._save_links(part, links)
        return part

    @transaction.atomic
    def update(self, instance, validated_data):
        links = validated_data.pop("customer_links", None)
        part = super().update(instance, validated_data)
        if links is not None:
            self._save_links(part, links)
        return part


class OperationTypeSerializer(CompanyUniqueMixin, serializers.ModelSerializer):
    class Meta:
        model = OperationType
        fields = [
            "id", "code", "name", "kind", "default_sequence", "default_enabled", "default_bucket",
            "is_active", "is_builtin", "multi_step",
        ]  # fmt: skip
        read_only_fields = ["id", "is_builtin"]

    def validate_code(self, value):
        if self.instance is not None and self.instance.is_builtin and value != self.instance.code:
            raise serializers.ValidationError("The code of a standard operation cannot change.")
        return self._unique_in_company(OperationType, "code", value, "This code is already used.")

    def validate_kind(self, value):
        if (
            self.instance is not None
            and self.instance.kind != value
            and self.instance.part_operations.exists()
        ):
            raise serializers.ValidationError(
                "The kind cannot change once parts use this operation."
            )
        if self.instance is None and value != OpKind.POST:
            raise serializers.ValidationError("Only extra post-casting operations can be added.")
        return value

    def validate(self, attrs):
        if (
            self.instance is not None
            and self.instance.is_builtin
            and attrs.get("is_active") is False
        ):
            raise serializers.ValidationError(
                {"is_active": "Standard operations cannot be switched off for the company."}
            )
        return attrs
