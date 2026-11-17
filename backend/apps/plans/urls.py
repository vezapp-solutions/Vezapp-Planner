from django.urls import path
from rest_framework.routers import SimpleRouter

from .shop_views import MachineShopView
from .views import PlanningConfigView, PlanViewSet

router = SimpleRouter(trailing_slash=False)
router.register("plans", PlanViewSet, basename="plan")

urlpatterns = [
    path("machine-shop", MachineShopView.as_view(), name="machine-shop"),
    path("planning-config", PlanningConfigView.as_view(), name="planning-config"),
    *router.urls,
]
