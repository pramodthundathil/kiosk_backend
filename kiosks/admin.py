from django.contrib import admin, messages
from django.utils import timezone
from .models import KioskProfile, KioskDevice, KioskCredential
from .services import register_kiosk_device, generate_device_secret

@admin.register(KioskProfile)
class KioskProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'latitude', 'longitude', 'is_active', 'screensaver_enabled', 'created_at')
    list_filter = ('is_active', 'screensaver_enabled', 'show_products', 'show_brochures')
    search_fields = ('name', 'code', 'description')

class KioskCredentialInline(admin.StackedInline):
    model = KioskCredential
    readonly_fields = ('id', 'created_at', 'expires_at', 'revoked_at', 'last_used_at')
    fields = ('id', 'created_at', 'expires_at', 'revoked_at', 'last_used_at')
    can_delete = False
    extra = 0

@admin.register(KioskDevice)
class KioskDeviceAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'device_id', 'store', 'profile', 'status',
        'is_deployed', 'latitude', 'longitude', 'is_active', 'app_version', 'last_heartbeat_at', 'current_content_version'
    )
    list_filter = ('status', 'is_deployed', 'is_active', 'store', 'profile')
    search_fields = ('name', 'device_id', 'serial_number', 'last_ip_address')
    readonly_fields = ('id', 'status', 'last_seen_at', 'last_heartbeat_at', 'last_sync_at', 'created_at', 'updated_at')
    inlines = [KioskCredentialInline]
    actions = ['generate_new_credential', 'revoke_credential']

    @admin.action(description="Generate/Regenerate device secret")
    def generate_new_credential(self, request, queryset):
        for kiosk in queryset:
            secret = generate_device_secret()
            credential, created = KioskCredential.objects.get_or_create(kiosk=kiosk)
            credential.set_secret(secret)
            credential.revoked_at = None
            credential.save()
            self.message_user(
                request,
                f"Generated new secret for Kiosk [{kiosk.device_id}]: '{secret}' (Save this secret now! It won't be displayed again).",
                messages.WARNING
            )

    @admin.action(description="Revoke device credential")
    def revoke_credential(self, request, queryset):
        for kiosk in queryset:
            if hasattr(kiosk, 'credential'):
                kiosk.credential.revoked_at = timezone.now()
                kiosk.credential.save()
        self.message_user(request, "Selected kiosk credentials have been revoked.", messages.SUCCESS)

@admin.register(KioskCredential)
class KioskCredentialAdmin(admin.ModelAdmin):
    list_display = ('kiosk', 'created_at', 'expires_at', 'revoked_at', 'last_used_at')
    readonly_fields = ('id', 'credential_hash', 'created_at', 'last_used_at')
    search_fields = ('kiosk__device_id', 'kiosk__name')


from .models import AppRelease, KioskUpdateLog

@admin.register(AppRelease)
class AppReleaseAdmin(admin.ModelAdmin):
    list_display = (
        'version_name', 'version_code', 'release_title', 'is_published',
        'is_mandatory', 'is_active', 'target_device_type',
        'staged_rollout_percentage', 'apk_file_size', 'published_at', 'created_at'
    )
    list_filter = ('is_published', 'is_mandatory', 'is_active', 'target_device_type')
    search_fields = ('version_name', 'version_code', 'release_title', 'release_notes', 'checksum_sha256')
    readonly_fields = ('id', 'apk_file_size', 'checksum_sha256', 'created_at', 'published_at')
    filter_horizontal = ('target_kiosks',)
    actions = ['publish_release', 'unpublish_release']

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Publish selected release(s)")
    def publish_release(self, request, queryset):
        count = 0
        for rel in queryset:
            rel.is_published = True
            if not rel.published_at:
                rel.published_at = timezone.now()
            rel.save()
            count += 1
        self.message_user(request, f"{count} release(s) published successfully.", messages.SUCCESS)

    @admin.action(description="Unpublish selected release(s)")
    def unpublish_release(self, request, queryset):
        count = queryset.update(is_published=False)
        self.message_user(request, f"{count} release(s) unpublished.", messages.WARNING)


@admin.register(KioskUpdateLog)
class KioskUpdateLogAdmin(admin.ModelAdmin):
    list_display = ('kiosk', 'release', 'from_version_code', 'to_version_code', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('kiosk__device_id', 'kiosk__name', 'message')
    readonly_fields = ('id', 'kiosk', 'release', 'from_version_code', 'to_version_code', 'status', 'message', 'created_at')

