"""
The alerting engine: rules → alerts → notifications.

* **AlertRule** is a declarative threshold/condition on a sensor (or a device
  meta-signal like battery/offline). Rules are evaluated on every ingest for
  low latency, and also on a Celery cadence as a safety net.
* **Alert** is a raised, stateful incident (open → acknowledged → resolved).
  De-duplication keeps a single open alert per (rule, device) so a flapping
  sensor doesn't spam the notification center.
* **NotificationChannel** + **Notification** form the fan-out + the per-user
  inbox shown in the dashboard's notification center.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Severity(models.TextChoices):
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    CRITICAL = "critical", "Critical"
    EMERGENCY = "emergency", "Emergency"


class AlertRule(BaseModel):
    """A condition that, when met, raises an alert."""

    class Source(models.TextChoices):
        SENSOR = "sensor", "Sensor reading"
        BATTERY = "battery", "Device battery"
        OFFLINE = "offline", "Device offline"
        HEALTH = "health", "Health score"

    class Operator(models.TextChoices):
        GT = "gt", ">"
        GTE = "gte", "≥"
        LT = "lt", "<"
        LTE = "lte", "≤"
        EQ = "eq", "="
        NEQ = "neq", "≠"

    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="alert_rules"
    )
    name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)
    severity = models.CharField(max_length=12, choices=Severity.choices, default=Severity.WARNING)

    source = models.CharField(max_length=10, choices=Source.choices, default=Source.SENSOR)
    # Scope: a specific device and/or a sensor type. Null device = whole org.
    device = models.ForeignKey(
        "devices.Device", null=True, blank=True, on_delete=models.CASCADE,
        related_name="alert_rules",
    )
    sensor = models.ForeignKey(
        "telemetry.Sensor", null=True, blank=True, on_delete=models.CASCADE,
        related_name="alert_rules",
    )
    sensor_type = models.CharField(max_length=20, blank=True)

    operator = models.CharField(max_length=4, choices=Operator.choices, default=Operator.GT)
    threshold = models.FloatField(null=True, blank=True)
    # Require the condition to hold for N seconds before firing (debounce).
    for_seconds = models.PositiveIntegerField(default=0)
    cooldown_seconds = models.PositiveIntegerField(
        default=300, help_text="Min seconds between re-notifications for the same alert."
    )
    notify_channels = models.ManyToManyField(
        "alerts.NotificationChannel", blank=True, related_name="rules"
    )

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["organization", "is_active"]),
            models.Index(fields=["sensor", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.name

    def matches(self, value: float) -> bool:
        if self.threshold is None or value is None:
            return False
        ops = {
            self.Operator.GT: value > self.threshold,
            self.Operator.GTE: value >= self.threshold,
            self.Operator.LT: value < self.threshold,
            self.Operator.LTE: value <= self.threshold,
            self.Operator.EQ: value == self.threshold,
            self.Operator.NEQ: value != self.threshold,
        }
        return ops.get(self.operator, False)


class Alert(BaseModel):
    """A raised incident with an explicit lifecycle."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"

    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="alerts"
    )
    rule = models.ForeignKey(
        AlertRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="alerts"
    )
    device = models.ForeignKey(
        "devices.Device", null=True, blank=True, on_delete=models.CASCADE, related_name="alerts"
    )
    sensor = models.ForeignKey(
        "telemetry.Sensor", null=True, blank=True, on_delete=models.SET_NULL, related_name="alerts"
    )
    severity = models.CharField(max_length=12, choices=Severity.choices, default=Severity.WARNING)
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.OPEN, db_index=True)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    value = models.FloatField(null=True, blank=True)
    context = models.JSONField(default=dict, blank=True)

    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="alerts_acknowledged",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["organization", "status", "-created_at"]),
            models.Index(fields=["device", "status"]),
            models.Index(fields=["severity", "status"]),
        ]
        constraints = [
            # At most one OPEN alert per rule+device (de-dupe flapping sensors).
            models.UniqueConstraint(
                fields=["rule", "device"],
                condition=models.Q(status="open"),
                name="uq_open_alert_per_rule_device",
            )
        ]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.title}"


class NotificationChannel(BaseModel):
    """A delivery target: in-app, email, webhook, SMS (extensible)."""

    class Kind(models.TextChoices):
        IN_APP = "in_app", "In-app"
        EMAIL = "email", "Email"
        WEBHOOK = "webhook", "Webhook"
        SMS = "sms", "SMS"

    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="notification_channels"
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.IN_APP)
    is_active = models.BooleanField(default=True)
    # Email recipients, webhook URL, SMS numbers, etc.
    config = models.JSONField(default=dict, blank=True)
    min_severity = models.CharField(max_length=12, choices=Severity.choices, default=Severity.WARNING)

    def __str__(self) -> str:
        return f"{self.name} ({self.kind})"


class Notification(BaseModel):
    """A single user-facing entry in the notification center."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    alert = models.ForeignKey(
        Alert, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications"
    )
    severity = models.CharField(max_length=12, choices=Severity.choices, default=Severity.INFO)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["recipient", "is_read", "-created_at"])]

    def __str__(self) -> str:
        return f"→ {self.recipient}: {self.title}"
