"""
Signals that keep the audit trail and live dashboard in sync with device state.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.core.realtime import broadcast, group_for_device, group_for_org
from apps.core.services import record_audit

from .models import Device


@receiver(pre_save, sender=Device)
def remember_previous_status(sender, instance: Device, **kwargs):
    """Stash the prior status so post_save can detect transitions."""
    if instance._state.adding:
        instance._prev_status = None
        return
    instance._prev_status = (
        Device.all_objects.filter(pk=instance.pk)
        .values_list("status", flat=True)
        .first()
    )


@receiver(post_save, sender=Device)
def on_device_saved(sender, instance: Device, created, **kwargs):
    if created:
        record_audit(action="create", target_type="device",
                     target_id=instance.id, summary=f"Device '{instance.name}' registered")

    prev = getattr(instance, "_prev_status", None)
    if not created and prev and prev != instance.status:
        record_audit(
            action="update", target_type="device", target_id=instance.id,
            summary=f"Status {prev} → {instance.status}",
            metadata={"from": prev, "to": instance.status},
        )

    # Push a compact state update to anyone watching this device or org.
    payload = {
        "device_id": str(instance.id),
        "serial": instance.serial,
        "status": instance.status,
        "battery_level": instance.battery_level,
        "health_score": instance.health_score,
        "last_seen": instance.last_seen.isoformat() if instance.last_seen else None,
        "latitude": instance.latitude,
        "longitude": instance.longitude,
    }
    broadcast(group_for_device(instance.id), "device.state", payload)
    if instance.organization_id:
        broadcast(group_for_org(instance.organization_id), "device.state", payload)
