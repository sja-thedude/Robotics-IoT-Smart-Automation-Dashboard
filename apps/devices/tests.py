from unittest import mock

from django.test import TestCase

from apps.accounts.models import Organization
from apps.core.models import AuditLog
from apps.devices.models import Device, DeviceCommand, DeviceStatus, DeviceType
from apps.devices.services import dispatch_command, transition_command


class CommandDispatchTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme", slug="acme")
        self.device = Device.objects.create(
            organization=self.org, name="Arm", serial="S-1",
            device_type=DeviceType.ROBOT,
            capabilities={"commands": ["move", "stop"]})

    @mock.patch("apps.mqtt.client.publish_command")
    def test_dispatch_creates_command_and_audit(self, pub):
        cmd = dispatch_command(device=self.device, command="move",
                               payload={"x": 1})
        pub.assert_called_once()
        self.assertEqual(cmd.command, "move")
        self.assertEqual(cmd.status, DeviceCommand.Status.SENT)
        self.assertTrue(
            AuditLog.objects.filter(action="command",
                                    target_id=str(self.device.id)).exists())

    @mock.patch("apps.mqtt.client.publish_command", side_effect=RuntimeError("broker down"))
    def test_dispatch_degrades_when_broker_unreachable(self, pub):
        cmd = dispatch_command(device=self.device, command="move")
        # Command is still recorded (queued) with the error captured.
        self.assertEqual(cmd.status, DeviceCommand.Status.QUEUED)
        self.assertIn("publish failed", cmd.error)

    @mock.patch("apps.mqtt.client.publish_command")
    def test_transition_lifecycle(self, pub):
        cmd = dispatch_command(device=self.device, command="move")
        transition_command(cmd, DeviceCommand.Status.COMPLETED, result={"ok": True})
        cmd.refresh_from_db()
        self.assertEqual(cmd.status, DeviceCommand.Status.COMPLETED)
        self.assertIsNotNone(cmd.completed_at)
        self.assertEqual(cmd.result, {"ok": True})


class OfflineDetectionTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme", slug="acme")

    def test_marks_stale_device_offline(self):
        from django.utils import timezone
        from datetime import timedelta

        from apps.devices.tasks import detect_offline_devices

        device = Device.objects.create(
            organization=self.org, name="Arm", serial="S-1",
            device_type=DeviceType.ROBOT, status=DeviceStatus.ONLINE,
            last_seen=timezone.now() - timedelta(minutes=10))
        n = detect_offline_devices()
        device.refresh_from_db()
        self.assertEqual(device.status, DeviceStatus.OFFLINE)
        self.assertGreaterEqual(n, 1)
