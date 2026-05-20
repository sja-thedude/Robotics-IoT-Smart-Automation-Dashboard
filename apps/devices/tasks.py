"""
Background jobs for fleet health.

* `detect_offline_devices` — the watchdog: any device that has missed its
  heartbeat window is flipped to OFFLINE, which fans out an alert + WS event.
* `rollup_device_health` — periodically snapshots a composite health score so
  the dashboard can draw trend lines without scanning raw telemetry.
* `expire_stale_commands` — fails commands the device never acknowledged.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("robogrid.devices")

OFFLINE_AFTER = timedelta(seconds=120)  # missed heartbeats → offline


@shared_task
def detect_offline_devices() -> int:
    from .models import Device, DeviceStatus

    cutoff = timezone.now() - OFFLINE_AFTER
    stale = Device.objects.filter(
        last_seen__lt=cutoff,
        status__in=[DeviceStatus.ONLINE, DeviceStatus.DEGRADED],
    )
    count = 0
    for device in stale.iterator():
        device.status = DeviceStatus.OFFLINE
        device.save(update_fields=["status", "updated_at"])  # signal fires alert/WS
        # Raise an offline alert through the alerts engine.
        from apps.alerts.services import raise_device_offline_alert

        raise_device_offline_alert(device)
        count += 1
    if count:
        logger.info("Marked %s device(s) offline", count)
    return count


@shared_task
def rollup_device_health() -> int:
    from .models import Device, DeviceHealthSnapshot, DeviceStatus

    snapshots = []
    for device in Device.objects.exclude(status=DeviceStatus.DECOMMISSIONED).iterator():
        score = _compute_health_score(device)
        if score != device.health_score:
            device.health_score = score
            device.save(update_fields=["health_score", "updated_at"])
        snapshots.append(
            DeviceHealthSnapshot(
                device=device,
                health_score=score,
                battery_level=device.battery_level,
                signal_strength=device.signal_strength,
            )
        )
    if snapshots:
        DeviceHealthSnapshot.objects.bulk_create(snapshots, batch_size=500)
    return len(snapshots)


def _compute_health_score(device) -> float:
    """Simple weighted composite — deliberately easy to extend with ML later."""
    from .models import DeviceStatus

    score = 100.0
    if device.status == DeviceStatus.OFFLINE:
        score -= 60
    elif device.status in {DeviceStatus.DEGRADED, DeviceStatus.ERROR}:
        score -= 35
    elif device.status == DeviceStatus.MAINTENANCE:
        score -= 15
    if device.battery_level is not None and device.battery_level < 20:
        score -= (20 - device.battery_level)
    if device.signal_strength is not None and device.signal_strength < -90:
        score -= 10
    return max(0.0, min(100.0, score))


@shared_task
def expire_stale_commands() -> int:
    from .models import DeviceCommand

    now = timezone.now()
    stale = DeviceCommand.objects.filter(
        expires_at__lt=now,
        status__in=[DeviceCommand.Status.QUEUED, DeviceCommand.Status.SENT],
    )
    return stale.update(status=DeviceCommand.Status.EXPIRED, updated_at=now)
