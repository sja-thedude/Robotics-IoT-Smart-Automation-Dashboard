from rest_framework import serializers

from .models import CameraFeed, Reading, Sensor


class SensorSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source="device.name", read_only=True)

    class Meta:
        model = Sensor
        fields = (
            "id", "device", "device_name", "name", "key", "sensor_type", "unit",
            "is_active", "last_value", "last_value_text", "last_reading_at",
            "min_threshold", "max_threshold", "metadata", "created_at",
        )
        read_only_fields = ("id", "device_name", "last_value", "last_value_text",
                            "last_reading_at", "created_at")


class ReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reading
        fields = ("id", "sensor", "device", "time", "value", "value_text",
                  "value_json", "quality")
        read_only_fields = ("id",)


class IngestReadingSerializer(serializers.Serializer):
    """
    Payload accepted from devices (HTTP fallback) and the MQTT bridge.

    A device posts a batch of channel readings keyed by sensor `key`; the
    service layer resolves keys to Sensor rows and writes the time series.
    """

    serial = serializers.CharField()
    time = serializers.DateTimeField(required=False)
    readings = serializers.DictField(
        child=serializers.JSONField(), help_text="{ sensor_key: value, ... }"
    )
    location = serializers.DictField(required=False)  # {lat, lon, alt}
    battery_level = serializers.FloatField(required=False)
    signal_strength = serializers.IntegerField(required=False)


class CameraFeedSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source="device.name", read_only=True)

    class Meta:
        model = CameraFeed
        fields = ("id", "device", "device_name", "name", "protocol", "stream_url",
                  "is_active", "last_snapshot", "last_snapshot_at", "resolution",
                  "metadata", "created_at")
        read_only_fields = ("id", "device_name", "last_snapshot", "last_snapshot_at",
                            "created_at")


class TimeBucketSerializer(serializers.Serializer):
    """Aggregated point returned by the chart/aggregation endpoint."""

    bucket = serializers.DateTimeField()
    avg = serializers.FloatField()
    min = serializers.FloatField()
    max = serializers.FloatField()
    count = serializers.IntegerField()
