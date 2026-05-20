from django.urls import re_path

from . import consumers

# WebSocket URL map, mounted under ws:// in config.asgi.
websocket_urlpatterns = [
    # Org-wide live feed: device state, telemetry, alerts for the dashboard.
    re_path(r"^ws/dashboard/$", consumers.DashboardConsumer.as_asgi()),
    # Focused stream for a single device's detail page.
    re_path(r"^ws/devices/(?P<device_id>[0-9a-f-]+)/$", consumers.DeviceConsumer.as_asgi()),
    # Dedicated alert + per-user notification channel.
    re_path(r"^ws/alerts/$", consumers.AlertConsumer.as_asgi()),
]
