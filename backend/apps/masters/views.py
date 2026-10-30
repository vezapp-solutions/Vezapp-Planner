from django.db import transaction
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.viewsets import MasterViewSet

from .models import Customer, Grade, OperationType, Part
from .route import RouteSerializer, copy_route, describe_route, save_route
from .serializers import (
    CustomerSerializer,
    GradeSerializer,
    OperationTypeSerializer,
    PartSerializer,
)


class GradeViewSet(MasterViewSet):
    queryset = Grade.objects.all()
    serializer_class = GradeSerializer


class CustomerViewSet(MasterViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(code__icontains=q)
        if self.request.query_params.get("active") == "true":
            qs = qs.filter(is_active=True)
        return qs


class OperationTypeViewSet(MasterViewSet):
    queryset = OperationType.objects.all()
    serializer_class = OperationTypeSerializer

    def perform_destroy(self, instance):
        if instance.is_builtin:
            raise ValidationError({"detail": "Standard operations cannot be deleted."})
        super().perform_destroy(instance)


class PartViewSet(MasterViewSet):
    queryset = Part.objects.select_related("grade").prefetch_related("customer_links__customer")
    serializer_class = PartSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("q"):
            qs = qs.filter(part_number__icontains=params["q"]) | qs.filter(
                name__icontains=params["q"]
            )
        if params.get("customer", "").isdigit():
            qs = qs.filter(customer_links__customer_id=int(params["customer"]))
        if params.get("grade", "").isdigit():
            qs = qs.filter(grade_id=int(params["grade"]))
        if params.get("active") == "true":
            qs = qs.filter(is_active=True)
        return qs.distinct()

    @action(detail=True, methods=["get", "put"])
    def operations(self, request, pk=None):
        part = self.get_object()
        if request.method == "PUT":
            serializer = RouteSerializer(
                data=request.data,
                context={"company": self.get_company(), "part": part, "request": request},
            )
            serializer.is_valid(raise_exception=True)
            save_route(part, serializer.validated_data["operations"])
        return Response(describe_route(part))

    @action(detail=True, methods=["post"], url_path="operations/preview")
    def preview_operations(self, request, pk=None):
        """Validate and describe a route exactly as saving would, without keeping anything.

        The editor calls this as the planner types, so derived numbers always match the inputs.
        """
        part = self.get_object()
        serializer = RouteSerializer(
            data=request.data,
            context={"company": self.get_company(), "part": part, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            save_route(part, serializer.validated_data["operations"])
            described = describe_route(part)
            transaction.set_rollback(True)
        return Response(described)

    @action(detail=True, methods=["post"], url_path="copy-route")
    def copy_route(self, request, pk=None):
        target = self.get_object()
        source_id = request.data.get("source_part")
        source = (
            self.get_queryset().filter(pk=source_id).first() if str(source_id).isdigit() else None
        )
        if source is None or source.pk == target.pk:
            raise ValidationError({"source_part": "Pick a different part of this company."})
        copy_route(source, target)
        return Response(describe_route(target))
