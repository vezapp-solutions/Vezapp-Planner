from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.accounts.roles import ALL_ROLES
from apps.core.permissions import AdminOnly, RoleMatrixPermission
from apps.core.viewsets import CompanyAPIView

from . import service
from .models import AssistantLog


class AllRoles(RoleMatrixPermission):
    """Every signed-in role may ask: the assistant only reads."""

    read_roles = ALL_ROLES
    write_roles = ALL_ROLES


class AssistantThrottle(UserRateThrottle):
    scope = "assistant"


class AssistantView(CompanyAPIView):
    permission_classes = [AllRoles]
    throttle_classes = [AssistantThrottle]


class StatusView(CompanyAPIView):
    permission_classes = [AllRoles]

    def get(self, request):
        return Response(service.status())


class LogView(CompanyAPIView):
    """What was asked of the assistant, by whom, which tools ran and what came back. Admins only."""

    permission_classes = [AdminOnly]

    def get(self, request):
        rows = AssistantLog.objects.filter(company=self.get_company())[:200]
        return Response(
            {
                "count": len(rows),
                "results": [
                    {
                        "id": r.pk, "created_at": r.created_at, "username": r.username, "kind": r.kind,
                        "mode": r.mode, "prompt": r.prompt, "tools": [c["name"] for c in r.tool_calls],
                        "answer": r.answer, "flagged": r.flagged,
                        "tokens": r.input_tokens + r.output_tokens,
                    }
                    for r in rows
                ],
            }
        )  # fmt: skip


class AskView(AssistantView):
    def post(self, request):
        return Response(
            service.ask(
                request.user,
                self.get_company(),
                request.data.get("question", ""),
                conversation=request.data.get("conversation", ""),
            )
        )


class ExplainView(AssistantView):
    def post(self, request):
        return Response(
            service.explain(request.user, self.get_company(), str(request.data.get("key", "")))
        )


class MonthlySummaryView(AssistantView):
    def post(self, request):
        return Response(service.monthly_summary(request.user, self.get_company()))
