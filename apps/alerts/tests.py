from django.test import TestCase

from apps.accounts.models import Organization
from apps.alerts.models import Alert, AlertRule, Severity
from apps.alerts.services import acknowledge_alert, raise_alert, resolve_alert
from apps.devices.models import Device, DeviceType
from django.contrib.auth import get_user_model

User = get_user_model()


class RuleMatchingTests(TestCase):
    def _rule(self, op, threshold):
        return AlertRule(operator=op, threshold=threshold)

    def test_operators(self):
        self.assertTrue(self._rule(AlertRule.Operator.GT, 10).matches(11))
        self.assertFalse(self._rule(AlertRule.Operator.GT, 10).matches(10))
        self.assertTrue(self._rule(AlertRule.Operator.LTE, 10).matches(10))
        self.assertTrue(self._rule(AlertRule.Operator.NEQ, 10).matches(9))
        self.assertFalse(self._rule(AlertRule.Operator.EQ, 10).matches(9))

    def test_none_value_never_matches(self):
        self.assertFalse(self._rule(AlertRule.Operator.GT, 10).matches(None))


class AlertLifecycleTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme", slug="acme")
        self.device = Device.objects.create(
            organization=self.org, name="Arm", serial="S-1", device_type=DeviceType.ROBOT)
        self.rule = AlertRule.objects.create(
            organization=self.org, name="r", source=AlertRule.Source.SENSOR,
            device=self.device, operator=AlertRule.Operator.GT, threshold=5,
            cooldown_seconds=300)
        self.user = User.objects.create_user(email="a@a.test", password="x",
                                             organization=self.org)

    def test_raise_is_idempotent_per_rule_device(self):
        a1 = raise_alert(rule=self.rule, device=self.device, value=9, title="t")
        a2 = raise_alert(rule=self.rule, device=self.device, value=10, title="t")
        self.assertEqual(a1.id, a2.id)  # de-duped to one OPEN alert
        self.assertEqual(Alert.objects.filter(status=Alert.Status.OPEN).count(), 1)

    def test_acknowledge_then_resolve(self):
        alert = raise_alert(rule=self.rule, device=self.device, value=9, title="t")
        acknowledge_alert(alert, self.user)
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.Status.ACKNOWLEDGED)
        self.assertEqual(alert.acknowledged_by, self.user)

        resolve_alert(alert, self.user)
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.Status.RESOLVED)
        self.assertIsNotNone(alert.resolved_at)
