from django.db import transaction
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.roles import Role
from apps.core.permissions import AdminWrite, VezappAdminOnly
from apps.core.viewsets import CompanyAPIView, CompanyScopedViewSet, MasterViewSet

from .calendar_data import week_summary
from .models import Company, CompanySettings, Holiday, Plant, Shift, WeekdayShift
from .serializers import (
    CompanySerializer,
    CompanySettingsSerializer,
    HolidaySerializer,
    PlantSerializer,
    ShiftSerializer,
)


class CompanyViewSet(viewsets.ModelViewSet):
    """Vezapp Admin manages every company; others see (Company Admin edits) only their own."""

    queryset = Company.objects.all()
    serializer_class = CompanySerializer

    def get_permissions(self):
        if self.action in {"create", "destroy"}:
            return [VezappAdminOnly()]
        return [AdminWrite()]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.role == Role.VEZAPP_ADMIN:
            return qs
        return qs.filter(pk=user.company_id)


class PlantViewSet(CompanyScopedViewSet):
    queryset = Plant.objects.all()
    serializer_class = PlantSerializer
    company_override_allowed = True


class ShiftViewSet(MasterViewSet):
    queryset = Shift.objects.all()
    serializer_class = ShiftSerializer


class HolidayViewSet(MasterViewSet):
    queryset = Holiday.objects.prefetch_related("shifts_off")
    serializer_class = HolidaySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        year = self.request.query_params.get("year")
        return qs.filter(date__year=int(year)) if year and year.isdigit() else qs


class WeekView(CompanyAPIView):
    """Which shifts run on which weekday. A weekday with none is a weekly off."""

    def get(self, request):
        company = self.get_company()
        shifts = ShiftSerializer(Shift.objects.for_company(company), many=True).data
        return Response({"shifts": shifts, **week_summary(company)})

    @transaction.atomic
    def put(self, request):
        company = self.get_company()
        valid = set(Shift.objects.for_company(company).values_list("pk", flat=True))
        wanted: dict[int, set[int]] = {}
        for key, ids in (request.data.get("days") or {}).items():
            if not str(key).isdigit() or int(key) > 6:
                raise ValidationError({"days": f"Unknown weekday {key}."})
            ids = set(ids)
            if not ids <= valid:
                raise ValidationError(
                    {"days": "A shift in the request does not belong to this company."}
                )
            wanted[int(key)] = ids

        existing = {(w.weekday, w.shift_id): w for w in WeekdayShift.objects.for_company(company)}
        for (weekday, shift_id), row in existing.items():
            if weekday in wanted and shift_id not in wanted[weekday]:
                row.delete()
        for weekday, ids in wanted.items():
            for shift_id in ids - {s for d, s in existing if d == weekday}:
                WeekdayShift.objects.create(company=company, weekday=weekday, shift_id=shift_id)
        return self.get(request)


class SettingsView(CompanyAPIView):
    def get(self, request):
        settings_row, _ = CompanySettings.objects.get_or_create(company=self.get_company())
        return Response(CompanySettingsSerializer(settings_row).data)

    def patch(self, request):
        company = self.get_company()
        settings_row, _ = CompanySettings.objects.get_or_create(company=company)
        serializer = CompanySettingsSerializer(
            settings_row,
            data=request.data,
            partial=True,
            context={"company": company, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
