from django.contrib import admin
from .models import MediaAsset, Screensaver

@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ('title', 'asset_type', 'is_active', 'created_at')
    list_filter = ('asset_type', 'is_active')
    search_fields = ('title', 'description')

@admin.register(Screensaver)
class ScreensaverAdmin(admin.ModelAdmin):
    list_display = ('title', 'orientation', 'duration_seconds', 'display_order', 'is_active', 'kiosk_profile', 'created_at')
    list_filter = ('orientation', 'is_active', 'kiosk_profile')
    search_fields = ('title', 'caption', 'description')
    ordering = ('display_order', '-created_at')

