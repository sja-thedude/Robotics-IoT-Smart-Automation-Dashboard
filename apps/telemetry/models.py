"""
Sensors and the high-volume time-series stream they produce.

Scale considerations
--------------------
* **Reading** is the hot path: thousands of writes/sec across a fleet. It uses
  a plain BigAutoField PK (cheap, monotonic, append-only) rather than the UUID
  base, and is intentionally *not* soft-deletable — old data is pruned by a
  retention job, not flagged.
* The `(sensor, time)` and `(device, time)` composite indexes serve the two
  query shapes the dashboard needs: "this sensor over time" and "everything
  from this device in a window".
* `Reading` is declared so it can be migrated to a native partitioned table or
  TimescaleDB hypertable later (see deployment guide) without touching app code
  — the manager API stays the same.
* Latest values are denormalised onto **Sensor.last_value** so dashboard cards
  and the live map don't scan the stream for a single number.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class SensorType(models.TextChoices):
    TEMPERATURE = "temperature", "Temperature"
    HUMIDITY = "humidity", "Humidity"
    MOTION = "motion", "Motion"
    GPS = "gps", "GPS"
    BATTERY = "battery", "Battery"
    PRESSURE = "pressure", "Pressure"
    LIGHT = "light", "Light"
    SOUND = "sound", "Sound / Noise"
    GAS = "gas", "Gas / Air Quality"
    PROXIMITY = "proximity", "Proximity / Distance"
    CURRENT = "current", "Current / Power"
    VIBRATION = "vibration", "Vibration"
    HEART_RATE = "heart_rate", "Heart Rate"
    CAMERA = "camera", "Camera"
    CUSTOM = "custom", "Custom"


class Sensor(BaseModel):
    """A single measurement channel attached to a device."""

    device = models.ForeignKey(
        "devices.Device", on_delete=models.CASCADE, related_name="sensors"
    )
    name = models.CharField(max_length=120)
    # Stable key the device firmware uses in its telemetry payloads.
    key = models.CharField(max_length=64, help_text="Payload key, e.g. 'temp_c'")
    sensor_type = models.CharField(
        max_length=20, choices=SensorType.choices, default=SensorType.CUSTOM, db_index=True
    )
    unit = models.CharField(max_length=24, blank=True, help_text="°C, %, lux, ppm, …")
    is_active = models.BooleanField(default=True)

    # Denormalised latest sample (avoids scanning Reading for current value).
    last_value = models.FloatField(null=True, blank=True)
    last_value_text = models.CharField(max_length=255, blank=True)
    last_reading_at = models.DateTimeField(null=True, blank=True)

    # Optional sane operating range used by the alerts engine as a default.
    min_threshold = models.FloatField(null=True, blank=True)
    max_threshold = models.FloatField(null=True, blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("device", "name")
        constraints = [
            models.UniqueConstraint(fields=["device", "key"], name="uq_sensor_device_key")
        ]
        indexes = [models.Index(fields=["device", "sensor_type"])]

    def __str__(self) -> str:
        return f"{self.device.name}/{self.name}"


class Reading(models.Model):
    """A single time-stamped sample. The platform's highest-volume table."""

    id = models.BigAutoField(primary_key=True)
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, related_name="readings")
    # Device is denormalised onto the reading so "all telemetry for a device in
    # a window" doesn't need to join through Sensor.
    device = models.ForeignKey(
        "devices.Device", on_delete=models.CASCADE, related_name="readings"
    )
    time = models.DateTimeField(default=timezone.now, db_index=True)

    # Numeric value covers most sensors; richer payloads (GPS, JSON blobs) use
    # value_text / value_json so a single table serves every sensor type.
    value = models.FloatField(null=True, blank=True)
    value_text = models.CharField(max_length=255, blank=True)
    value_json = models.JSONField(null=True, blank=True)
    quality = models.SmallIntegerField(default=100)  # 0–100 data-quality hint

    class Meta:
        # Most-recent-first scans are the common case for dashboards.
        ordering = ("-time",)
        indexes = [
            models.Index(fields=["sensor", "-time"], name="idx_reading_sensor_time"),
            models.Index(fields=["device", "-time"], name="idx_reading_device_time"),
        ]

    def __str__(self) -> str:
        return f"{self.sensor_id} @ {self.time:%Y-%m-%d %H:%M:%S} = {self.value}"


class CameraFeed(BaseModel):
    """Metadata + stream locator for a device's camera (frames live elsewhere)."""

    class Protocol(models.TextChoices):
        RTSP = "rtsp", "RTSP"
        WEBRTC = "webrtc", "WebRTC"
        HLS = "hls", "HLS"
        MJPEG = "mjpeg", "MJPEG"

    device = models.ForeignKey(
        "devices.Device", on_delete=models.CASCADE, related_name="camera_feeds"
    )
    name = models.CharField(max_length=120)
    protocol = models.CharField(max_length=10, choices=Protocol.choices, default=Protocol.RTSP)
    stream_url = models.URLField(max_length=512)
    is_active = models.BooleanField(default=True)
    # Latest captured still — useful for thumbnails and CV pipelines later.
    last_snapshot = models.ImageField(upload_to="snapshots/", null=True, blank=True)
    last_snapshot_at = models.DateTimeField(null=True, blank=True)
    resolution = models.CharField(max_length=20, blank=True, help_text="e.g. 1920x1080")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("device", "name")

    def __str__(self) -> str:
        return f"{self.device.name}/{self.name} ({self.protocol})"
