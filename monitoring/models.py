import uuid
from django.db import models
from kiosks.models import KioskDevice

class KioskEvent(models.Model):
    class EventType(models.TextChoices):
        BOOT = 'BOOT', 'Boot'
        HEARTBEAT = 'HEARTBEAT', 'Heartbeat'
        APP_STARTED = 'APP_STARTED', 'App Started'
        APP_STOPPED = 'APP_STOPPED', 'App Stopped'
        APP_CRASH = 'APP_CRASH', 'App Crash'
        SYNC_STARTED = 'SYNC_STARTED', 'Sync Started'
        SYNC_COMPLETED = 'SYNC_COMPLETED', 'Sync Completed'
        SYNC_FAILED = 'SYNC_FAILED', 'Sync Failed'
        NETWORK_CONNECTED = 'NETWORK_CONNECTED', 'Network Connected'
        NETWORK_DISCONNECTED = 'NETWORK_DISCONNECTED', 'Network Disconnected'
        LOW_BATTERY = 'LOW_BATTERY', 'Low Battery'
        SCREEN_OFF = 'SCREEN_OFF', 'Screen Off'
        SCREEN_ON = 'SCREEN_ON', 'Screen On'
        ERROR = 'ERROR', 'Error'

    class Severity(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        ERROR = 'ERROR', 'Error'
        CRITICAL = 'CRITICAL', 'Critical'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kiosk = models.ForeignKey(
        KioskDevice,
        on_delete=models.CASCADE,
        related_name='events',
        db_index=True
    )
    event_type = models.CharField(max_length=50, choices=EventType.choices, db_index=True)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.INFO)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Kiosk Event'
        verbose_name_plural = 'Kiosk Events'
        indexes = [
            models.Index(fields=['kiosk', '-created_at']),
            models.Index(fields=['event_type']),
        ]

    def __str__(self):
        return f"[{self.event_type}] {self.kiosk.device_id}: {self.message[:50]}"


class Alert(models.Model):
    class AlertType(models.TextChoices):
        KIOSK_OFFLINE = 'KIOSK_OFFLINE', 'Kiosk Offline'
        LOW_BATTERY = 'LOW_BATTERY', 'Low Battery'
        SYNC_FAILED = 'SYNC_FAILED', 'Sync Failed'
        APP_ERROR = 'APP_ERROR', 'App Error'
        OLD_APP_VERSION = 'OLD_APP_VERSION', 'Old App Version'
        CONTENT_OUTDATED = 'CONTENT_OUTDATED', 'Content Outdated'

    class Severity(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        ERROR = 'ERROR', 'Error'
        CRITICAL = 'CRITICAL', 'Critical'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kiosk = models.ForeignKey(
        KioskDevice,
        on_delete=models.CASCADE,
        related_name='alerts',
        db_index=True
    )
    alert_type = models.CharField(max_length=50, choices=AlertType.choices, db_index=True)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.WARNING)
    message = models.TextField()
    opened_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-opened_at']
        verbose_name = 'Alert'
        verbose_name_plural = 'Alerts'
        indexes = [
            models.Index(fields=['kiosk', 'resolved_at']),
            models.Index(fields=['alert_type']),
        ]

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None

    def __str__(self):
        status_str = "RESOLVED" if self.is_resolved else "OPEN"
        return f"[{self.alert_type}] {self.kiosk.device_id} ({status_str})"
