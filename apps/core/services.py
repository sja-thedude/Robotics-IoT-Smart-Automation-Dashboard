"""Thin service helpers used across apps."""
from __future__ import annotations

from typing import Any

from .middleware import get_current_actor, get_current_ip
from .models import AuditLog


def record_audit(
    *,
    action: str,
    target_type: str = "",
    target_id: str = "",
    summary: str = "",
    metadata: dict[str, Any] | None = None,
    actor=None,
    ip: str | None = None,
) -> AuditLog:
    """Persist an audit entry, defaulting actor/ip from request context."""
    return AuditLog.objects.create(
        actor=actor or get_current_actor(),
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        summary=summary[:255],
        metadata=metadata or {},
        ip_address=ip or get_current_ip(),
    )
