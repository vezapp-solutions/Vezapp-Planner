from django.urls import include, path

urlpatterns = [
    path(
        "api/v1/",
        include(
            [
                path("", include("apps.core.urls")),
                path("", include("apps.accounts.urls")),
                path("", include("apps.companies.urls")),
                path("", include("apps.resources.urls")),
                path("", include("apps.masters.urls")),
                path("", include("apps.scheduler.urls")),
                path("", include("apps.plans.urls")),
                path("", include("apps.scenarios.urls")),
                path("", include("apps.insights.urls")),
                path("", include("apps.assistant.urls")),
            ]
        ),
    ),
]
