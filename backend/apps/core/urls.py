from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AuditLogViewSet, HealthView

router = SimpleRouter(trailing_slash=False)
router.register("audit-log", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    *router.urls,
]
