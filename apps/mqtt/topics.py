"""
Canonical MQTT topic scheme.

    {base}/devices/{serial}/telemetry   device → backend   sensor batches
    {base}/devices/{serial}/status      device → backend   online/offline/health
    {base}/devices/{serial}/commands    backend → device   control instructions
    {base}/devices/{serial}/results     device → backend   command acks/results

Wildcards are used for the backend's shared subscription so a single bridge
process serves the whole fleet. Devices authenticate to the broker with their
serial-scoped credentials and are ACL'd to only their own subtree.
"""
from django.conf import settings


def base() -> str:
    return settings.MQTT["BASE_TOPIC"]


def telemetry_sub() -> str:
    return f"{base()}/devices/+/telemetry"


def status_sub() -> str:
    return f"{base()}/devices/+/status"


def results_sub() -> str:
    return f"{base()}/devices/+/results"


def command_topic(serial: str) -> str:
    return f"{base()}/devices/{serial}/commands"


def serial_from_topic(topic: str) -> str | None:
    """Extract the device serial from a `.../devices/<serial>/<leaf>` topic."""
    parts = topic.split("/")
    try:
        i = parts.index("devices")
        return parts[i + 1]
    except (ValueError, IndexError):
        return None
