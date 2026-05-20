"""Operational endpoints that aren't tied to a domain model."""
from django.db import connection
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(exclude=True)  # operational probe, not part of the public API
@api_view(["GET"])
@permission_classes([AllowAny])
def healthcheck(request):
    """
    Liveness + dependency probe used by Docker/K8s and load balancers.

    Returns 200 only when Postgres and Redis are both reachable so an
    unhealthy container is pulled from rotation instead of serving errors.
    """
    checks = {"database": False, "cache": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database"] = cursor.fetchone()[0] == 1
    except Exception:  # noqa: BLE001 - probe must never raise
        checks["database"] = False

    try:
        cache.set("healthz", "ok", 5)
        checks["cache"] = cache.get("healthz") == "ok"
    except Exception:  # noqa: BLE001
        checks["cache"] = False

    healthy = all(checks.values())
    return Response(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status=200 if healthy else 503,
    )
