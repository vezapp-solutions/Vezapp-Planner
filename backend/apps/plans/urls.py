from django.urls import path
from rest_framework.routers import SimpleRouter

from .shop_views import MachineShopView
from .views import PlanViewSet

router = SimpleRouter(trailing_slash=False)
router.register("plans", PlanViewSet, basename="plan")

urlpatterns = [path("machine-shop", MachineShopView.as_view(), name="machine-shop"), *router.urls]
