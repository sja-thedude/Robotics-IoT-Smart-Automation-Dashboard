"""
Identity, tenancy, and access control.

Design notes
------------
* **Organization** is the tenant boundary. Every device, sensor, alert and
  user belongs to exactly one org, so all queries can be scoped cheaply.
* **User** is email-first (no username) with a coarse `role` for UI/menu
  gating, plus fine-grained, per-device grants via **DevicePermission** for
  the "who can drive *this* robot" question.
* Roles are deliberately an enum, not free-form Django groups, because the
  product has a fixed operational vocabulary (operator, engineer, viewer…).
  Django's group/permission system still works underneath for admin actions.
"""
from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel, TimeStampedModel, UUIDModel


class Organization(BaseModel):
    """A tenant — a company, lab, hospital, or smart-city operator."""

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=160, unique=True)
    contact_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Role(models.TextChoices):
    SUPER_ADMIN = "super_admin", "Super Admin"     # cross-org platform owner
    ORG_ADMIN = "org_admin", "Org Admin"           # full control within an org
    ENGINEER = "engineer", "Engineer"              # configure devices & rules
    OPERATOR = "operator", "Operator"              # control devices, ack alerts
    VIEWER = "viewer", "Viewer"                    # read-only dashboards
    DEVICE = "device", "Device/Service Account"    # machine identity (MQTT/API)


class UserManager(BaseUserManager):
    """Email-based manager (the default expects a username)."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("role", Role.VIEWER)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(
            is_staff=True,
            is_superuser=True,
            role=Role.SUPER_ADMIN,
            is_active=True,
        )
        return self._create_user(email, password, **extra)


class User(AbstractUser, UUIDModel):
    """Custom user keyed by email, scoped to an organization."""

    username = None  # removed in favour of email
    email = models.EmailField(unique=True, db_index=True)
    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
    phone = models.CharField(max_length=32, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    # Service accounts (role=DEVICE) authenticate machines, not people.
    is_service_account = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        ordering = ("email",)
        indexes = [models.Index(fields=["organization", "role"])]

    def __str__(self) -> str:
        return self.email

    # ── Role helpers ────────────────────────────────────────────────────
    @property
    def is_platform_admin(self) -> bool:
        return self.is_superuser or self.role in {Role.SUPER_ADMIN, Role.ORG_ADMIN}

    @property
    def can_configure(self) -> bool:
        return self.is_platform_admin or self.role == Role.ENGINEER

    @property
    def can_control(self) -> bool:
        return self.can_configure or self.role == Role.OPERATOR

    def can_access_device(self, device, *, control: bool = False) -> bool:
        """
        True if the user may view (or control) a specific device.

        Access matrix (within the user's own organization):
          * platform admin (super/org admin) → view + control everything
          * engineer  → view + control any org device (they configure devices)
          * operator  → view any org device; control needs a per-device grant
          * viewer    → view only the devices explicitly granted to them
        Cross-organization access is always denied for non-admins.
        """
        if self.is_platform_admin:
            return True
        if device.organization_id != self.organization_id:
            return False

        if control:
            if self.role == Role.ENGINEER:
                return True
            grant = self.device_permissions.filter(device=device).first()
            return bool(grant and grant.can_control)

        # View access.
        if self.role in {Role.ENGINEER, Role.OPERATOR}:
            return True
        return self.device_permissions.filter(device=device).exists()


class DevicePermission(TimeStampedModel, UUIDModel):
    """Explicit per-user, per-device access grant (fine-grained ACL)."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="device_permissions"
    )
    device = models.ForeignKey(
        "devices.Device", on_delete=models.CASCADE, related_name="permissions"
    )
    can_control = models.BooleanField(
        default=False, help_text="May issue commands, not just view telemetry."
    )
    granted_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="grants_made"
    )
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "device"], name="uq_user_device_permission"
            )
        ]
        indexes = [models.Index(fields=["device", "user"])]

    def __str__(self) -> str:
        scope = "control" if self.can_control else "view"
        return f"{self.user} → {self.device} ({scope})"

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at < timezone.now())
