from django.conf import settings
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


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "username",
            "action",
            "model_label",
            "object_pk",
            "object_repr",
            "before",
            "after",
            "created_at",
        ]


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
