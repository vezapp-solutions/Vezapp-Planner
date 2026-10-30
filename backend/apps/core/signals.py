from django.db.models.signals import post_save
from django.dispatch import receiver

from .context import audit_suppressed


@receiver(post_save, sender="companies.Company", dispatch_uid="company-defaults")
def seed_company_defaults(sender, instance, created, raw=False, **kwargs):
    """Every new company starts with the standard resource types, operations and settings."""
    if not created or raw:
        return
    from apps.companies.models import CompanySettings
    from apps.masters.models import ensure_default_operation_types
    from apps.resources.models import ensure_default_resource_types

    with audit_suppressed():
        CompanySettings.objects.get_or_create(company=instance)
        ensure_default_resource_types(instance)
        ensure_default_operation_types(instance)
