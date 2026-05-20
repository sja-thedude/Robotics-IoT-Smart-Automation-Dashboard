from rest_framework import serializers

from .models import Alert, AlertRule, Notification, NotificationChannel


class AlertRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertRule
        fields = (
            "id", "organization", "name", "is_active", "severity", "source",
            "device", "sensor", "sensor_type", "operator", "threshold",
            "for_seconds", "cooldown_seconds", "notify_channels", "created_at",
        )
        read_only_fields = ("id", "created_at")


class AlertSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source="device.name", read_only=True)
    sensor_name = serializers.CharField(source="sensor.name", read_only=True)
    acknowledged_by_email = serializers.CharField(
        source="acknowledged_by.email", read_only=True
    )

    class Meta:
        model = Alert
        fields = (
            "id", "organization", "rule", "device", "device_name", "sensor",
            "sensor_name", "severity", "status", "title", "message", "value",
            "context", "acknowledged_by", "acknowledged_by_email",
            "acknowledged_at", "resolved_at", "created_at",
        )
        read_only_fields = fields


class NotificationChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationChannel
        fields = ("id", "organization", "name", "kind", "is_active", "config",
                  "min_severity", "created_at")
        read_only_fields = ("id", "created_at")


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "alert", "severity", "title", "body", "is_read",
                  "read_at", "created_at")
        read_only_fields = fields
