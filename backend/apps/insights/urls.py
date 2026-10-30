from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import DataHealthView, InsightViewSet, ReportView

router = SimpleRouter(trailing_slash=False)
router.register("insights", InsightViewSet, basename="insight")

urlpatterns = [
    path("data-health", DataHealthView.as_view(), name="data-health"),
    path("reports/<str:kind>", ReportView.as_view(), name="report"),
    *router.urls,
]
