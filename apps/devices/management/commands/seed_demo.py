"""
Seed a realistic demo tenant so the dashboard has something to show.

    python manage.py seed_demo

Creates an organization, an admin + operator user, a device hierarchy, a
fleet of mixed devices with sensors, a few alert rules, and an in-app
notification channel. Idempotent: safe to re-run.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.accounts.models import Organization, Role
from apps.alerts.models import AlertRule, NotificationChannel, Severity
from apps.devices.models import Device, DeviceGroup, DeviceStatus, DeviceType
from apps.telemetry.models import Sensor, SensorType

User = get_user_model()


class Command(BaseCommand):
    help = "Seed a demo organization with devices, sensors, and alert rules."

    def handle(self, *args, **options):
        org, _ = Organization.objects.get_or_create(
            slug="demo", defaults={"name": "Demo Robotics Lab",
                                   "contact_email": "ops@demo.robogrid.ai"})

        admin, created = User.objects.get_or_create(
            email="admin@robogrid.ai",
            defaults={"role": Role.ORG_ADMIN, "organization": org,
                      "is_staff": True, "first_name": "Ada", "last_name": "Admin"})
        if created:
            admin.set_password("robogrid123")
            admin.save()

        operator, created = User.objects.get_or_create(
            email="operator@robogrid.ai",
            defaults={"role": Role.OPERATOR, "organization": org,
                      "first_name": "Otto", "last_name": "Operator"})
        if created:
            operator.set_password("robogrid123")
            operator.save()

        site = DeviceGroup.objects.get_or_create(
            organization=org, name="HQ Campus", parent=None)[0]
        floor = DeviceGroup.objects.get_or_create(
            organization=org, name="Production Floor", parent=site)[0]

        fleet = [
            ("ROBO-001", "Assembly Arm A", DeviceType.ROBOT,
             {"commands": ["move", "home", "stop", "calibrate"], "has_camera": True}),
            ("ROBO-002", "Mobile AMR 1", DeviceType.VEHICLE,
             {"commands": ["navigate", "dock", "stop"]}),
            ("DRONE-001", "Inspection Drone", DeviceType.DRONE,
             {"commands": ["takeoff", "land", "return_home"]}),
            ("HUB-001", "Cold Storage Sensor Hub", DeviceType.SENSOR_HUB, {}),
            ("CAM-001", "Perimeter Camera", DeviceType.CAMERA, {"has_camera": True}),
        ]

        sensor_specs = {
            "temp_c": (SensorType.TEMPERATURE, "°C", -10, 60),
            "humidity": (SensorType.HUMIDITY, "%", 0, 100),
            "motion": (SensorType.MOTION, "", None, None),
            "vibration": (SensorType.VIBRATION, "mm/s", 0, 10),
        }

        for serial, name, dtype, caps in fleet:
            device, _ = Device.objects.get_or_create(
                serial=serial,
                defaults={"name": name, "organization": org, "group": floor,
                          "device_type": dtype, "status": DeviceStatus.PROVISIONING,
                          "capabilities": caps, "manufacturer": "RoboGrid Demo"})
            for key, (stype, unit, lo, hi) in sensor_specs.items():
                Sensor.objects.get_or_create(
                    device=device, key=key,
                    defaults={"name": key.replace("_", " ").title(),
                              "sensor_type": stype, "unit": unit,
                              "min_threshold": lo, "max_threshold": hi})

        channel, _ = NotificationChannel.objects.get_or_create(
            organization=org, name="In-app default",
            defaults={"kind": NotificationChannel.Kind.IN_APP,
                      "min_severity": Severity.WARNING})

        rules = [
            ("High temperature", AlertRule.Source.SENSOR, "temperature",
             AlertRule.Operator.GT, 45.0, Severity.CRITICAL),
            ("High vibration", AlertRule.Source.SENSOR, "vibration",
             AlertRule.Operator.GT, 7.0, Severity.WARNING),
            ("Low battery", AlertRule.Source.BATTERY, "",
             AlertRule.Operator.LT, 20.0, Severity.WARNING),
            ("Device offline", AlertRule.Source.OFFLINE, "",
             AlertRule.Operator.EQ, None, Severity.CRITICAL),
        ]
        for name, source, stype, op, threshold, sev in rules:
            rule, _ = AlertRule.objects.get_or_create(
                organization=org, name=name,
                defaults={"source": source, "sensor_type": stype, "operator": op,
                          "threshold": threshold, "severity": sev})
            rule.notify_channels.add(channel)

        self.stdout.write(self.style.SUCCESS(
            "✅ Seeded demo org.\n"
            "   Login:    admin@robogrid.ai / robogrid123 (org admin)\n"
            "             operator@robogrid.ai / robogrid123 (operator)\n"
            f"   Devices:  {Device.objects.filter(organization=org).count()}  "
            f"Sensors: {Sensor.objects.filter(device__organization=org).count()}  "
            f"Rules: {AlertRule.objects.filter(organization=org).count()}\n"
            "   Try:      python manage.py simulate_device --serial ROBO-001"
        ))
