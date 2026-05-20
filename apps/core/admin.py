from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "target_type", "target_id", "summary")
    list_filter = ("action", "created_at")
    search_fields = ("target_id", "summary", "actor__email")
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    date_hierarchy = "created_at"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
