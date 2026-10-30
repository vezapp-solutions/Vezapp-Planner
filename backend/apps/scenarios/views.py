from django.db.models import Max
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.permissions import PlannerOnly
from apps.core.viewsets import CompanyScopedViewSet

from . import service
from .models import Scenario, ScenarioChange, ScenarioStatus
from .serializers import ChangeSerializer, ScenarioDetailSerializer, ScenarioSerializer


class ScenarioViewSet(CompanyScopedViewSet):
    """What-if scenarios. Planners and admins only; viewers do not see them."""

    queryset = Scenario.objects.select_related("created_by", "applied_by").prefetch_related(
        "changes"
    )
    permission_classes = [PlannerOnly]
    company_override_allowed = True
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        return ScenarioSerializer if self.action == "list" else ScenarioDetailSerializer

    def perform_create(self, serializer):
        company = self.get_company()
        if company is None:
            raise ValidationError({"company": "No company selected for this request."})
        serializer.save(company=company, created_by=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.status == ScenarioStatus.APPLIED:
            raise ValidationError({"detail": "An applied scenario cannot be edited."})
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status == ScenarioStatus.APPLIED:
            raise ValidationError(
                {"detail": "An applied scenario is kept as a record and cannot be deleted."}
            )
        instance.delete()

    # --- changes -------------------------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="changes")
    def add_change(self, request, pk=None):
        scenario = self.get_object()
        if scenario.status == ScenarioStatus.APPLIED:
            raise ValidationError({"detail": "An applied scenario cannot be edited."})
        serializer = ChangeSerializer(
            data=request.data, context={"company": scenario.company, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        order = (scenario.changes.aggregate(m=Max("order"))["m"] or 0) + 1
        change = ScenarioChange.objects.create(
            company=scenario.company, scenario=scenario, order=order, **serializer.validated_data
        )
        return Response(
            ChangeSerializer(change, context={"company": scenario.company}).data,
            status=http.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["delete"], url_path=r"changes/(?P<change_id>\d+)")
    def remove_change(self, request, pk=None, change_id=None):
        scenario = self.get_object()
        if scenario.status == ScenarioStatus.APPLIED:
            raise ValidationError({"detail": "An applied scenario cannot be edited."})
        deleted, _ = scenario.changes.filter(pk=change_id).delete()
        if not deleted:
            return Response({"detail": "Not found."}, status=http.HTTP_404_NOT_FOUND)
        return Response(status=http.HTTP_204_NO_CONTENT)

    # --- run and apply ---------------------------------------------------------------------------------
    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        scenario = service.run(self.get_object())
        return Response(
            ScenarioDetailSerializer(scenario, context=self.get_serializer_context()).data
        )

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        scenario = self.get_object()
        recalculate = str(request.data.get("recalculate", True)).lower() not in {"false", "0", "no"}
        summary = service.apply(scenario, request.user, recalculate)
        scenario.refresh_from_db()
        data = ScenarioDetailSerializer(scenario, context=self.get_serializer_context()).data
        return Response({**data, "applied_summary": summary})
