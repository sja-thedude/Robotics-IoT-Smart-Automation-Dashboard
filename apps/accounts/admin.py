from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import DevicePermission, Organization, User


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "role", "organization", "is_active", "is_service_account")
    list_filter = ("role", "is_active", "is_service_account", "organization")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "phone", "avatar")}),
        ("Access", {"fields": ("role", "organization", "is_service_account")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",),
                "fields": ("email", "password1", "password2", "role", "organization")}),
    )


@admin.register(DevicePermission)
class DevicePermissionAdmin(admin.ModelAdmin):
    list_display = ("user", "device", "can_control", "expires_at", "created_at")
    list_filter = ("can_control",)
    search_fields = ("user__email", "device__name")
    autocomplete_fields = ("user", "device", "granted_by")
