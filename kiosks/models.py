import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from stores.models import Store
from .apk_validator import compute_file_sha256_and_size, validate_apk_file

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


class AppRelease(models.Model):
    class DeviceType(models.TextChoices):
        ALL = 'ALL', 'All Kiosks'
        ANDROID_TV = 'ANDROID_TV', 'Android TV'
        TABLET = 'TABLET', 'Tablet / Touch Screen'
        STANDALONE = 'STANDALONE', 'Standalone Kiosk'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version_name = models.CharField(max_length=50, help_text="Semantic version string, e.g. 1.0.5")
    version_code = models.PositiveIntegerField(unique=True, db_index=True, help_text="Monotonically increasing integer Android versionCode")
    release_title = models.CharField(max_length=255, help_text="Release title, e.g. Product Display Improvements")
    release_notes = models.TextField(help_text="Release notes / changelog items (one per line or markdown)")
    
    apk_file = models.FileField(upload_to="apks/", blank=True, null=True, help_text="APK installer binary file")
    apk_url = models.URLField(max_length=500, blank=True, help_text="Direct APK download URL (S3, CDN, or external VPS)")
    apk_file_size = models.PositiveBigIntegerField(blank=True, null=True, help_text="File size in bytes")
    checksum_sha256 = models.CharField(max_length=64, blank=True, help_text="SHA-256 hash checksum")
    
    is_mandatory = models.BooleanField(default=False, help_text="Require kiosks to update before further operation")
    is_active = models.BooleanField(default=True, db_index=True, help_text="Enable or disable this release")
    is_published = models.BooleanField(default=False, db_index=True, help_text="Published releases are discoverable by kiosks")
    
    minimum_supported_version = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        help_text="Minimum current versionCode required on kiosk before upgrading"
    )
    target_device_type = models.CharField(
        max_length=50, 
        choices=DeviceType.choices, 
        default=DeviceType.ALL,
        help_text="Target device hardware family"
    )
    target_kiosks = models.ManyToManyField(
        'KioskDevice', 
        blank=True, 
        related_name='targeted_releases',
        help_text="Optional selective targeting: if selected, only these specific kiosks receive the update"
    )
    staged_rollout_percentage = models.PositiveIntegerField(
        default=100,
        help_text="Percentage (1-100) of kiosk fleet to deploy to in stages"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='app_releases'
    )

    class Meta:
        ordering = ['-version_code']
        verbose_name = 'App Release'
        verbose_name_plural = 'App Releases'

    def __str__(self):
        status = "Published" if self.is_published else "Draft"
        return f"v{self.version_name} ({self.version_code}) - {self.release_title} [{status}]"

    def clean(self):
        super().clean()
        if self.apk_file and not self.checksum_sha256:
            validate_apk_file(self.apk_file)
            sha, size = compute_file_sha256_and_size(self.apk_file)
            self.checksum_sha256 = sha
            if not self.apk_file_size:
                self.apk_file_size = size

    def save(self, *args, **kwargs):
        if self.apk_file and (not self.checksum_sha256 or not self.apk_file_size):
            validate_apk_file(self.apk_file)
            sha, size = compute_file_sha256_and_size(self.apk_file)
            self.checksum_sha256 = sha
            if not self.apk_file_size:
                self.apk_file_size = size
        if self.is_published and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def get_effective_apk_url(self, request=None) -> str:
        """Returns the download URL for the APK: explicit apk_url or media file absolute URL."""
        if self.apk_url:
            return self.apk_url
        if self.apk_file:
            if request:
                url = request.build_absolute_uri(self.apk_file.url)
                if request.is_secure() or request.META.get('HTTP_X_FORWARDED_PROTO') == 'https':
                    url = url.replace('http://', 'https://', 1)
                return url
            return self.apk_file.url
        return ""

    def get_release_notes_list(self) -> list:
        """Splits release notes by line break into a clean list."""
        if not self.release_notes:
            return []
        lines = [line.strip().lstrip('•-* ').strip() for line in self.release_notes.splitlines()]
        return [l for l in lines if l]


class KioskDevice(models.Model):
    class Status(models.TextChoices):
        ONLINE = 'ONLINE', 'Online'
        WARNING = 'WARNING', 'Warning'
        OFFLINE = 'OFFLINE', 'Offline'
        DISABLED = 'DISABLED', 'Disabled'

    class UpdateStatus(models.TextChoices):
        UP_TO_DATE = 'UP_TO_DATE', 'Up to Date'
        UPDATE_AVAILABLE = 'UPDATE_AVAILABLE', 'Update Available'
        DOWNLOADING = 'DOWNLOADING', 'Downloading'
        INSTALLING = 'INSTALLING', 'Installing'
        UPDATED = 'UPDATED', 'Updated'
        FAILED = 'FAILED', 'Failed'
        OFFLINE = 'OFFLINE', 'Offline'

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
    current_app_version_code = models.PositiveIntegerField(default=1, db_index=True, help_text="Current Android app versionCode")
    device_model = models.CharField(max_length=100, blank=True, null=True)
    manufacturer = models.CharField(max_length=100, blank=True, null=True)
    screen_width = models.PositiveIntegerField(null=True, blank=True)
    screen_height = models.PositiveIntegerField(null=True, blank=True)
    screen_density = models.FloatField(null=True, blank=True)
    serial_number = models.CharField(max_length=100, blank=True, null=True)

    # Remote Update Telemetry & State Tracking
    last_update_check = models.DateTimeField(null=True, blank=True, help_text="Timestamp of last update check")
    update_status = models.CharField(
        max_length=30, 
        choices=UpdateStatus.choices, 
        default=UpdateStatus.UP_TO_DATE, 
        db_index=True
    )
    update_started_at = models.DateTimeField(null=True, blank=True)
    update_completed_at = models.DateTimeField(null=True, blank=True)
    update_error = models.TextField(blank=True, null=True, help_text="Latest update failure or verification error")
    pending_update_release = models.ForeignKey(
        AppRelease,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='pending_kiosks',
        help_text="Target release currently queued or being installed"
    )
    force_update_requested = models.BooleanField(default=False, help_text="Signals device to immediately download and install latest release")
    check_update_requested = models.BooleanField(default=False, help_text="Signals device to perform an immediate update check")

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
    
    # Assigned products for display on this kiosk
    assigned_products = models.ManyToManyField(
        'products.Product',
        related_name='assigned_kiosks',
        blank=True,
        help_text="Products assigned to display on this kiosk"
    )

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
            models.Index(fields=['update_status']),
            models.Index(fields=['last_seen_at']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} [{self.device_id}] ({self.status}) - App v{self.app_version or '1.0.0'}"


class KioskUpdateLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kiosk = models.ForeignKey(KioskDevice, on_delete=models.CASCADE, related_name='update_logs')
    release = models.ForeignKey(AppRelease, null=True, blank=True, on_delete=models.SET_NULL, related_name='device_logs')
    from_version_code = models.PositiveIntegerField(null=True, blank=True)
    to_version_code = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=KioskDevice.UpdateStatus.choices)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Kiosk Update Log'
        verbose_name_plural = 'Kiosk Update Logs'

    def __str__(self):
        return f"{self.kiosk.device_id}: {self.status} at {self.created_at}"


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

