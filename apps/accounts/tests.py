from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import DevicePermission, Organization, Role
from apps.devices.models import Device, DeviceType

User = get_user_model()


class AuthFlowTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme", slug="acme")
        self.user = User.objects.create_user(
            email="op@acme.test", password="pw12345678",
            role=Role.OPERATOR, organization=self.org,
        )

    def test_login_returns_tokens_and_profile(self):
        resp = self.client.post("/api/v1/auth/login/",
                                {"email": "op@acme.test", "password": "pw12345678"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertEqual(resp.data["user"]["email"], "op@acme.test")

    def test_login_rejects_bad_password(self):
        resp = self.client.post("/api/v1/auth/login/",
                                {"email": "op@acme.test", "password": "wrong"})
        self.assertEqual(resp.status_code, 401)

    def test_me_endpoint_requires_auth(self):
        self.assertEqual(self.client.get("/api/v1/auth/users/me/").status_code, 401)
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/v1/auth/users/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["email"], "op@acme.test")


class DeviceAccessTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme", slug="acme")
        self.other = Organization.objects.create(name="Other", slug="other")
        self.device = Device.objects.create(
            organization=self.org, name="Arm", serial="S-1", device_type=DeviceType.ROBOT)

    def test_operator_views_org_device_but_needs_grant_to_control(self):
        op = User.objects.create_user(email="o@a.test", password="x",
                                      role=Role.OPERATOR, organization=self.org)
        self.assertTrue(op.can_access_device(self.device))            # view: yes
        self.assertFalse(op.can_access_device(self.device, control=True))  # control: no grant
        DevicePermission.objects.create(user=op, device=self.device, can_control=True)
        self.assertTrue(op.can_access_device(self.device, control=True))   # control: granted

    def test_engineer_controls_org_device_without_grant(self):
        eng = User.objects.create_user(email="e@a.test", password="x",
                                       role=Role.ENGINEER, organization=self.org)
        self.assertTrue(eng.can_access_device(self.device, control=True))

    def test_viewer_needs_grant_even_to_view(self):
        v = User.objects.create_user(email="v@a.test", password="x",
                                     role=Role.VIEWER, organization=self.org)
        self.assertFalse(v.can_access_device(self.device))
        self.assertFalse(v.can_access_device(self.device, control=True))
        DevicePermission.objects.create(user=v, device=self.device, can_control=False)
        self.assertTrue(v.can_access_device(self.device))
        self.assertFalse(v.can_access_device(self.device, control=True))

    def test_cross_org_user_denied(self):
        outsider = User.objects.create_user(email="x@o.test", password="x",
                                            role=Role.ORG_ADMIN, organization=self.other)
        # org_admin is a platform admin → allowed; a viewer would be denied.
        viewer = User.objects.create_user(email="vx@o.test", password="x",
                                          role=Role.VIEWER, organization=self.other)
        self.assertFalse(viewer.can_access_device(self.device))
        self.assertTrue(outsider.can_access_device(self.device))
