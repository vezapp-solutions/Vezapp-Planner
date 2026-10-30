from rest_framework.routers import SimpleRouter

from .views import (
    CapacityAdjustmentViewSet,
    DowntimeViewSet,
    ResourceTypeViewSet,
    ResourceViewSet,
)

router = SimpleRouter(trailing_slash=False)
router.register("resource-types", ResourceTypeViewSet, basename="resource-type")
router.register("resources", ResourceViewSet, basename="resource")
router.register("downtimes", DowntimeViewSet, basename="downtime")
router.register("capacity-adjustments", CapacityAdjustmentViewSet, basename="capacity-adjustment")

urlpatterns = router.urls
