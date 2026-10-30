from django.urls import path

from .views import AskView, ExplainView, LogView, MonthlySummaryView, StatusView

urlpatterns = [
    path("assistant/logs", LogView.as_view(), name="assistant-logs"),
    path("assistant/status", StatusView.as_view(), name="assistant-status"),
    path("assistant/ask", AskView.as_view(), name="assistant-ask"),
    path("assistant/explain", ExplainView.as_view(), name="assistant-explain"),
    path("assistant/monthly-summary", MonthlySummaryView.as_view(), name="assistant-summary"),
]
