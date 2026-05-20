"""
Device-control service layer.

`dispatch_command` is the single, testable entry point for remote control:
it persists intent, hands the message to the MQTT publisher, mirrors the
event onto the WebSocket layer, and writes an audit record. Views and Celery
tasks both go through here so the side-effects stay consistent.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.realtime import broadcast, group_for_device
from apps.core.services import record_audit

from .models import Device, DeviceCommand

logger = logging.getLogger("robogrid.devices")

DEFAULT_COMMAND_TTL = timedelta(seconds=120)


def dispatch_command(
    *, device: Device, command: str, payload: dict | None = None, actor=None,
    ttl: timedelta = DEFAULT_COMMAND_TTL,
) -> DeviceCommand:
    """Queue a command, publish it to the device, and broadcast the event."""
    cmd = DeviceCommand.objects.create(
        device=device,
        command=command,
        payload=payload or {},
        issued_by=actor,
        expires_at=timezone.now() + ttl,
        status=DeviceCommand.Status.QUEUED,
    )

    # Publish over MQTT. Imported lazily to avoid a hard dependency at import
    # time (the broker may be unreachable in some deployments/tests).
    try:
        from apps.mqtt.client import publish_command

        publish_command(cmd)
        cmd.status = DeviceCommand.Status.SENT
        cmd.sent_at = timezone.now()
        cmd.save(update_fields=["status", "sent_at", "updated_at"])
    except Exception as exc:  # noqa: BLE001 - degrade gracefully if broker down
        logger.warning("MQTT publish failed for command %s: %s", cmd.id, exc)
        cmd.error = f"publish failed: {exc}"
        cmd.save(update_fields=["error", "updated_at"])

    broadcast(
        group_for_device(device.id),
        "device.command",
        {"command_id": str(cmd.id), "device_id": str(device.id),
         "command": command, "status": cmd.status},
    )
    record_audit(
        action="command", target_type="device", target_id=device.id,
        summary=f"Command '{command}' issued", actor=actor,
        metadata={"command_id": str(cmd.id), "payload": payload or {}},
    )
    return cmd


def transition_command(cmd: DeviceCommand, status: str, *, result=None, error: str = "") -> None:
    """Advance a command's lifecycle (called by the MQTT ack/result handler)."""
    cmd.status = status
    now = timezone.now()
    if status == DeviceCommand.Status.ACKED:
        cmd.acked_at = now
    elif status in {DeviceCommand.Status.COMPLETED, DeviceCommand.Status.FAILED}:
        cmd.completed_at = now
    if result is not None:
        cmd.result = result
    if error:
        cmd.error = error
    cmd.save()

    broadcast(
        group_for_device(cmd.device_id),
        "device.command",
        {"command_id": str(cmd.id), "device_id": str(cmd.device_id),
         "command": cmd.command, "status": status},
    )
