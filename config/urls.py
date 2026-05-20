"""
Root URL configuration.

The public API is versioned under /api/v1/. Each domain app contributes its
own router-based urls module, keeping route ownership inside the app.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.views import healthcheck

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("devices/", include("apps.devices.urls")),
    path("telemetry/", include("apps.telemetry.urls")),
    path("alerts/", include("apps.alerts.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthcheck, name="healthcheck"),
    # ── API v1 ──────────────────────────────────────────────────────────
    path("api/v1/", include((api_v1, "v1"))),
    # ── OpenAPI schema & docs ───────────────────────────────────────────
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
