from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role

from .models import Alert, AlertRule, Notification, NotificationChannel
from .serializers import (
    AlertRuleSerializer,
    AlertSerializer,
    NotificationChannelSerializer,
    NotificationSerializer,
)
from .services import acknowledge_alert, resolve_alert


class OrgScopedMixin:
    org_field = "organization_id"

    def scope(self, qs):
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if user.is_superuser or getattr(user, "role", None) == Role.SUPER_ADMIN:
            return qs
        return qs.filter(**{self.org_field: user.organization_id})


class AlertRuleViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = AlertRuleSerializer
    filterset_fields = ("source", "severity", "is_active", "device", "sensor")
    search_fields = ("name",)

    def get_queryset(self):
        return self.scope(AlertRule.objects.all())

    def perform_create(self, serializer):
        # Default new rules to the creator's org.
        org_id = serializer.validated_data.get("organization") or self.request.user.organization
        serializer.save(organization=org_id)


class AlertViewSet(OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = AlertSerializer
    filterset_fields = ("status", "severity", "device", "rule")
    ordering_fields = ("created_at", "severity")
    search_fields = ("title", "message")

    def get_queryset(self):
        return self.scope(Alert.objects.select_related("device", "sensor", "acknowledged_by"))

    @action(detail=False, methods=["get"])
    def active(self, request):
        qs = self.get_queryset().exclude(status=Alert.Status.RESOLVED)
        return Response(self.get_serializer(qs[:200], many=True).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        from django.db.models import Count

        qs = self.get_queryset().filter(status=Alert.Status.OPEN)
        by_sev = {r["severity"]: r["n"] for r in
                  qs.values("severity").annotate(n=Count("id"))}
        return Response({"open_total": qs.count(), "by_severity": by_sev})

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        alert = acknowledge_alert(self.get_object(), request.user)
        return Response(self.get_serializer(alert).data)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        alert = resolve_alert(self.get_object(), request.user)
        return Response(self.get_serializer(alert).data)


class NotificationChannelViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = NotificationChannelSerializer
    filterset_fields = ("kind", "is_active")

    def get_queryset(self):
        return self.scope(NotificationChannel.objects.all())


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """The per-user notification center."""

    serializer_class = NotificationSerializer
    filterset_fields = ("is_read", "severity")

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        return Response({"unread": self.get_queryset().filter(is_read=False).count()})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        n = self.get_object()
        n.is_read = True
        n.read_at = timezone.now()
        n.save(update_fields=["is_read", "read_at"])
        return Response(self.get_serializer(n).data)

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        updated = self.get_queryset().filter(is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return Response({"marked_read": updated}, status=status.HTTP_200_OK)
