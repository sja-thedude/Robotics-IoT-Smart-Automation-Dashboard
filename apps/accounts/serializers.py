from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import DevicePermission, Organization

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "name", "slug", "contact_email", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class UserSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "phone",
            "organization",
            "organization_name",
            "is_active",
            "is_service_account",
            "last_login",
            "date_joined",
        )
        read_only_fields = ("id", "last_login", "date_joined", "organization_name")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ("id", "email", "password", "first_name", "last_name", "role", "organization")

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT login that embeds role/org claims so the gateway and WS layer
    can authorize without a DB round-trip."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["org"] = str(user.organization_id) if user.organization_id else None
        token["email"] = user.email
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class DevicePermissionSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)
    device_name = serializers.CharField(source="device.name", read_only=True)

    class Meta:
        model = DevicePermission
        fields = (
            "id",
            "user",
            "user_email",
            "device",
            "device_name",
            "can_control",
            "expires_at",
            "granted_by",
            "created_at",
        )
        read_only_fields = ("id", "granted_by", "created_at", "user_email", "device_name")
