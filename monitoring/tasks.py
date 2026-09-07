from celery import shared_task
from kiosks.models import KioskDevice
from .services import update_kiosk_status_and_alerts

@shared_task
def check_kiosk_status():
    """
    Periodic Celery task executing every 30 seconds.
    Evaluates active kiosks and updates connection statuses (ONLINE -> WARNING -> OFFLINE).
    Handles alert deduplication and auto-resolution.
    """
    active_kiosks = KioskDevice.objects.filter(is_active=True).exclude(status=KioskDevice.Status.DISABLED)
    updated_count = 0

    for kiosk in active_kiosks:
        update_kiosk_status_and_alerts(kiosk)
        updated_count += 1

    return f"Checked status for {updated_count} active kiosks."
