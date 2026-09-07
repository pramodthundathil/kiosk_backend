import uuid
from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from stores.models import Store

class KioskProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, help_text="Profile display name (e.g. Standard, Showroom)")
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text="Profile unique code (e.g. STANDARD, DEMO)")
    description = models.TextField(blank=True, null=True)
    
    # Feature & Content display flags
    show_products = models.BooleanField(default=True)
    show_brochures = models.BooleanField(default=True)
    show_technical_documents = models.BooleanField(default=True)
    show_pricing = models.BooleanField(default=True)
    show_videos = models.BooleanField(default=True)
    show_3d_assets = models.BooleanField(default=False)
    show_whiteboard = models.BooleanField(default=False)
    
    # Screensaver settings
    screensaver_enabled = models.BooleanField(default=True)
    screensaver_timeout_seconds = models.PositiveIntegerField(default=300)
    
    # Location / GPS coordinates (optional)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, help_text="Optional profile latitude coordinate")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, help_text="Optional profile longitude coordinate")

    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Kiosk Profile'
        verbose_name_plural = 'Kiosk Profiles'

    def __str__(self):
        return f"{self.name} ({self.code})"


class KioskDevice(models.Model):
    class Status(models.TextChoices):
        ONLINE = 'ONLINE', 'Online'
        WARNING = 'WARNING', 'Warning'
        OFFLINE = 'OFFLINE', 'Offline'
        DISABLED = 'DISABLED', 'Disabled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_id = models.CharField(max_length=100, unique=True, db_index=True, help_text="Globally unique physical device ID")
    name = models.CharField(max_length=255, help_text="Human-readable kiosk name")
    
    store = models.ForeignKey(
        Store,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kiosks',
        db_index=True
    )
    profile = models.ForeignKey(
        KioskProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kiosks'
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OFFLINE,
        db_index=True
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_deployed = models.BooleanField(default=False, db_index=True, help_text="Indicates whether the kiosk device is deployed at physical location")
    deployed_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when device was deployed")

    # Location / GPS coordinates (optional)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, help_text="Optional device latitude coordinate")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, help_text="Optional device longitude coordinate")

    # Device hardware specifications
    android_version = models.CharField(max_length=50, blank=True, null=True)
    app_version = models.CharField(max_length=50, blank=True, null=True)
    device_model = models.CharField(max_length=100, blank=True, null=True)
    manufacturer = models.CharField(max_length=100, blank=True, null=True)
    screen_width = models.PositiveIntegerField(null=True, blank=True)
    screen_height = models.PositiveIntegerField(null=True, blank=True)
    screen_density = models.FloatField(null=True, blank=True)
    serial_number = models.CharField(max_length=100, blank=True, null=True)

    # Network telemetry
    last_ip_address = models.GenericIPAddressField(null=True, blank=True)
    network_type = models.CharField(max_length=50, blank=True, null=True)

    # Monitoring & Sync timestamps
    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    # Content versioning tracking
    current_content_version = models.CharField(max_length=50, default="1")
    desired_content_version = models.CharField(max_length=50, default="1")

    # Health & status metrics
    battery_percentage = models.SmallIntegerField(null=True, blank=True)
    screen_on = models.BooleanField(default=True)
    app_running = models.BooleanField(default=True)
    last_error = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Kiosk Device'
        verbose_name_plural = 'Kiosk Devices'
        indexes = [
            models.Index(fields=['device_id']),
            models.Index(fields=['store']),
            models.Index(fields=['status']),
            models.Index(fields=['last_seen_at']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} [{self.device_id}] ({self.status})"


class KioskCredential(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kiosk = models.OneToOneField(
        KioskDevice,
        on_delete=models.CASCADE,
        related_name='credential'
    )
    credential_hash = models.CharField(max_length=255, help_text="PBKDF2/Argon2/Bcrypt hash of device_secret")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def set_secret(self, raw_secret: str):
        """Hashes the secret key using Django's password hashers."""
        self.credential_hash = make_password(raw_secret)

    def check_secret(self, raw_secret: str) -> bool:
        """Verifies the raw secret against stored hash."""
        if self.revoked_at is not None:
            return False
        return check_password(raw_secret, self.credential_hash)

    def is_valid(self) -> bool:
        return self.revoked_at is None


    def __str__(self):
        return f"Credential for {self.kiosk.device_id}"
