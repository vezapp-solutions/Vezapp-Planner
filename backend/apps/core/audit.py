"""Audit trail for masters and schedules.

Decorate a model with ``@audited(...)`` and every create, update and delete is recorded in
AuditLog with the acting user, the time and the values before and after.
"""

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.signals import post_delete, post_save, pre_save

from .context import get_current_user, is_audit_suppressed


def _snapshot(instance, exclude):
    data = {}
    for field in instance._meta.concrete_fields:
        # updated_at changes on every save, so it would make every save look like an edit.
        if field.name in exclude or field.name == "updated_at":
            continue
        data[field.attname] = getattr(instance, field.attname)
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def _company_id(instance):
    if instance._meta.label == "companies.Company":
        return instance.pk
    return getattr(instance, "company_id", None)


def _write(instance, action, before, after):
    from .models import AuditLog

    if is_audit_suppressed():
        return
    user = get_current_user()
    AuditLog.objects.create(
        company_id=_company_id(instance),
        user=user if getattr(user, "pk", None) else None,
        username=getattr(user, "username", "") or "",
        action=action,
        model_label=instance._meta.label,
        object_pk=str(instance.pk),
        object_repr=str(instance)[:200],
        before=before,
        after=after,
    )


def audited(exclude=()):
    exclude = frozenset(exclude)

    def decorator(model):
        uid = f"audit-{model._meta.label}"

        def on_pre_save(sender, instance, raw=False, **kwargs):
            instance._audit_before = None
            if raw or instance.pk is None:
                return
            existing = sender._base_manager.filter(pk=instance.pk).first()
            if existing is not None:
                instance._audit_before = _snapshot(existing, exclude)

        def on_post_save(sender, instance, created, raw=False, **kwargs):
            if raw:
                return
            after = _snapshot(instance, exclude)
            if created:
                _write(instance, "create", None, after)
                return
            before = getattr(instance, "_audit_before", None)
            if before != after:
                _write(instance, "update", before, after)

        def on_post_delete(sender, instance, **kwargs):
            _write(instance, "delete", _snapshot(instance, exclude), None)

        pre_save.connect(on_pre_save, sender=model, weak=False, dispatch_uid=f"{uid}-pre")
        post_save.connect(on_post_save, sender=model, weak=False, dispatch_uid=f"{uid}-post")
        post_delete.connect(on_post_delete, sender=model, weak=False, dispatch_uid=f"{uid}-del")
        return model

    return decorator
