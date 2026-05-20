"""
Async alert work: the periodic safety-net evaluation and channel delivery.

Inline evaluation on ingest covers the common path; this Celery task re-checks
device-meta rules (battery, health) and acts as a backstop if an ingest path
ever skips evaluation.
"""
from __future__ import annotations

import logging

import requests
from celery import shared_task
from django.core.mail import send_mail

logger = logging.getLogger("robogrid.alerts")


@shared_task
def evaluate_threshold_alerts() -> int:
    """Periodic backstop: evaluate battery/health rules across the fleet."""
    from apps.devices.models import Device, DeviceStatus

    from .models import AlertRule, Severity
    from .services import raise_alert

    raised = 0
    battery_rules = list(AlertRule.objects.filter(
        is_active=True, source=AlertRule.Source.BATTERY
    ))
    health_rules = list(AlertRule.objects.filter(
        is_active=True, source=AlertRule.Source.HEALTH
    ))

    for device in Device.objects.exclude(status=DeviceStatus.DECOMMISSIONED).iterator():
        for rule in battery_rules:
            if rule.organization_id != device.organization_id:
                continue
            if device.battery_level is not None and rule.matches(device.battery_level):
                raise_alert(rule=rule, device=device, value=device.battery_level,
                            title=f"{device.name} low battery",
                            message=f"Battery at {device.battery_level}%.")
                raised += 1
        for rule in health_rules:
            if rule.organization_id != device.organization_id:
                continue
            if rule.matches(device.health_score):
                raise_alert(rule=rule, device=device, value=device.health_score,
                            title=f"{device.name} health degraded",
                            message=f"Health score {device.health_score}.")
                raised += 1
    return raised


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def deliver_notification(self, alert_id: str, channel_id: str) -> str:
    """Deliver one alert to one external channel (email / webhook / sms)."""
    from .models import Alert, NotificationChannel

    alert = Alert.objects.filter(id=alert_id).first()
    channel = NotificationChannel.objects.filter(id=channel_id, is_active=True).first()
    if not alert or not channel:
        return "skipped"

    try:
        if channel.kind == NotificationChannel.Kind.EMAIL:
            recipients = channel.config.get("recipients", [])
            send_mail(
                subject=f"[RoboGrid {alert.severity.upper()}] {alert.title}",
                message=alert.message,
                from_email=channel.config.get("from_email", "alerts@robogrid.ai"),
                recipient_list=recipients,
                fail_silently=False,
            )
        elif channel.kind == NotificationChannel.Kind.WEBHOOK:
            requests.post(
                channel.config["url"],
                json={"id": str(alert.id), "title": alert.title,
                      "severity": alert.severity, "message": alert.message,
                      "device_id": str(alert.device_id) if alert.device_id else None},
                timeout=10,
            )
        # SMS would integrate a provider (Twilio etc.) here.
        return "delivered"
    except Exception as exc:  # noqa: BLE001
        logger.warning("notification delivery failed (%s): %s", channel.kind, exc)
        raise self.retry(exc=exc)
