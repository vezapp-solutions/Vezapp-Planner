from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    CompanyViewSet,
    HolidayViewSet,
    PlantViewSet,
    SettingsView,
    ShiftViewSet,
    WeekView,
)

router = SimpleRouter(trailing_slash=False)
router.register("companies", CompanyViewSet, basename="company")
router.register("plants", PlantViewSet, basename="plant")
router.register("shifts", ShiftViewSet, basename="shift")
router.register("holidays", HolidayViewSet, basename="holiday")

urlpatterns = [
    path("calendar/week", WeekView.as_view(), name="calendar-week"),
    path("company/settings", SettingsView.as_view(), name="company-settings"),
    *router.urls,
]
