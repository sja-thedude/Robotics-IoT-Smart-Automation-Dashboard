"""Development settings — verbose, permissive, single-host."""
from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Allow any localhost origin for the front-end during development.
CORS_ALLOW_ALL_ORIGINS = True

# Make the browsable API available while developing.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)

# Email to console instead of an SMTP server.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
