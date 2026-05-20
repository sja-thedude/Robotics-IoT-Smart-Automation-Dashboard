from unittest import mock

from django.test import TestCase

from apps.accounts.models import Organization
from apps.alerts.models import Alert, AlertRule, Severity
from apps.devices.models import Device, DeviceStatus, DeviceType
from apps.telemetry.models import Reading, Sensor, SensorType
from apps.telemetry.services import ingest_payload


class IngestPipelineTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme", slug="acme")
        self.device = Device.objects.create(
            organization=self.org, name="Hub", serial="HUB-1",
            device_type=DeviceType.SENSOR_HUB, status=DeviceStatus.PROVISIONING)
        self.temp = Sensor.objects.create(
            device=self.device, name="Temp", key="temp_c",
            sensor_type=SensorType.TEMPERATURE, unit="°C")

    def test_ingest_stores_readings_and_marks_online(self):
        result = ingest_payload({
            "serial": "HUB-1", "battery_level": 80.0,
            "location": {"lat": 1.0, "lon": 2.0},
            "readings": {"temp_c": 22.5, "humidity": 50},
        })
        self.assertEqual(result["stored"], 2)
        self.device.refresh_from_db()
        self.assertEqual(self.device.status, DeviceStatus.ONLINE)
        self.assertEqual(self.device.battery_level, 80.0)
        self.assertEqual(self.device.latitude, 1.0)
        self.temp.refresh_from_db()
        self.assertEqual(self.temp.last_value, 22.5)

    def test_ingest_autocreates_unknown_sensor(self):
        ingest_payload({"serial": "HUB-1", "readings": {"co2": 410}})
        self.assertTrue(Sensor.objects.filter(device=self.device, key="co2").exists())

    def test_threshold_breach_raises_alert(self):
        AlertRule.objects.create(
            organization=self.org, name="hot", source=AlertRule.Source.SENSOR,
            sensor=self.temp, operator=AlertRule.Operator.GT, threshold=45.0,
            severity=Severity.CRITICAL)
        ingest_payload({"serial": "HUB-1", "readings": {"temp_c": 60.0}})
        alert = Alert.objects.get(device=self.device)
        self.assertEqual(alert.severity, Severity.CRITICAL)
        self.assertEqual(alert.status, Alert.Status.OPEN)
        self.assertEqual(alert.value, 60.0)

    def test_unknown_serial_raises(self):
        with self.assertRaises(Device.DoesNotExist):
            ingest_payload({"serial": "NOPE", "readings": {"temp_c": 1}})
