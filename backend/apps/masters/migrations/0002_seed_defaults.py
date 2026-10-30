from django.db import migrations


def seed(apps, schema_editor):
    Company = apps.get_model("companies", "Company")
    CompanySettings = apps.get_model("companies", "CompanySettings")
    ResourceType = apps.get_model("resources", "ResourceType")
    OperationType = apps.get_model("masters", "OperationType")
    from apps.masters.models import DEFAULT_OPERATION_TYPES
    from apps.resources.models import DEFAULT_RESOURCE_TYPES

    for company in Company.objects.all():
        CompanySettings.objects.get_or_create(company=company)
        for name, kind in DEFAULT_RESOURCE_TYPES:
            ResourceType.objects.get_or_create(
                company=company, name=name, defaults={"kind": kind, "is_default": True}
            )
        for code, name, kind, seq, enabled, bucket, builtin, active in DEFAULT_OPERATION_TYPES:
            OperationType.objects.get_or_create(
                company=company,
                code=code,
                defaults=dict(
                    name=name, kind=kind, default_sequence=seq, default_enabled=enabled,
                    default_bucket=bucket, is_builtin=builtin, is_active=active,
                ),
            )


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0002_companysettings_shift_holiday_weekdayshift_and_more"),
        ("resources", "0001_initial"),
        ("masters", "0001_initial"),
    ]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
