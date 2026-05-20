from rest_framework.routers import DefaultRouter

from .views import DeviceCommandViewSet, DeviceGroupViewSet, DeviceViewSet

router = DefaultRouter()
router.register("groups", DeviceGroupViewSet, basename="device-group")
router.register("commands", DeviceCommandViewSet, basename="command")
router.register("", DeviceViewSet, basename="device")

urlpatterns = router.urls
