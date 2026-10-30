from datetime import date

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.core.permissions import PlannerOnly, PlannerWrite
from apps.core.tenancy import resolve_company
from apps.core.viewsets import CompanyAPIView, CompanyScopedViewSet

from . import reports, service
from .models import LineStatus, ScheduleLine, UploadBatch
from .serializers import ScheduleLineSerializer, UploadBatchSerializer

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _month(text: str, field: str) -> date:
    try:
        year, month = text.split("-")
        return date(int(year), int(month), 1)
    except (ValueError, AttributeError) as exc:
        raise ValidationError({field: "Use a month like 2026-11."}) from exc


class ScheduleLineViewSet(CompanyScopedViewSet):
    queryset = ScheduleLine.objects.select_related("customer", "part", "part__grade")
    serializer_class = ScheduleLineSerializer
    permission_classes = [PlannerWrite]
    company_override_allowed = True

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("month"):
            first = _month(p["month"], "month")
            qs = qs.filter(
                internal_dispatch_date__year=first.year, internal_dispatch_date__month=first.month
            )
        for param, lookup in (
            ("customer", "customer_id"),
            ("part", "part_id"),
            ("grade", "part__grade_id"),
        ):
            if p.get(param, "").isdigit():
                qs = qs.filter(**{lookup: int(p[param])})
        if p.get("status") in LineStatus.values:
            qs = qs.filter(status=p["status"])
        if p.get("q"):
            qs = qs.filter(part__part_number__icontains=p["q"]) | qs.filter(
                part__name__icontains=p["q"]
            )
        return qs

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Totals for the same filters as the list: pieces, tonnes and value."""
        qs = self.filter_queryset(self.get_queryset()).exclude(status=LineStatus.CANCELLED)
        money = DecimalField(max_digits=18, decimal_places=2)
        weight = DecimalField(max_digits=18, decimal_places=3)
        agg = qs.aggregate(
            pieces=Sum("dispatch_qty"),
            kg=Sum(
                ExpressionWrapper(
                    F("dispatch_qty") * F("part__casting_weight_kg"), output_field=weight
                )
            ),
            value=Sum(
                ExpressionWrapper(F("dispatch_qty") * F("part__selling_price"), output_field=money)
            ),
        )
        return Response(
            {
                "lines": qs.count(),
                "pieces": agg["pieces"] or 0,
                "tonnes": round(float(agg["kg"] or 0) / 1000, 3),
                "value": float(agg["value"]) if agg["value"] is not None else None,
                "lines_without_price": qs.filter(part__selling_price__isnull=True).count(),
            }
        )

    @action(detail=False, methods=["post"], url_path="copy-month")
    def copy_month(self, request):
        company = self.get_company()
        if company is None:
            raise ValidationError({"company": "No company selected for this request."})
        source = _month(request.data.get("from_month"), "from_month")
        target = _month(request.data.get("to_month"), "to_month")
        if source == target:
            raise ValidationError({"to_month": "Pick a different month to copy into."})
        return Response(service.copy_month(company, source, target))


class UploadBase(CompanyAPIView):
    permission_classes = [PlannerOnly]
    parser_classes = [MultiPartParser, FormParser]

    def read_file(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "Choose a file to upload."})
        if upload.size > 5 * 1024 * 1024:
            raise ValidationError({"file": "The file is larger than 5 MB."})
        return upload.name, upload.read()

    def mode(self, request):
        return request.data.get("mode", "insert")


class TemplateView(CompanyAPIView):
    """Anyone who can see the scheduler can download the template."""

    def get(self, request):
        response = HttpResponse(reports.template_workbook(), content_type=XLSX)
        response["Content-Disposition"] = 'attachment; filename="schedule-template.xlsx"'
        return response


class PreviewView(UploadBase):
    def post(self, request):
        company = self.get_company()
        name, content = self.read_file(request)
        return Response(service.preview(company, name, content, self.mode(request)))


class CommitView(UploadBase):
    def post(self, request):
        company = self.get_company()
        name, content = self.read_file(request)
        skip = str(request.data.get("skip_errors", "")).lower() in {"1", "true", "yes", "on"}
        batch = service.commit(company, request.user, name, content, self.mode(request), skip)
        return Response(UploadBatchSerializer(batch).data, status=201)


class ErrorReportView(UploadBase):
    def post(self, request):
        company = self.get_company()
        name, content = self.read_file(request)
        results = service.analyse(company, name, content, self.mode(request))
        response = HttpResponse(reports.error_report(results), content_type=XLSX)
        response["Content-Disposition"] = 'attachment; filename="schedule-upload-problems.xlsx"'
        return response


class UploadHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UploadBatchSerializer
    permission_classes = [PlannerOnly]

    def get_queryset(self):
        company = resolve_company(self.request, allow_override=True)
        return (
            UploadBatch.objects.filter(company=company) if company else UploadBatch.objects.none()
        )

    @action(detail=True, methods=["get"], url_path="errors.xlsx")
    def errors(self, request, pk=None):
        batch = self.get_object()
        response = HttpResponse(reports.report_from_stored(batch.report), content_type=XLSX)
        response["Content-Disposition"] = f'attachment; filename="upload-{batch.pk}-problems.xlsx"'
        return response
