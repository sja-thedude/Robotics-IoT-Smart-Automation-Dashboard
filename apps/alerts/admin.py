from django.contrib import admin

from .models import Alert, AlertRule, Notification, NotificationChannel


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "source", "severity", "operator",
                    "threshold", "is_active")
    list_filter = ("source", "severity", "is_active")
    search_fields = ("name",)
    filter_horizontal = ("notify_channels",)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("title", "severity", "status", "device", "value", "created_at")
    list_filter = ("severity", "status")
    search_fields = ("title", "message", "device__name")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "updated_at")


@admin.register(NotificationChannel)
class NotificationChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "organization", "min_severity", "is_active")
    list_filter = ("kind", "is_active")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "severity", "is_read", "created_at")
    list_filter = ("severity", "is_read")
    search_fields = ("title", "recipient__email")
