from django.apps import AppConfig


class DevicesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.devices"
    verbose_name = "Devices & Robots"

    def ready(self) -> None:
        from . import signals  # noqa: F401  (register signal handlers)
