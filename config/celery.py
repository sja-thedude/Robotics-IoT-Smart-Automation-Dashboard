"""
Celery application bootstrap.

Beat schedules live here so the periodic jobs that keep device health,
offline detection, and alert evaluation running are version-controlled
alongside the code.
"""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("robogrid")

# Pull every CELERY_* setting from Django config.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in every installed app.
app.autodiscover_tasks()

# ── Periodic schedule ──────────────────────────────────────────────────
app.conf.beat_schedule = {
    "detect-offline-devices": {
        "task": "apps.devices.tasks.detect_offline_devices",
        "schedule": 60.0,  # every minute
    },
    "rollup-device-health": {
        "task": "apps.devices.tasks.rollup_device_health",
        "schedule": 300.0,  # every 5 minutes
    },
    "expire-stale-commands": {
        "task": "apps.devices.tasks.expire_stale_commands",
        "schedule": 60.0,  # every minute
    },
    "evaluate-threshold-alerts": {
        "task": "apps.alerts.tasks.evaluate_threshold_alerts",
        "schedule": 30.0,  # every 30 seconds
    },
    "purge-old-telemetry": {
        "task": "apps.telemetry.tasks.purge_old_telemetry",
        "schedule": crontab(hour=3, minute=0),  # nightly at 03:00 UTC
    },
}


@app.task(bind=True)
def debug_task(self) -> str:  # pragma: no cover - smoke test helper
    return f"request: {self.request!r}"
