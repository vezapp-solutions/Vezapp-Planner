from rest_framework.routers import SimpleRouter

from .views import CustomerViewSet, GradeViewSet, OperationTypeViewSet, PartViewSet

router = SimpleRouter(trailing_slash=False)
router.register("grades", GradeViewSet, basename="grade")
router.register("customers", CustomerViewSet, basename="customer")
router.register("operation-types", OperationTypeViewSet, basename="operation-type")
router.register("parts", PartViewSet, basename="part")

urlpatterns = router.urls
