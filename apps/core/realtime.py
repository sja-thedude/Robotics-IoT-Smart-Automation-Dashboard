"""
Helpers for pushing events onto the Channels layer from synchronous code.

Domain code (REST views, Celery tasks, MQTT ingest) calls `broadcast` to fan
an event out to every WebSocket subscriber of a group. This is the single
seam between "something happened" and "the dashboard updates live", so all
real-time payloads share one envelope shape.
"""
from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def group_for_device(device_id) -> str:
    return f"device.{device_id}"


def group_for_org(org_id) -> str:
    return f"org.{org_id}"


GROUP_ALERTS = "alerts"
GROUP_DASHBOARD = "dashboard"


def broadcast(group: str, event_type: str, payload: dict[str, Any]) -> None:
    """
    Send `payload` to every consumer subscribed to `group`.

    The consumer-side handler is named `broadcast` (see realtime.consumers),
    and re-emits `{type, ...payload}` to the client. Safe to call when no
    channel layer is configured (e.g. unit tests) — it simply no-ops.
    """
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        group,
        {"type": "broadcast", "event": event_type, "payload": payload},
    )
