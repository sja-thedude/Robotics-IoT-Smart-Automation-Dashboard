"""
Test settings — fast, hermetic, no external services.

Uses in-memory SQLite, the in-memory channel layer, and a local-memory cache so
the suite runs in CI without Postgres/Redis/MQTT. Production parity is covered
by running the same migrations against Postgres in the deploy pipeline.
"""
from .base import *  # noqa: F401,F403

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Run Celery tasks inline (no broker) so task logic is exercised in tests.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Speed: cheap password hashing during tests only.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
