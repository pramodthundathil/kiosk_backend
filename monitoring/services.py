from django.utils import timezone
from datetime import timedelta
from kiosks.models import KioskDevice
from .models import Alert, KioskEvent

def calculate_kiosk_status(kiosk: KioskDevice) -> str:
    """
    Calculates dynamic Kiosk connection status based strictly on SERVER TIME.
    Configured for 10-second heartbeat cadence:
    - DISABLED: Admin disabled kiosk
    - ONLINE: last_heartbeat_at <= 15 seconds ago (10s heartbeat + 5s network jitter)
    - WARNING: last_heartbeat_at > 15 seconds and <= 25 seconds ago
    - OFFLINE: last_heartbeat_at > 25 seconds ago or missing
    """
    if kiosk.status == KioskDevice.Status.DISABLED or not kiosk.is_active:
        return KioskDevice.Status.DISABLED

    if not kiosk.last_heartbeat_at:
        return KioskDevice.Status.OFFLINE

    now = timezone.now()
    diff_seconds = (now - kiosk.last_heartbeat_at).total_seconds()

    if diff_seconds <= 15:
        return KioskDevice.Status.ONLINE
    elif diff_seconds <= 25:
        return KioskDevice.Status.WARNING
    else:
        return KioskDevice.Status.OFFLINE



def update_kiosk_status_and_alerts(kiosk: KioskDevice) -> str:
    """
    Recalculates kiosk status, creates/updates KioskEvent records, and manages
    deduplicated alerts for OFFLINE / WARNING transitions.
    """
    old_status = kiosk.status
    new_status = calculate_kiosk_status(kiosk)

    if old_status != new_status:
        kiosk.status = new_status
        kiosk.save(update_fields=['status', 'updated_at'])

        # Create status change event
        KioskEvent.objects.create(
            kiosk=kiosk,
            event_type=KioskEvent.EventType.HEARTBEAT,
            severity=KioskEvent.Severity.INFO if new_status == KioskDevice.Status.ONLINE else KioskEvent.Severity.WARNING,
            message=f"Kiosk status changed from {old_status} to {new_status}."
        )

        # Alert handling for status transitions
        if new_status == KioskDevice.Status.OFFLINE:
            # Create ONE deduplicated open offline alert if not already active
            open_alert = Alert.objects.filter(
                kiosk=kiosk,
                alert_type=Alert.AlertType.KIOSK_OFFLINE,
                resolved_at__isnull=True
            ).first()

            if not open_alert:
                Alert.objects.create(
                    kiosk=kiosk,
                    alert_type=Alert.AlertType.KIOSK_OFFLINE,
                    severity=Alert.Severity.CRITICAL,
                    message=f"Terminal {kiosk.device_id} ({kiosk.name}) at {kiosk.store.name if kiosk.store else 'Unspecified Location'} missed periodic 10-second heartbeat (>25s timeout)."
                )

        elif new_status == KioskDevice.Status.ONLINE:
            # Auto-resolve existing open offline alert upon reconnection
            open_alerts = Alert.objects.filter(
                kiosk=kiosk,
                alert_type=Alert.AlertType.KIOSK_OFFLINE,
                resolved_at__isnull=True
            )
            for alert in open_alerts:
                alert.resolved_at = timezone.now()
                alert.save(update_fields=['resolved_at'])

    return new_status
