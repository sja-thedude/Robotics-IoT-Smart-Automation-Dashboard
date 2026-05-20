"""
Telemetry ingestion — the single write path for all sensor data.

Both the HTTP ingest endpoint and the MQTT bridge call `ingest_payload`, so
parsing, denormalisation, liveness updates, alert evaluation and the live WS
broadcast happen identically regardless of transport.
"""
from __future__ import annotations

import logging
from datetime import datetime

from django.utils import timezone

from apps.core.realtime import broadcast, group_for_device
from apps.devices.models import Device

from .models import Reading, Sensor

logger = logging.getLogger("robogrid.telemetry")


def ingest_payload(payload: dict) -> dict:
    """
    Persist a device telemetry batch.

    `payload` matches IngestReadingSerializer:
        {serial, time?, readings: {key: value}, location?, battery_level?, ...}

    Returns a small summary; raises Device.DoesNotExist for unknown serials.
    """
    serial = payload["serial"]
    device = Device.objects.get(serial=serial)

    ts = payload.get("time") or timezone.now()
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)

    # ── Liveness + denormalised device telemetry ─────────────────────────
    update_fields = ["last_seen", "status", "updated_at"]
    device.last_seen = ts
    from apps.devices.models import DeviceStatus

    if device.status in {DeviceStatus.OFFLINE, DeviceStatus.PROVISIONING}:
        device.status = DeviceStatus.ONLINE
    if "battery_level" in payload:
        device.battery_level = payload["battery_level"]
        update_fields.append("battery_level")
    if "signal_strength" in payload:
        device.signal_strength = payload["signal_strength"]
        update_fields.append("signal_strength")
    loc = payload.get("location") or {}
    if "lat" in loc and "lon" in loc:
        device.latitude, device.longitude = loc["lat"], loc["lon"]
        device.altitude = loc.get("alt")
        update_fields += ["latitude", "longitude", "altitude"]
    device.save(update_fields=list(set(update_fields)))

    # ── Resolve sensor keys → rows (auto-create unknown channels) ────────
    readings_in = payload.get("readings", {})
    sensors = {s.key: s for s in device.sensors.all()}

    rows: list[Reading] = []
    live: dict[str, object] = {}
    triggered_sensor_ids: list = []

    for key, raw in readings_in.items():
        sensor = sensors.get(key)
        if sensor is None:
            sensor = Sensor.objects.create(
                device=device, name=key, key=key,
                sensor_type=_guess_type(key),
            )
            sensors[key] = sensor

        numeric, text, js = _coerce(raw)
        rows.append(Reading(sensor=sensor, device=device, time=ts,
                            value=numeric, value_text=text or "", value_json=js))

        sensor.last_value = numeric
        sensor.last_value_text = text or ""
        sensor.last_reading_at = ts
        sensor.save(update_fields=["last_value", "last_value_text", "last_reading_at"])
        live[key] = numeric if numeric is not None else (text or js)
        triggered_sensor_ids.append(sensor.id)

    if rows:
        Reading.objects.bulk_create(rows, batch_size=500)

    # ── Live dashboard push ──────────────────────────────────────────────
    broadcast(
        group_for_device(device.id),
        "telemetry",
        {"device_id": str(device.id), "serial": serial,
         "time": ts.isoformat(), "readings": live},
    )

    # ── Evaluate alert rules synchronously for low-latency alerting ───────
    try:
        from apps.alerts.services import evaluate_device_readings

        evaluate_device_readings(device, triggered_sensor_ids)
    except Exception as exc:  # noqa: BLE001
        logger.warning("alert evaluation failed for %s: %s", serial, exc)

    return {"device": serial, "stored": len(rows)}


def _coerce(raw):
    """Split a raw value into (numeric, text, json) buckets."""
    if isinstance(raw, bool):
        return (1.0 if raw else 0.0), None, None
    if isinstance(raw, (int, float)):
        return float(raw), None, None
    if isinstance(raw, (dict, list)):
        return None, None, raw
    try:
        return float(raw), None, None
    except (TypeError, ValueError):
        return None, str(raw), None


def _guess_type(key: str):
    from .models import SensorType

    k = key.lower()
    mapping = {
        "temp": SensorType.TEMPERATURE, "humid": SensorType.HUMIDITY,
        "motion": SensorType.MOTION, "gps": SensorType.GPS,
        "batt": SensorType.BATTERY, "press": SensorType.PRESSURE,
        "light": SensorType.LIGHT, "lux": SensorType.LIGHT,
        "gas": SensorType.GAS, "co2": SensorType.GAS,
        "heart": SensorType.HEART_RATE, "hr": SensorType.HEART_RATE,
        "vib": SensorType.VIBRATION,
    }
    for needle, stype in mapping.items():
        if needle in k:
            return stype
    return SensorType.CUSTOM
