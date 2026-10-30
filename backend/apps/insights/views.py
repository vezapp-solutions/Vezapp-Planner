from dataclasses import asdict
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.response import Response

from apps.core.permissions import AdminWrite, PlannerOnly, PlannerWrite
from apps.core.viewsets import CompanyAPIView, CompanyScopedViewSet
from apps.plans import exports
from apps.plans.models import Plan
from apps.plans.reports import Report, Table
from insights import digest as digest_rules
from insights import health
from insights.model import Card

from . import collect, reports, service
from .models import Insight, InsightRun
from .serializers import InsightRunSerializer, InsightSerializer

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def to_card(row: Insight) -> Card:
    return Card(
        key=row.key, type=row.type, severity=row.severity, title=row.title, message=row.message,
        numbers=row.numbers, entities=row.entities, action=row.action, why=tuple(row.why),
        impact=row.impact,
    )  # fmt: skip


def download(report: Report, fmt: str, footer: str) -> HttpResponse:
    body = (
        exports.render_pdf(report, footer) if fmt == "pdf" else exports.render_xlsx(report, footer)
    )
    response = HttpResponse(body, content_type=CONTENT_TYPES[fmt])
    response["Content-Disposition"] = f'attachment; filename="{report.filename}.{fmt}"'
    return response


def output_format(request, allowed=("pdf", "xlsx")) -> str | None:
    fmt = request.query_params.get("output")
    if fmt is not None and fmt not in allowed:
        raise ValidationError({"output": f"Use {' or '.join(allowed)}."})
    return fmt


class InsightViewSet(CompanyScopedViewSet):
    """The latest run's cards. Everyone reads; planners refresh and test suggestions."""

    queryset = Insight.objects.all()
    serializer_class = InsightSerializer
    permission_classes = [PlannerWrite]
    company_override_allowed = True
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed("POST")

    def list(self, request, *args, **kwargs):
        company = self.get_company()
        run = service.latest_run(company)
        cards = self.get_queryset().filter(run=run) if run else self.get_queryset().none()
        p = request.query_params
        if p.get("type"):
            cards = cards.filter(type=p["type"])
        if p.get("severity"):
            cards = cards.filter(severity=p["severity"])
        data = InsightSerializer(cards, many=True).data
        return Response(
            {
                "run": InsightRunSerializer(run).data if run else None,
                "count": len(data),
                "results": data,
            }
        )

    @action(detail=False, methods=["post"])
    def refresh(self, request):
        run = service.refresh(self.get_company(), trigger="manual")
        return Response(InsightRunSerializer(run).data, status=http.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def history(self, request):
        runs = InsightRun.objects.filter(company=self.get_company()).select_related("plan")[:30]
        return Response(InsightRunSerializer(runs, many=True).data)

    @action(detail=False, methods=["get"])
    def digest(self, request):
        company = self.get_company()
        run = service.latest_run(company)
        today = timezone.localdate()
        cards = [to_card(c) for c in self.get_queryset().filter(run=run)] if run else []
        data = digest_rules.digest(cards, today, company.name)
        if output_format(request, ("pdf",)) == "pdf":
            report = Report(
                data["title"], "The top insights today",
                [Table(
                    "Top insights",
                    ["#", "Severity", "Insight", "What it means", "Next step"],
                    [[str(n), i["severity"].title(), i["title"], i["message"], i["action"]] for n, i in enumerate(data["items"], 1)]
                    or [["", "", "Nothing needs attention today.", "", ""]],
                    widths=[0.4, 1, 3, 5, 4],
                )],
                "daily-digest",
            )  # fmt: skip
            return download(
                report, "pdf", f"{settings.APP_NAME} · {company.name} · {today:%d-%m-%Y}"
            )
        return Response(data)

    @action(detail=True, methods=["post"], url_path="dry-run")
    def dry_run(self, request, pk=None):
        result = service.dry_run(self.get_company(), self.get_object())
        return Response(result)


class DataHealthView(CompanyAPIView):
    """What is missing or doubtful in the masters and schedule, and why it hurts the plan."""

    permission_classes = [PlannerOnly]

    def get(self, request):
        company = self.get_company()
        items = collect.health_items(company, timezone.localdate())
        cards = health.data_health(items)
        order = {"error": 0, "warning": 1, "info": 2}
        return Response(
            {
                "count": len(items),
                "cards": [c.as_dict() for c in cards],
                "items": [
                    asdict(i)
                    for i in sorted(
                        items, key=lambda i: (order[i.severity], -i.lines_affected, i.subject)
                    )
                ],
            }
        )


class ReportView(CompanyAPIView):
    """Dispatch performance, utilisation and plan versus actual, on screen or as PDF or Excel."""

    permission_classes = [AdminWrite]  # everyone reads

    def get(self, request, kind):
        company = self.get_company()
        p = request.query_params
        fmt = output_format(request)
        start, end = (
            reports.parse_date(p.get("from"), "from"),
            reports.parse_date(p.get("to"), "to"),
        )
        footer = f"{settings.APP_NAME} · {company.name} · {timezone.localdate():%d-%m-%Y}"

        if kind == "dispatch-performance":
            data, report = reports.dispatch_performance(
                company, start, end, p.get("customer") or None
            )
        elif kind == "plan-vs-actual":
            data, report = reports.plan_vs_actual(company, start, end)
        elif kind == "utilisation":
            plan = (
                Plan.objects.filter(company=company, pk=p["plan"]).first()
                if p.get("plan", "").isdigit()
                else service.latest_plan(company)
            )
            if plan is None:
                if fmt:
                    raise ValidationError({"detail": "Calculate a plan first."})
                return Response({"plan": None, "from": start, "to": end, "resources": []})
            first = start or max(plan.plan_from, timezone.localdate())
            data, report = reports.utilisation(plan, first, end or first + timedelta(days=27))
        else:
            return Response({"detail": "Not found."}, status=http.HTTP_404_NOT_FOUND)
        return download(report, fmt, footer) if fmt else Response(data)
