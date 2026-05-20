"""
ASGI entrypoint — serves both HTTP and WebSocket traffic.

HTTP is handled by Django's standard application; WebSocket connections are
routed through the Channels stack with JWT auth applied at the transport
layer (see apps.realtime.middleware.JWTAuthMiddleware).
"""
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

# Initialise Django before importing anything that touches the app registry.
django_asgi_app = get_asgi_application()

from apps.realtime.middleware import JWTAuthMiddleware  # noqa: E402
from apps.realtime.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddleware(URLRouter(websocket_urlpatterns))
        ),
    }
)
