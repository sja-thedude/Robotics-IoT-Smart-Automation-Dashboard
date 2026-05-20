from django.contrib import admin

from .models import Device, DeviceCommand, DeviceGroup, DeviceHealthSnapshot


@admin.register(DeviceGroup)
class DeviceGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "parent", "full_path")
    list_filter = ("organization",)
    search_fields = ("name",)
    autocomplete_fields = ("parent",)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "serial", "device_type", "status", "battery_level",
                    "health_score", "last_seen", "organization")
    list_filter = ("device_type", "status", "organization", "manufacturer")
    search_fields = ("name", "serial", "model_number")
    autocomplete_fields = ("group", "service_account")
    readonly_fields = ("last_seen", "health_score", "created_at", "updated_at")


@admin.register(DeviceCommand)
class DeviceCommandAdmin(admin.ModelAdmin):
    list_display = ("command", "device", "status", "issued_by", "created_at", "completed_at")
    list_filter = ("status", "command")
    search_fields = ("device__name", "device__serial", "command")
    readonly_fields = [f.name for f in DeviceCommand._meta.fields]


@admin.register(DeviceHealthSnapshot)
class DeviceHealthSnapshotAdmin(admin.ModelAdmin):
    list_display = ("device", "health_score", "battery_level", "created_at")
    list_filter = ("device__organization",)
    date_hierarchy = "created_at"
