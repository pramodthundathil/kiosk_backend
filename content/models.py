import uuid
from django.db import models
from kiosks.models import KioskProfile

class MediaAsset(models.Model):
    class AssetType(models.TextChoices):
        IMAGE = 'IMAGE', 'Product Image'
        VIDEO = 'VIDEO', 'Promotional Video'
        PDF_BROCHURE = 'PDF_BROCHURE', 'PDF Brochure'
        TECH_SHEET = 'TECH_SHEET', 'Technical Specification'
        THREE_D = 'THREE_D', '3D Asset'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    asset_type = models.CharField(max_length=50, choices=AssetType.choices, default=AssetType.VIDEO)
    file = models.FileField(upload_to='media_assets/', blank=True, null=True)
    external_url = models.URLField(blank=True, null=True, help_text="Alternative external file or embed link")
    file_size_mb = models.FloatField(default=0.0)
    kiosk_profile = models.ForeignKey(
        KioskProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='media_assets'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='media_assets'
    )
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_asset_type_display()})"


class Screensaver(models.Model):
    class Orientation(models.TextChoices):
        LANDSCAPE = 'LANDSCAPE', 'Landscape (Horizontal - 16:9 / 1920x1080)'
        PORTRAIT = 'PORTRAIT', 'Portrait (Vertical - 9:16 / 1080x1920)'
        BOTH = 'BOTH', 'Universal (Fits Both)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, help_text="Screensaver display title")
    image = models.ImageField(upload_to='screensavers/', help_text="High-resolution screensaver image")
    orientation = models.CharField(
        max_length=20,
        choices=Orientation.choices,
        default=Orientation.LANDSCAPE,
        db_index=True,
        help_text="Monitor orientation mode (Landscape, Portrait, or Universal)"
    )
    display_order = models.PositiveIntegerField(default=0, help_text="Display order sequence in sliding animation")
    duration_seconds = models.PositiveIntegerField(default=10, help_text="Slide display duration in seconds")
    caption = models.CharField(max_length=255, blank=True, null=True, help_text="Optional caption / overlay text")
    description = models.TextField(blank=True, null=True, help_text="Internal notes or description")
    is_active = models.BooleanField(default=True, db_index=True)

    kiosk_profile = models.ForeignKey(
        KioskProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='screensavers',
        help_text="Target specific kiosk profile (leave empty for all)"
    )
    kiosks = models.ManyToManyField(
        'kiosks.KioskDevice',
        blank=True,
        related_name='screensavers',
        help_text="Target specific kiosks (leave empty for all)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', '-created_at']
        verbose_name = 'Screensaver'
        verbose_name_plural = 'Screensavers'

    def __str__(self):
        return f"{self.title} [{self.get_orientation_display()}]"

