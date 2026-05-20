from django.db.models import Avg, Count, Max, Min
from django.db.models.functions import Trunc
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.devices.models import Device

from .models import CameraFeed, Reading, Sensor
from .serializers import (
    CameraFeedSerializer,
    IngestReadingSerializer,
    ReadingSerializer,
    SensorSerializer,
)
from .services import ingest_payload


class OrgScopedMixin:
    org_field = "device__organization_id"

    def scope(self, qs):
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if user.is_superuser or getattr(user, "role", None) == Role.SUPER_ADMIN:
            return qs
        return qs.filter(**{self.org_field: user.organization_id})


class SensorViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = SensorSerializer
    filterset_fields = ("device", "sensor_type", "is_active")
    search_fields = ("name", "key")

    def get_queryset(self):
        return self.scope(Sensor.objects.select_related("device"))

    @action(detail=True, methods=["get"])
    def readings(self, request, pk=None):
        """Recent raw samples for one sensor (use ?limit=, ?since=)."""
        sensor = self.get_object()
        qs = sensor.readings.all()
        since = request.query_params.get("since")
        if since:
            qs = qs.filter(time__gte=since)
        limit = min(int(request.query_params.get("limit", 500)), 5000)
        return Response(ReadingSerializer(qs[:limit], many=True).data)

    @action(detail=True, methods=["get"])
    def aggregate(self, request, pk=None):
        """
        Down-sampled series for charts: average/min/max per time bucket.

        Query params: ?bucket=minute|hour|day (default minute), ?since=ISO.
        """
        sensor = self.get_object()
        bucket = request.query_params.get("bucket", "minute")
        if bucket not in {"minute", "hour", "day"}:
            raise ValidationError({"bucket": "Must be minute, hour, or day."})
        qs = sensor.readings.all()
        since = request.query_params.get("since")
        if since:
            qs = qs.filter(time__gte=since)
        data = (
            qs.annotate(b=Trunc("time", bucket))
            .values("b")
            .annotate(avg=Avg("value"), min=Min("value"),
                      max=Max("value"), count=Count("id"))
            .order_by("b")
        )
        return Response([
            {"bucket": r["b"], "avg": r["avg"], "min": r["min"],
             "max": r["max"], "count": r["count"]}
            for r in data
        ])


class ReadingViewSet(OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ReadingSerializer
    filterset_fields = ("device", "sensor")
    ordering_fields = ("time",)

    def get_queryset(self):
        return self.scope(Reading.objects.select_related("sensor", "device"))


class CameraFeedViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = CameraFeedSerializer
    filterset_fields = ("device", "protocol", "is_active")

    def get_queryset(self):
        return self.scope(CameraFeed.objects.select_related("device"))


class TelemetryIngestView(APIView):
    """
    HTTP fallback ingest for devices that can't speak MQTT.

    Authenticated with the device's API token (service account) or any
    control-capable user. The MQTT bridge is the primary path; this endpoint
    keeps the contract identical for edge devices behind restrictive networks.
    """

    serializer_class = IngestReadingSerializer

    def post(self, request):
        serializer = IngestReadingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = ingest_payload(serializer.validated_data)
        except Device.DoesNotExist:
            raise ValidationError({"serial": "Unknown device serial."})
        return Response(result, status=status.HTTP_201_CREATED)
