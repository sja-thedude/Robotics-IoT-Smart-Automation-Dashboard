from rest_framework import serializers

from .models import Device, DeviceCommand, DeviceGroup, DeviceHealthSnapshot


class DeviceGroupSerializer(serializers.ModelSerializer):
    full_path = serializers.CharField(read_only=True)
    device_count = serializers.IntegerField(source="devices.count", read_only=True)

    class Meta:
        model = DeviceGroup
        fields = (
            "id", "organization", "name", "parent", "description",
            "full_path", "device_count", "created_at",
        )
        read_only_fields = ("id", "full_path", "device_count", "created_at")


class DeviceSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)
    is_online = serializers.BooleanField(read_only=True)

    class Meta:
        model = Device
        fields = (
            "id", "organization", "group", "group_name", "name", "serial",
            "device_type", "status", "ip_address", "firmware_version",
            "model_number", "manufacturer", "last_seen", "battery_level",
            "signal_strength", "health_score", "latitude", "longitude",
            "altitude", "capabilities", "metadata", "is_online",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "status", "last_seen", "health_score", "battery_level",
            "signal_strength", "is_online", "created_at", "updated_at",
        )


class DeviceLocationSerializer(serializers.ModelSerializer):
    """Lightweight payload for the live map view."""

    class Meta:
        model = Device
        fields = ("id", "name", "serial", "device_type", "status",
                  "latitude", "longitude", "battery_level", "last_seen")


class DeviceCommandSerializer(serializers.ModelSerializer):
    issued_by_email = serializers.CharField(source="issued_by.email", read_only=True)

    class Meta:
        model = DeviceCommand
        fields = (
            "id", "device", "command", "payload", "status", "result", "error",
            "issued_by", "issued_by_email", "sent_at", "acked_at",
            "completed_at", "expires_at", "created_at",
        )
        read_only_fields = (
            "id", "status", "result", "error", "issued_by", "issued_by_email",
            "sent_at", "acked_at", "completed_at", "created_at",
        )


class DeviceHealthSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceHealthSnapshot
        fields = (
            "id", "device", "health_score", "battery_level", "signal_strength",
            "cpu_percent", "memory_percent", "temperature_c", "uptime_seconds",
            "details", "created_at",
        )
        read_only_fields = fields
