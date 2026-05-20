"""
MQTT client wrapper (paho-mqtt v2).

Two responsibilities:
1. A long-lived **bridge** (run via `manage.py run_mqtt_bridge`) that subscribes
   to the fleet's telemetry/status/result topics and feeds the domain services.
2. A lightweight, lazily-connected **publisher** used by the request/Celery
   processes to send commands down to devices, without each of them holding a
   subscription.

Auto-reconnect and a clean callback API keep the bridge resilient to broker
restarts — important for an always-on control plane.
"""
from __future__ import annotations

import json
import logging
import ssl
import threading

import paho.mqtt.client as mqtt
from django.conf import settings

from . import handlers, topics

logger = logging.getLogger("robogrid.mqtt")


def _configure(client: mqtt.Client) -> None:
    cfg = settings.MQTT
    if cfg.get("USERNAME"):
        client.username_pw_set(cfg["USERNAME"], cfg["PASSWORD"])
    if cfg.get("TLS"):
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.reconnect_delay_set(min_delay=1, max_delay=60)


# ── Bridge (subscriber) ─────────────────────────────────────────────────────
class MQTTBridge:
    """Subscribes to the whole fleet and dispatches inbound messages."""

    def __init__(self) -> None:
        cfg = settings.MQTT
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{cfg['CLIENT_ID_PREFIX']}-bridge",
            clean_session=False,  # durable session: don't miss QoS1 on restart
        )
        _configure(self.client)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            logger.error("MQTT connect failed: %s", reason_code)
            return
        logger.info("MQTT bridge connected; subscribing to fleet topics")
        # QoS 1 — at-least-once; handlers are idempotent on command_id / time.
        client.subscribe([(topics.telemetry_sub(), 1),
                          (topics.status_sub(), 1),
                          (topics.results_sub(), 1)])

    def _on_message(self, client, userdata, msg):
        try:
            handlers.dispatch(msg.topic, msg.payload)
        except Exception:  # noqa: BLE001 - never let one bad message kill the loop
            logger.exception("error handling message on %s", msg.topic)

    def _on_disconnect(self, client, userdata, *args):
        logger.warning("MQTT bridge disconnected; auto-reconnect will retry")

    def run_forever(self) -> None:
        cfg = settings.MQTT
        self.client.connect(cfg["HOST"], cfg["PORT"], cfg["KEEPALIVE"])
        self.client.loop_forever(retry_first_connection=True)


# ── Publisher (shared singleton) ────────────────────────────────────────────
_pub_lock = threading.Lock()
_publisher: mqtt.Client | None = None


def _get_publisher() -> mqtt.Client:
    global _publisher
    with _pub_lock:
        if _publisher is None:
            cfg = settings.MQTT
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"{cfg['CLIENT_ID_PREFIX']}-pub",
            )
            _configure(client)
            client.connect(cfg["HOST"], cfg["PORT"], cfg["KEEPALIVE"])
            client.loop_start()  # background network thread for reconnects
            _publisher = client
        return _publisher


def publish(topic: str, payload: dict, qos: int = 1, retain: bool = False) -> None:
    client = _get_publisher()
    info = client.publish(topic, json.dumps(payload, default=str), qos=qos, retain=retain)
    info.wait_for_publish(timeout=5)


def publish_command(cmd) -> None:
    """Serialise a DeviceCommand and publish it to the device's command topic."""
    publish(
        topics.command_topic(cmd.device.serial),
        {"command_id": str(cmd.id), "command": cmd.command, "payload": cmd.payload},
        qos=1,
    )
