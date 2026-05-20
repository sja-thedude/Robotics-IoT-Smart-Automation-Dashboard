"""Retention / maintenance jobs for the time-series stream."""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("robogrid.telemetry")

# Raw readings retained for 90 days by default; override via env if needed.
RAW_RETENTION_DAYS = getattr(settings, "TELEMETRY_RAW_RETENTION_DAYS", 90)


@shared_task
def purge_old_telemetry() -> int:
    """
    Delete raw readings past the retention window.

    Deletes in batches to avoid long-held locks / replication lag on the hot
    table. For very large fleets, prefer dropping time-based partitions (see
    deployment guide) instead of row-level DELETEs.
    """
    from .models import Reading

    cutoff = timezone.now() - timedelta(days=RAW_RETENTION_DAYS)
    total = 0
    while True:
        ids = list(
            Reading.objects.filter(time__lt=cutoff).values_list("id", flat=True)[:10000]
        )
        if not ids:
            break
        deleted, _ = Reading.objects.filter(id__in=ids).delete()
        total += deleted
    if total:
        logger.info("Purged %s old readings (older than %s days)", total, RAW_RETENTION_DAYS)
    return total
