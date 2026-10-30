from datetime import date, timedelta

from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.viewsets import MasterViewSet

from .availability import resource_availability
from .models import CapacityAdjustment, Downtime, Resource, ResourceType
from .serializers import (
    CapacityAdjustmentSerializer,
    DowntimeSerializer,
    ResourceSerializer,
    ResourceTypeSerializer,
)


class ResourceTypeViewSet(MasterViewSet):
    queryset = ResourceType.objects.all()
    serializer_class = ResourceTypeSerializer

    def perform_destroy(self, instance):
        if instance.is_default:
            raise ValidationError({"detail": "The standard resource types cannot be deleted."})
        super().perform_destroy(instance)


class ResourceViewSet(MasterViewSet):
    queryset = Resource.objects.select_related("resource_type").prefetch_related("shifts")
    serializer_class = ResourceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("kind"):
            qs = qs.filter(resource_type__kind=params["kind"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return qs

    @action(detail=True, methods=["get"])
    def availability(self, request, pk=None):
        resource = self.get_object()
        try:
            start = date.fromisoformat(request.query_params.get("from", date.today().isoformat()))
            end = date.fromisoformat(
                request.query_params.get("to", (start + timedelta(days=6)).isoformat())
            )
        except ValueError as exc:
            raise ValidationError({"detail": "Dates must look like 2026-11-02."}) from exc
        if end < start or (end - start).days > 92:
            raise ValidationError({"detail": "Pick a range of 1 to 93 days."})
        return Response(resource_availability(resource, start, end))


class DowntimeViewSet(MasterViewSet):
    queryset = Downtime.objects.select_related("resource")
    serializer_class = DowntimeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        resource = self.request.query_params.get("resource")
        return qs.filter(resource_id=int(resource)) if resource and resource.isdigit() else qs


class CapacityAdjustmentViewSet(MasterViewSet):
    """Extra shifts and overtime that every plan honours. Company Admins edit; everyone reads."""

    queryset = CapacityAdjustment.objects.select_related("shift").prefetch_related("resources")
    serializer_class = CapacityAdjustmentSerializer
