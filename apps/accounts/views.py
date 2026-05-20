from django.contrib.auth import get_user_model
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import CreateAPIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.permissions import IsAdmin
from apps.core.services import record_audit

from .models import DevicePermission, Organization, Role
from .serializers import (
    CustomTokenObtainPairSerializer,
    DevicePermissionSerializer,
    OrganizationSerializer,
    RegisterSerializer,
    UserSerializer,
)

User = get_user_model()


class LoginView(TokenObtainPairView):
    """POST email/password → access + refresh tokens (+ user profile)."""

    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            user = User.objects.filter(email=request.data.get("email")).first()
            record_audit(action="login", target_type="user",
                         target_id=getattr(user, "id", ""), summary="User login",
                         actor=user)
        return response


class RegisterView(CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ("role", "organization", "is_active")
    search_fields = ("email", "first_name", "last_name")
    ordering_fields = ("email", "date_joined", "last_login")

    def get_queryset(self):
        qs = User.objects.select_related("organization")
        user = self.request.user
        # Org admins are confined to their own tenant; super admins see all.
        if user.role == Role.ORG_ADMIN and user.organization_id:
            qs = qs.filter(organization_id=user.organization_id)
        return qs

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        """Return the authenticated caller's own profile."""
        return Response(UserSerializer(request.user).data)


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAdmin]
    queryset = Organization.objects.all()
    search_fields = ("name", "slug")

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.SUPER_ADMIN or user.is_superuser:
            return Organization.objects.all()
        return Organization.objects.filter(id=user.organization_id)


class DevicePermissionViewSet(viewsets.ModelViewSet):
    serializer_class = DevicePermissionSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ("user", "device", "can_control")

    def get_queryset(self):
        qs = DevicePermission.objects.select_related("user", "device")
        user = self.request.user
        if user.role == Role.ORG_ADMIN and user.organization_id:
            qs = qs.filter(device__organization_id=user.organization_id)
        return qs

    def perform_create(self, serializer):
        grant = serializer.save(granted_by=self.request.user)
        record_audit(
            action="update", target_type="device_permission", target_id=grant.id,
            summary=f"Granted {'control' if grant.can_control else 'view'} on "
                    f"{grant.device} to {grant.user}",
        )
