from rest_framework.response import Response

from apps.core.permissions import AdminWrite
from apps.core.viewsets import CompanyAPIView
from apps.insights.reports import parse_date
from apps.insights.service import latest_plan

from . import machine_shop
from .models import Plan


class MachineShopView(CompanyAPIView):
    """Machines grouped by type with free hours against planned load. Everyone in the company reads."""

    permission_classes = [AdminWrite]

    def get(self, request):
        company = self.get_company()
        p = request.query_params
        plan = (
            Plan.objects.filter(company=company, pk=p["plan"]).first()
            if p.get("plan", "").isdigit()
            else latest_plan(company)
        )
        data = machine_shop.build(
            company, plan, parse_date(p.get("from"), "from"), parse_date(p.get("to"), "to")
        )
        return Response(data)
