"""
Publish synthetic telemetry as if a real device were online.

    python manage.py simulate_device --serial ROBO-001 --interval 2

Handy for demos, load tests, and exercising the full pipeline
(MQTT → ingest → alerts → WebSocket) without physical hardware. It also
subscribes to the device's command topic and auto-acks commands, so the
remote-control round-trip can be demonstrated end to end.
"""
import json
import random
import time

import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.mqtt import topics


class Command(BaseCommand):
    help = "Simulate a device publishing telemetry over MQTT."

    def add_arguments(self, parser):
        parser.add_argument("--serial", required=True)
        parser.add_argument("--interval", type=float, default=3.0)
        parser.add_argument("--lat", type=float, default=37.7749)
        parser.add_argument("--lon", type=float, default=-122.4194)

    def handle(self, *args, **opts):
        serial = opts["serial"]
        cfg = settings.MQTT
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=f"sim-{serial}")
        if cfg.get("USERNAME"):
            client.username_pw_set(cfg["USERNAME"], cfg["PASSWORD"])

        def on_command(c, u, msg):
            data = json.loads(msg.payload)
            self.stdout.write(self.style.WARNING(f"← command: {data}"))
            c.publish(
                f"{topics.base()}/devices/{serial}/results",
                json.dumps({"command_id": data.get("command_id"),
                            "status": "completed", "result": {"ok": True}}),
                qos=1,
            )

        client.on_command = on_command
        client.message_callback_add(topics.command_topic(serial), on_command)
        client.connect(cfg["HOST"], cfg["PORT"], cfg["KEEPALIVE"])
        client.subscribe(topics.command_topic(serial), qos=1)
        client.loop_start()

        battery = 100.0
        self.stdout.write(self.style.SUCCESS(f"Simulating {serial} (Ctrl-C to stop)…"))
        try:
            while True:
                battery = max(5.0, battery - random.uniform(0, 0.4))
                payload = {
                    "serial": serial,
                    "battery_level": round(battery, 1),
                    "signal_strength": random.randint(-95, -45),
                    "location": {"lat": opts["lat"] + random.uniform(-0.001, 0.001),
                                 "lon": opts["lon"] + random.uniform(-0.001, 0.001)},
                    "readings": {
                        "temp_c": round(random.uniform(18, 34), 2),
                        "humidity": round(random.uniform(30, 80), 1),
                        "motion": random.choice([0, 0, 0, 1]),
                        "vibration": round(random.uniform(0, 5), 2),
                    },
                }
                client.publish(topics.telemetry_sub().replace("+", serial),
                               json.dumps(payload), qos=1)
                self.stdout.write(f"→ telemetry batt={payload['battery_level']}%")
                time.sleep(opts["interval"])
        except KeyboardInterrupt:
            client.loop_stop()
            self.stdout.write(self.style.WARNING("\nSimulator stopped."))
