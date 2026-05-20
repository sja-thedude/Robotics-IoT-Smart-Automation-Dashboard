"""
WebSocket consumers — the live edge of the dashboard.

All consumers share one server→client envelope: `{"event": <type>, "payload":
{...}}`, emitted by the `broadcast` handler. Producers anywhere in the codebase
(signals, services, MQTT ingest, Celery) call `apps.core.realtime.broadcast`
with a group + event + payload; the consumer just relays it. Authorisation is
enforced at `connect`: every group a socket joins is one it's allowed to see.
"""
from __future__ import annotations

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.accounts.models import Role
from apps.core.realtime import (
    GROUP_ALERTS,
    group_for_device,
    group_for_org,
)


class BaseConsumer(AsyncJsonWebsocketConsumer):
    """Shared auth + envelope handling."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)  # unauthorized
            return
        self.user = user
        self.groups_joined: list[str] = []
        await self.accept()
        await self.on_authenticated()

    async def on_authenticated(self):  # overridden by subclasses
        ...

    async def disconnect(self, code):
        for group in getattr(self, "groups_joined", []):
            await self.channel_layer.group_discard(group, self.channel_name)

    async def join(self, group: str):
        await self.channel_layer.group_add(group, self.channel_name)
        self.groups_joined.append(group)

    async def broadcast(self, message):
        """Channel-layer handler: relay {event, payload} to the client."""
        await self.send_json({"event": message["event"], "payload": message["payload"]})

    async def send_json(self, content, close=False):
        await super().send(text_data=json.dumps(content, default=str), close=close)


class DashboardConsumer(BaseConsumer):
    """Org-wide firehose for the main dashboard (device state + alerts)."""

    async def on_authenticated(self):
        if self.user.organization_id:
            await self.join(group_for_org(self.user.organization_id))
        await self.join(GROUP_ALERTS)
        await self.send_json({"event": "connected",
                              "payload": {"scope": "dashboard"}})


class DeviceConsumer(BaseConsumer):
    """Per-device stream for a device detail page (telemetry + commands)."""

    async def on_authenticated(self):
        self.device_id = self.scope["url_route"]["kwargs"]["device_id"]
        allowed = await self._can_view(self.device_id)
        if not allowed:
            await self.close(code=4403)  # forbidden
            return
        await self.join(group_for_device(self.device_id))
        await self.send_json({"event": "connected",
                              "payload": {"device_id": self.device_id}})

    @database_sync_to_async
    def _can_view(self, device_id) -> bool:
        from apps.devices.models import Device

        device = Device.objects.filter(id=device_id).first()
        if device is None:
            return False
        return self.user.can_access_device(device)


class AlertConsumer(BaseConsumer):
    """Alert feed + this user's private notification channel."""

    async def on_authenticated(self):
        await self.join(GROUP_ALERTS)
        if self.user.organization_id:
            await self.join(group_for_org(self.user.organization_id))
        await self.join(f"user.{self.user.id}")  # personal notifications
        await self.send_json({"event": "connected", "payload": {"scope": "alerts"}})
