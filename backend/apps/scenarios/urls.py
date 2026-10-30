from rest_framework.routers import SimpleRouter

from .views import ScenarioViewSet

router = SimpleRouter(trailing_slash=False)
router.register("scenarios", ScenarioViewSet, basename="scenario")

urlpatterns = router.urls
