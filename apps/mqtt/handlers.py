"""
Message handlers for the MQTT bridge.

These translate raw broker messages into domain actions, reusing the exact
same service-layer entry points the HTTP API uses (telemetry.ingest_payload,
devices.transition_command). That keeps MQTT and REST behaviourally identical.
"""
from __future__ import annotations

import json
import logging

from django.utils import timezone

from . import topics

logger = logging.getLogger("robogrid.mqtt")


def handle_telemetry(topic: str, payload: bytes) -> None:
    serial = topics.serial_from_topic(topic)
    if not serial:
        return
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("bad telemetry JSON on %s", topic)
        return

    data.setdefault("serial", serial)

    from apps.devices.models import Device
    from apps.telemetry.services import ingest_payload

    try:
        ingest_payload(data)
    except Device.DoesNotExist:
        logger.warning("telemetry for unknown device serial=%s", serial)


def handle_status(topic: str, payload: bytes) -> None:
    """Device-reported status/health heartbeat."""
    serial = topics.serial_from_topic(topic)
    if not serial:
        return
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return

    from apps.devices.models import Device, DeviceStatus

    device = Device.objects.filter(serial=serial).first()
    if device is None:
        return

    fields = ["last_seen", "updated_at"]
    device.last_seen = timezone.now()
    reported = data.get("status")
    if reported in DeviceStatus.values:
        device.status = reported
        fields.append("status")
    else:
        device.mark_seen(save=False)
        fields.append("status")
    for key in ("battery_level", "signal_strength", "firmware_version", "ip_address"):
        if key in data:
            setattr(device, key, data[key])
            fields.append(key)
    device.save(update_fields=list(set(fields)))


def handle_result(topic: str, payload: bytes) -> None:
    """A device's acknowledgement / result for a previously sent command."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return

    from apps.devices.models import DeviceCommand
    from apps.devices.services import transition_command

    command_id = data.get("command_id")
    if not command_id:
        return
    cmd = DeviceCommand.objects.filter(id=command_id).first()
    if cmd is None:
        return

    status_map = {
        "ack": DeviceCommand.Status.ACKED,
        "acknowledged": DeviceCommand.Status.ACKED,
        "ok": DeviceCommand.Status.COMPLETED,
        "completed": DeviceCommand.Status.COMPLETED,
        "done": DeviceCommand.Status.COMPLETED,
        "error": DeviceCommand.Status.FAILED,
        "failed": DeviceCommand.Status.FAILED,
    }
    new_status = status_map.get(str(data.get("status", "")).lower(),
                                DeviceCommand.Status.ACKED)
    transition_command(
        cmd, new_status,
        result=data.get("result"), error=data.get("error", ""),
    )


def dispatch(topic: str, payload: bytes) -> None:
    """Route an inbound message to the right handler by topic leaf."""
    if topic.endswith("/telemetry"):
        handle_telemetry(topic, payload)
    elif topic.endswith("/status"):
        handle_status(topic, payload)
    elif topic.endswith("/results"):
        handle_result(topic, payload)
    else:
        logger.debug("ignoring message on %s", topic)
