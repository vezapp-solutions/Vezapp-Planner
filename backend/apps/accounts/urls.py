from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import LoginView, LogoutView, MeView, RefreshView, UserViewSet

router = SimpleRouter(trailing_slash=False)
router.register("users", UserViewSet, basename="user")

urlpatterns = [
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("me", MeView.as_view(), name="me"),
    *router.urls,
]
