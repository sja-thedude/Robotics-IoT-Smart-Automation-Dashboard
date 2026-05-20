from django.db.models import Count, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.permissions import HasDeviceAccess

from .filters import DeviceFilter
from .models import Device, DeviceCommand, DeviceGroup, DeviceHealthSnapshot, DeviceStatus
from .serializers import (
    DeviceCommandSerializer,
    DeviceGroupSerializer,
    DeviceHealthSnapshotSerializer,
    DeviceLocationSerializer,
    DeviceSerializer,
)
from .services import dispatch_command


class OrgScopedMixin:
    """Confines querysets to the caller's organization (super admins see all)."""

    org_field = "organization_id"

    def scope(self, qs):
        user = self.request.user
        # Anonymous (incl. OpenAPI schema introspection) sees nothing.
        if not user.is_authenticated:
            return qs.none()
        if user.is_superuser or getattr(user, "role", None) == Role.SUPER_ADMIN:
            return qs
        return qs.filter(**{self.org_field: user.organization_id})


class DeviceGroupViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = DeviceGroupSerializer
    search_fields = ("name", "description")
    filterset_fields = ("organization", "parent")

    def get_queryset(self):
        return self.scope(DeviceGroup.objects.select_related("parent"))


class DeviceViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = DeviceSerializer
    permission_classes = [HasDeviceAccess]
    filterset_class = DeviceFilter
    search_fields = ("name", "serial", "model_number", "manufacturer")
    ordering_fields = ("name", "last_seen", "health_score", "battery_level", "created_at")

    def get_queryset(self):
        return self.scope(Device.objects.select_related("group", "organization"))

    # ── Fleet summary for dashboard cards ────────────────────────────────
    @action(detail=False, methods=["get"])
    def stats(self, request):
        qs = self.get_queryset()
        by_status = {
            row["status"]: row["n"]
            for row in qs.values("status").annotate(n=Count("id"))
        }
        return Response({
            "total": qs.count(),
            "online": by_status.get(DeviceStatus.ONLINE, 0),
            "offline": by_status.get(DeviceStatus.OFFLINE, 0),
            "degraded": by_status.get(DeviceStatus.DEGRADED, 0),
            "error": by_status.get(DeviceStatus.ERROR, 0),
            "by_status": by_status,
            "by_type": {
                row["device_type"]: row["n"]
                for row in qs.values("device_type").annotate(n=Count("id"))
            },
        })

    # ── Map markers ──────────────────────────────────────────────────────
    @action(detail=False, methods=["get"])
    def map(self, request):
        qs = self.get_queryset().filter(
            latitude__isnull=False, longitude__isnull=False
        )
        return Response(DeviceLocationSerializer(qs, many=True).data)

    # ── Remote control ───────────────────────────────────────────────────
    @action(detail=True, methods=["post"])
    def command(self, request, pk=None):
        device = self.get_object()  # runs HasDeviceAccess object check
        if not request.user.can_access_device(device, control=True):
            raise PermissionDenied("You lack control permission on this device.")

        command = request.data.get("command")
        if not command:
            raise ValidationError({"command": "This field is required."})

        declared = device.capabilities.get("commands")
        if declared and command not in declared:
            raise ValidationError(
                {"command": f"Device does not support '{command}'. "
                            f"Supported: {declared}"}
            )

        cmd = dispatch_command(
            device=device,
            command=command,
            payload=request.data.get("payload", {}),
            actor=request.user,
        )
        return Response(DeviceCommandSerializer(cmd).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get"])
    def commands(self, request, pk=None):
        device = self.get_object()
        qs = device.commands.all()[:100]
        return Response(DeviceCommandSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"])
    def health(self, request, pk=None):
        device = self.get_object()
        qs = device.health_snapshots.all()[:200]
        return Response(DeviceHealthSnapshotSerializer(qs, many=True).data)


class DeviceCommandViewSet(OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only audit view of every command (issuing happens via /devices)."""

    serializer_class = DeviceCommandSerializer
    org_field = "device__organization_id"
    filterset_fields = ("device", "status", "command")
    ordering_fields = ("created_at", "completed_at")

    def get_queryset(self):
        return self.scope(DeviceCommand.objects.select_related("device", "issued_by"))
