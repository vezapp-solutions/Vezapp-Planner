from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db import connection
from rest_framework import serializers, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLog
from .permissions import AdminOnly
from .tenancy import resolve_company


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            database = "ok"
        except Exception:  # noqa: BLE001 - report, never raise, from a health probe
            database = "unavailable"
        status = "ok" if database == "ok" else "degraded"
        return Response(
            {"status": status, "app": settings.APP_NAME, "database": database},
            status=200 if status == "ok" else 503,
        )


def _fk_refs(entry: AuditLog):
    """Every (related model, snapshot key, id) in a log entry whose snapshot names a foreign key ("customer_id")."""
    try:
        model = apps.get_model(entry.model_label)
    except (LookupError, ValueError):
        return
    for snapshot in (entry.before, entry.after):
        for key, value in (snapshot or {}).items():
            if not key.endswith("_id") or not isinstance(value, int) or isinstance(value, bool):
                continue
            try:
                related = model._meta.get_field(key[:-3]).related_model
            except FieldDoesNotExist:
                continue
            if related is not None:
                yield related, key, value


class AuditLogListSerializer(serializers.ListSerializer):
    """Looks the names up for the whole page at once: one query per kind of record, not one per row."""

    def to_representation(self, data):
        entries = list(data)
        cache = self.context.setdefault("ref_cache", {})
        wanted: dict = {}
        for entry in entries:
            for related, _key, value in _fk_refs(entry):
                if (related._meta.label, value) not in cache:
                    wanted.setdefault(related, set()).add(value)
        for related, ids in wanted.items():
            names = {obj.pk: str(obj) for obj in related._base_manager.filter(pk__in=ids)}
            for pk in ids:
                cache[(related._meta.label, pk)] = names.get(pk, "")
        return super().to_representation(entries)


class AuditLogSerializer(serializers.ModelSerializer):
    # The snapshots hold ids ("customer_id": 3). `refs` names the records those ids point to, so the screen can say
    # "Aarav Pumps" instead of "3": { "customer_id": { "3": "C-101 Aarav Pumps" } }.
    refs = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        list_serializer_class = AuditLogListSerializer
        fields = [
            "id",
            "username",
            "action",
            "model_label",
            "object_pk",
            "object_repr",
            "before",
            "after",
            "refs",
            "created_at",
        ]

    def get_refs(self, entry: AuditLog) -> dict[str, dict[str, str]]:
        cache = self.context.setdefault("ref_cache", {})
        out: dict[str, dict[str, str]] = {}
        for related, key, value in _fk_refs(entry):
            token = (related._meta.label, value)
            if token not in cache:  # a single record fetched on its own
                found = related._base_manager.filter(pk=value).first()
                cache[token] = str(found) if found is not None else ""
            if cache[token]:
                out.setdefault(key, {})[str(value)] = cache[token]
        return out


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Who changed what. Company Admins see their own company's log; read-only for everyone."""

    permission_classes = [AdminOnly]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        company = resolve_company(self.request, allow_override=True)
        qs = AuditLog.objects.filter(company=company) if company else AuditLog.objects.none()
        params = self.request.query_params
        for field in ("model_label", "object_pk", "username", "action"):
            if params.get(field):
                qs = qs.filter(**{field: params[field]})
        return qs
