from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CameraFeedViewSet,
    ReadingViewSet,
    SensorViewSet,
    TelemetryIngestView,
)

router = DefaultRouter()
router.register("sensors", SensorViewSet, basename="sensor")
router.register("readings", ReadingViewSet, basename="reading")
router.register("cameras", CameraFeedViewSet, basename="camera")

urlpatterns = [
    path("ingest/", TelemetryIngestView.as_view(), name="telemetry-ingest"),
] + router.urls
