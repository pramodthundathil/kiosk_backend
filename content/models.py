import uuid
from django.db import models
from kiosks.models import KioskProfile

class MediaAsset(models.Model):
    class AssetType(models.TextChoices):
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
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_asset_type_display()})"
