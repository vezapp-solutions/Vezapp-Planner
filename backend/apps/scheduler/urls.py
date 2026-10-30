from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    CommitView,
    ErrorReportView,
    PreviewView,
    ScheduleLineViewSet,
    TemplateView,
    UploadHistoryViewSet,
)

router = SimpleRouter(trailing_slash=False)
router.register("schedule-lines", ScheduleLineViewSet, basename="schedule-line")
router.register("uploads/history", UploadHistoryViewSet, basename="upload-history")

urlpatterns = [
    path("uploads/template", TemplateView.as_view(), name="upload-template"),
    path("uploads/preview", PreviewView.as_view(), name="upload-preview"),
    path("uploads/commit", CommitView.as_view(), name="upload-commit"),
    path("uploads/error-report", ErrorReportView.as_view(), name="upload-error-report"),
    *router.urls,
]
