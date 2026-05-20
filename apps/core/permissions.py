"""Reusable DRF permission classes shared across domain apps."""
from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdmin(BasePermission):
    """Platform administrators only."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_platform_admin)


class IsAdminOrReadOnly(BasePermission):
    """Anyone authenticated may read; only admins may write."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.is_platform_admin


class HasDeviceAccess(BasePermission):
    """
    Object-level gate for device-scoped resources.

    Admins bypass; otherwise the user must have an explicit grant on the
    device (see accounts.DevicePermission). Write methods additionally
    require a control-capable grant.
    """

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_platform_admin:
            return True

        device = getattr(obj, "device", obj)
        require_control = request.method not in SAFE_METHODS
        return user.can_access_device(device, control=require_control)
