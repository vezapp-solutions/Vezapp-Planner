from rest_framework import serializers


class CompanyPKField(serializers.PrimaryKeyRelatedField):
    """A relation that can only point at rows of the request's own company.

    This is what stops a client from linking its record to another company's row by guessing an id.
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        company = self.context.get("company")
        if hasattr(queryset, "for_company"):
            return queryset.for_company(company)
        return queryset.none()


class GSTINField(serializers.CharField):
    """Upper-cases before checking the 15-character GSTIN format, so 'abc...' is accepted as typed."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_blank", True)
        kwargs.setdefault("max_length", 15)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.companies.models import GSTIN_VALIDATOR

        value = super().to_internal_value(data).upper()
        if value:
            try:
                GSTIN_VALIDATOR(value)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages) from exc
        return value


class CompanyUniqueMixin:
    """Per-company uniqueness as a clean 400 instead of a database error."""

    def _unique_in_company(self, model, field, value, message, ignore_case=False):
        lookup = f"{field}__iexact" if ignore_case else field
        clash = model.objects.for_company(self.context.get("company")).filter(**{lookup: value})
        if getattr(self, "instance", None) is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(message)
        return value
