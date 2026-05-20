"""
The alert engine + notification fan-out.

`evaluate_device_readings` is called inline on every telemetry ingest so
threshold breaches surface within milliseconds. `raise_alert` centralises
de-duplication, the live WS push, the notification fan-out, and the audit
record so every alert — threshold, offline, battery — behaves identically.
"""
from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.realtime import GROUP_ALERTS, broadcast, group_for_org
from apps.core.services import record_audit

from .models import Alert, AlertRule, Notification, NotificationChannel, Severity

logger = logging.getLogger("robogrid.alerts")


# ── Public API ─────────────────────────────────────────────────────────────
def evaluate_device_readings(device, sensor_ids: list) -> None:
    """Check every active rule that could be affected by these sensors."""
    if not sensor_ids:
        return
    rules = (
        AlertRule.objects.filter(
            organization_id=device.organization_id,
            is_active=True,
            source=AlertRule.Source.SENSOR,
        )
        .filter(_rule_scope_q(device, sensor_ids))
        .select_related("sensor")
        .prefetch_related("notify_channels")
    )
    sensors = {s.id: s for s in device.sensors.filter(id__in=sensor_ids)}

    for rule in rules:
        for sensor in _sensors_for_rule(rule, sensors):
            value = sensor.last_value
            if value is None:
                continue
            if rule.matches(value):
                raise_alert(
                    rule=rule, device=device, sensor=sensor, value=value,
                    title=f"{sensor.name} {rule.get_operator_display()} {rule.threshold}",
                    message=f"{sensor.name} reading {value}{sensor.unit} breached "
                            f"threshold {rule.threshold}{sensor.unit}.",
                )
            else:
                _auto_resolve(rule, device)


def raise_alert(*, rule=None, device=None, sensor=None, value=None, title,
                message="", severity=None, organization=None,
                channels=None) -> Alert | None:
    """
    Open (or refresh) an alert, then notify — idempotent per (rule, device).
    """
    org_id = (organization.id if organization else None) or (
        device.organization_id if device else None
    )
    sev = severity or (rule.severity if rule else Severity.WARNING)

    try:
        with transaction.atomic():
            alert, created = Alert.objects.get_or_create(
                rule=rule, device=device, status=Alert.Status.OPEN,
                defaults=dict(
                    organization_id=org_id, sensor=sensor, severity=sev,
                    title=title, message=message, value=value,
                ),
            )
    except IntegrityError:
        # Race on the partial-unique constraint: the alert already exists.
        alert = Alert.objects.filter(rule=rule, device=device,
                                     status=Alert.Status.OPEN).first()
        created = False

    if alert is None:
        return None

    if not created:
        # Refresh the live value but respect the per-rule cooldown for notifies.
        alert.value = value
        alert.message = message or alert.message
        alert.save(update_fields=["value", "message", "updated_at"])
        if not _cooldown_elapsed(alert, rule):
            return alert

    _emit(alert, rule=rule, channels=channels)
    return alert


def raise_device_offline_alert(device) -> Alert | None:
    rule = AlertRule.objects.filter(
        organization_id=device.organization_id, source=AlertRule.Source.OFFLINE,
        is_active=True,
    ).filter(_device_q(device)).first()
    return raise_alert(
        rule=rule, device=device, organization=device.organization,
        severity=Severity.CRITICAL if rule is None else rule.severity,
        title=f"{device.name} is offline",
        message=f"Device {device.serial} missed its heartbeat window.",
    )


def acknowledge_alert(alert: Alert, user) -> Alert:
    alert.status = Alert.Status.ACKNOWLEDGED
    alert.acknowledged_by = user
    alert.acknowledged_at = timezone.now()
    alert.save(update_fields=["status", "acknowledged_by", "acknowledged_at", "updated_at"])
    _broadcast_alert(alert, "alert.updated")
    record_audit(action="alert", target_type="alert", target_id=alert.id,
                 summary=f"Acknowledged: {alert.title}", actor=user)
    return alert


def resolve_alert(alert: Alert, user=None) -> Alert:
    alert.status = Alert.Status.RESOLVED
    alert.resolved_at = timezone.now()
    alert.save(update_fields=["status", "resolved_at", "updated_at"])
    _broadcast_alert(alert, "alert.resolved")
    record_audit(action="alert", target_type="alert", target_id=alert.id,
                 summary=f"Resolved: {alert.title}", actor=user)
    return alert


# ── Internals ──────────────────────────────────────────────────────────────
def _emit(alert: Alert, *, rule=None, channels=None) -> None:
    """Push live + create notifications + dispatch external channels."""
    alert.last_notified_at = timezone.now()
    alert.save(update_fields=["last_notified_at", "updated_at"])

    _broadcast_alert(alert, "alert.raised")

    targets = list(channels) if channels else (
        list(rule.notify_channels.all()) if rule else []
    )
    if not targets:
        targets = list(
            NotificationChannel.objects.filter(
                organization_id=alert.organization_id,
                kind=NotificationChannel.Kind.IN_APP, is_active=True,
            )
        )
    _fan_out(alert, targets)
    record_audit(action="alert", target_type="alert", target_id=alert.id,
                 summary=f"Raised [{alert.severity}]: {alert.title}")


def _fan_out(alert: Alert, channels) -> None:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    severity_rank = {s: i for i, s in enumerate(
        [Severity.INFO, Severity.WARNING, Severity.CRITICAL, Severity.EMERGENCY]
    )}

    for channel in channels:
        if severity_rank.get(alert.severity, 0) < severity_rank.get(channel.min_severity, 0):
            continue
        if channel.kind == NotificationChannel.Kind.IN_APP:
            recipients = User.objects.filter(
                organization_id=alert.organization_id, is_active=True
            ).exclude(is_service_account=True)
            Notification.objects.bulk_create([
                Notification(recipient=u, alert=alert, severity=alert.severity,
                             title=alert.title, body=alert.message)
                for u in recipients
            ])
            for u in recipients:
                broadcast(f"user.{u.id}", "notification",
                          {"alert_id": str(alert.id), "title": alert.title,
                           "severity": alert.severity})
        else:
            # Email / webhook / SMS are delivered async to keep ingest fast.
            from .tasks import deliver_notification

            deliver_notification.delay(str(alert.id), str(channel.id))


def _broadcast_alert(alert: Alert, event: str) -> None:
    payload = {
        "id": str(alert.id), "title": alert.title, "severity": alert.severity,
        "status": alert.status, "device_id": str(alert.device_id) if alert.device_id else None,
        "value": alert.value, "created_at": alert.created_at.isoformat(),
    }
    broadcast(GROUP_ALERTS, event, payload)
    if alert.organization_id:
        broadcast(group_for_org(alert.organization_id), event, payload)


def _auto_resolve(rule, device) -> None:
    Alert.objects.filter(rule=rule, device=device, status=Alert.Status.OPEN).update(
        status=Alert.Status.RESOLVED, resolved_at=timezone.now()
    )


def _cooldown_elapsed(alert: Alert, rule) -> bool:
    if alert.last_notified_at is None or rule is None:
        return True
    elapsed = (timezone.now() - alert.last_notified_at).total_seconds()
    return elapsed >= rule.cooldown_seconds


def _rule_scope_q(device, sensor_ids):
    from django.db.models import Q

    return (
        Q(sensor_id__in=sensor_ids)
        | Q(device=device, sensor__isnull=True)
        | (Q(device__isnull=True) & (Q(sensor_type="") | Q(sensor__isnull=True)))
    )


def _device_q(device):
    from django.db.models import Q

    return Q(device=device) | Q(device__isnull=True)


def _sensors_for_rule(rule, sensors: dict):
    if rule.sensor_id:
        s = sensors.get(rule.sensor_id)
        return [s] if s else []
    if rule.sensor_type:
        return [s for s in sensors.values() if s.sensor_type == rule.sensor_type]
    return list(sensors.values())
