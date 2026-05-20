from rest_framework.routers import DefaultRouter

from .views import (
    AlertRuleViewSet,
    AlertViewSet,
    NotificationChannelViewSet,
    NotificationViewSet,
)

router = DefaultRouter()
router.register("rules", AlertRuleViewSet, basename="alert-rule")
router.register("channels", NotificationChannelViewSet, basename="notification-channel")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("", AlertViewSet, basename="alert")

urlpatterns = router.urls
