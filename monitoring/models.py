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


class ProductInteraction(models.Model):
    class InteractionType(models.TextChoices):
        CLICK = 'CLICK', 'Product Card Click'
        VIEW_DETAIL = 'VIEW_DETAIL', 'Full Detail View'
        SPEC_TAB_CLICK = 'SPEC_TAB_CLICK', 'Specification Tab Click'
        BROCHURE_VIEW = 'BROCHURE_VIEW', 'Brochure View'
        WHITEBOARD_OPEN = 'WHITEBOARD_OPEN', 'Whiteboard Launch'
        SEARCH_SELECT = 'SEARCH_SELECT', 'Search Selection'
        CATEGORY_CLICK = 'CATEGORY_CLICK', 'Category Click'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kiosk = models.ForeignKey(
        KioskDevice,
        on_delete=models.CASCADE,
        related_name='product_interactions',
        db_index=True
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='interactions',
        db_index=True
    )
    interaction_type = models.CharField(
        max_length=50,
        choices=InteractionType.choices,
        default=InteractionType.CLICK,
        db_index=True
    )
    session_id = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Product Interaction'
        verbose_name_plural = 'Product Interactions'
        indexes = [
            models.Index(fields=['kiosk', '-created_at']),
            models.Index(fields=['product', '-created_at']),
            models.Index(fields=['interaction_type']),
            models.Index(fields=['session_id']),
        ]

    def __str__(self):
        prod_name = self.product.name if self.product else "General/Category"
        return f"[{self.interaction_type}] {self.kiosk.name or self.kiosk.device_id} -> {prod_name}"


class KioskUsageSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kiosk = models.ForeignKey(
        KioskDevice,
        on_delete=models.CASCADE,
        related_name='usage_sessions',
        db_index=True
    )
    session_id = models.CharField(max_length=64, unique=True, db_index=True)
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True, db_index=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    total_clicks = models.PositiveIntegerField(default=0)
    products_viewed_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Kiosk Usage Session'
        verbose_name_plural = 'Kiosk Usage Sessions'
        indexes = [
            models.Index(fields=['kiosk', '-started_at']),
            models.Index(fields=['started_at']),
        ]

    def __str__(self):
        return f"Session {self.session_id[:8]} on {self.kiosk.name or self.kiosk.device_id} ({self.duration_seconds}s, {self.total_clicks} clicks)"

