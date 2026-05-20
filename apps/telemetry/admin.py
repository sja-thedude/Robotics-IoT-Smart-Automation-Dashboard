from django.contrib import admin

from .models import CameraFeed, Reading, Sensor


@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    list_display = ("name", "device", "sensor_type", "unit", "last_value",
                    "last_reading_at", "is_active")
    list_filter = ("sensor_type", "is_active")
    search_fields = ("name", "key", "device__name", "device__serial")
    autocomplete_fields = ("device",)


@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
    list_display = ("sensor", "device", "time", "value", "value_text", "quality")
    list_filter = ("sensor__sensor_type",)
    date_hierarchy = "time"
    # The readings table is huge; disable the slow full count in the changelist.
    show_full_result_count = False


@admin.register(CameraFeed)
class CameraFeedAdmin(admin.ModelAdmin):
    list_display = ("name", "device", "protocol", "is_active", "last_snapshot_at")
    list_filter = ("protocol", "is_active")
    search_fields = ("name", "device__name")
    autocomplete_fields = ("device",)
