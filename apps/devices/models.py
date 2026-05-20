"""
The device domain — robots, IoT nodes, gateways, and everything you control.

Modelling choices
-----------------
* A single **Device** table with a `device_type` discriminator covers robots,
  sensors-hubs, drones, cameras, etc. Type-specific attributes live in the
  schemaless `capabilities`/`metadata` JSON fields so adding a new class of
  hardware never requires a migration. Hot, queryable fields (status, battery,
  last_seen, location) are promoted to real columns + indexes.
* **DeviceGroup** is a self-referential tree (site → building → floor → cell),
  letting the dashboard roll telemetry up a hierarchy.
* **DeviceCommand** is the remote-control audit + lifecycle record: it captures
  intent, who issued it, and the round-trip through the device. The MQTT layer
  transitions it SENT → ACKED → COMPLETED/FAILED.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class DeviceType(models.TextChoices):
    ROBOT = "robot", "Robot"
    DRONE = "drone", "Drone"
    SENSOR_HUB = "sensor_hub", "Sensor Hub"
    GATEWAY = "gateway", "Gateway"
    CAMERA = "camera", "Camera"
    ACTUATOR = "actuator", "Actuator"
    WEARABLE = "wearable", "Healthcare Wearable"
    VEHICLE = "vehicle", "Autonomous Vehicle"
    CONTROLLER = "controller", "Industrial Controller (PLC)"
    OTHER = "other", "Other"


class DeviceStatus(models.TextChoices):
    PROVISIONING = "provisioning", "Provisioning"
    ONLINE = "online", "Online"
    OFFLINE = "offline", "Offline"
    DEGRADED = "degraded", "Degraded"
    MAINTENANCE = "maintenance", "Maintenance"
    ERROR = "error", "Error"
    DECOMMISSIONED = "decommissioned", "Decommissioned"


class DeviceGroup(BaseModel):
    """Hierarchical grouping: site / building / floor / production cell."""

    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="device_groups"
    )
    name = models.CharField(max_length=160)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        indexes = [models.Index(fields=["organization", "parent"])]

    def __str__(self) -> str:
        return self.name

    @property
    def full_path(self) -> str:
        node, parts = self, []
        while node is not None:
            parts.append(node.name)
            node = node.parent
        return " / ".join(reversed(parts))


class Device(BaseModel):
    """A single managed endpoint — robot, drone, sensor hub, camera, etc."""

    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="devices"
    )
    group = models.ForeignKey(
        DeviceGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name="devices"
    )
    name = models.CharField(max_length=160)
    # Stable, human/operator-facing identifier burned into firmware. Used as
    # the MQTT topic segment and for device-side authentication.
    serial = models.CharField(max_length=128, unique=True, db_index=True)
    device_type = models.CharField(
        max_length=20, choices=DeviceType.choices, default=DeviceType.OTHER, db_index=True
    )
    status = models.CharField(
        max_length=16, choices=DeviceStatus.choices,
        default=DeviceStatus.PROVISIONING, db_index=True,
    )

    # ── Network / firmware ───────────────────────────────────────────────
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    firmware_version = models.CharField(max_length=64, blank=True)
    model_number = models.CharField(max_length=128, blank=True)
    manufacturer = models.CharField(max_length=128, blank=True)

    # ── Liveness / health (hot columns, indexed for dashboards) ──────────
    last_seen = models.DateTimeField(null=True, blank=True, db_index=True)
    battery_level = models.FloatField(null=True, blank=True)  # percent 0–100
    signal_strength = models.IntegerField(null=True, blank=True)  # dBm / rssi
    health_score = models.FloatField(default=100.0)  # 0–100 composite

    # ── Geo (denormalised latest position for map rendering) ─────────────
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    altitude = models.FloatField(null=True, blank=True)

    # ── Extensible, schemaless attributes ────────────────────────────────
    capabilities = models.JSONField(
        default=dict, blank=True,
        help_text="Declared abilities, e.g. {'commands': ['move','dock'], 'has_camera': true}",
    )
    metadata = models.JSONField(default=dict, blank=True)

    # ── Security ─────────────────────────────────────────────────────────
    # Hash of the device's provisioning/API token; the plaintext is shown once.
    auth_token_hash = models.CharField(max_length=128, blank=True)
    service_account = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="owned_device",
    )

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "device_type"]),
            models.Index(fields=["status", "last_seen"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.serial})"

    # ── Behaviour ────────────────────────────────────────────────────────
    @property
    def is_online(self) -> bool:
        return self.status == DeviceStatus.ONLINE

    @property
    def command_topic(self) -> str:
        base = settings.MQTT["BASE_TOPIC"]
        return f"{base}/devices/{self.serial}/commands"

    @property
    def telemetry_topic(self) -> str:
        base = settings.MQTT["BASE_TOPIC"]
        return f"{base}/devices/{self.serial}/telemetry"

    def mark_seen(self, *, save: bool = True) -> None:
        """Record a heartbeat; flip OFFLINE/PROVISIONING devices to ONLINE."""
        self.last_seen = timezone.now()
        if self.status in {DeviceStatus.OFFLINE, DeviceStatus.PROVISIONING}:
            self.status = DeviceStatus.ONLINE
        if save:
            self.save(update_fields=["last_seen", "status", "updated_at"])


class DeviceCommand(BaseModel):
    """A remote-control instruction and its lifecycle (the control system)."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        ACKED = "acked", "Acknowledged"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="commands")
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="commands_issued",
    )
    command = models.CharField(max_length=64)  # e.g. "move", "dock", "reboot"
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    sent_at = models.DateTimeField(null=True, blank=True)
    acked_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["device", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.command} → {self.device} [{self.status}]"


class DeviceHealthSnapshot(BaseModel):
    """
    Periodic health rollup written by Celery, separate from raw telemetry.

    Keeping rollups in their own table lets the dashboard render trend lines
    cheaply without scanning the high-volume telemetry stream.
    """

    device = models.ForeignKey(
        Device, on_delete=models.CASCADE, related_name="health_snapshots"
    )
    health_score = models.FloatField()
    battery_level = models.FloatField(null=True, blank=True)
    signal_strength = models.IntegerField(null=True, blank=True)
    cpu_percent = models.FloatField(null=True, blank=True)
    memory_percent = models.FloatField(null=True, blank=True)
    temperature_c = models.FloatField(null=True, blank=True)
    uptime_seconds = models.BigIntegerField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["device", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.device} health={self.health_score:.0f} @ {self.created_at:%Y-%m-%d %H:%M}"
