"""
Run the long-lived MQTT ↔ Django bridge.

    python manage.py run_mqtt_bridge

Deployed as its own container/process (see docker-compose `mqtt_bridge`). It
holds a durable subscription to the fleet and turns inbound device messages
into telemetry, status updates, and command results.
"""
from django.core.management.base import BaseCommand

from apps.mqtt.client import MQTTBridge


class Command(BaseCommand):
    help = "Run the MQTT bridge that ingests device telemetry/status/results."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting RoboGrid MQTT bridge…"))
        bridge = MQTTBridge()
        try:
            bridge.run_forever()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("MQTT bridge stopped."))
