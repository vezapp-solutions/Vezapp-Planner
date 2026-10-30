from django.db.models import ProtectedError
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from .permissions import AdminWrite
from .tenancy import resolve_company


class CompanyScopedViewSet(viewsets.ModelViewSet):
    """Base for every tenant-owned resource.

    The company comes from the logged-in user, never from the request body. A Vezapp Admin has
    no company of their own and may act for one client by sending ``X-Company-Id``, but only on
    viewsets that opt in with ``company_override_allowed = True``.
    """

    permission_classes = [AdminWrite]
    company_override_allowed = False

    def get_company(self):
        return resolve_company(self.request, self.company_override_allowed)

    def get_queryset(self):
        return super().get_queryset().for_company(self.get_company())

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["company"] = self.get_company()
        return context

    def perform_create(self, serializer):
        company = self.get_company()
        if company is None:
            raise ValidationError({"company": "No company selected for this request."})
        serializer.save(company=company)


class MasterViewSet(CompanyScopedViewSet):
    """Master data: everyone in the company reads, admins write, a Vezapp Admin can act for a client."""

    company_override_allowed = True

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError as exc:
            raise ValidationError(
                {"detail": "This record is in use and cannot be deleted. Mark it inactive instead."}
            ) from exc


class CompanyAPIView(APIView):
    """Base for single-record or computed endpoints that belong to the request's company."""

    permission_classes = [AdminWrite]
    company_override_allowed = True

    def get_company(self):
        company = resolve_company(self.request, self.company_override_allowed)
        if company is None:
            raise ValidationError({"company": "No company selected for this request."})
        return company
