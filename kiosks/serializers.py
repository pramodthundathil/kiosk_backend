from django.db import models
from rest_framework import serializers
from .models import KioskDevice, KioskProfile, KioskCredential
from stores.models import Store
from content.models import Screensaver


class ScreensaverSerializer(serializers.ModelSerializer):
    orientation_display = serializers.CharField(source='get_orientation_display', read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Screensaver
        fields = [
            'id', 'title', 'image', 'image_url', 'orientation', 'orientation_display',
            'duration_seconds', 'display_order', 'caption', 'description',
            'is_active', 'created_at', 'updated_at'
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class KioskLoginSerializer(serializers.Serializer):
    device_id = serializers.CharField(required=False, max_length=100, allow_blank=True)
    mac_address = serializers.CharField(required=False, max_length=100, allow_blank=True)
    device_secret = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        device_id = attrs.get('device_id') or attrs.get('mac_address')
        if not device_id:
            raise serializers.ValidationError("Either device_id or mac_address is required.")
        attrs['device_id'] = device_id.strip()
        return attrs

class KioskProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = KioskProfile
        fields = '__all__'

class KioskDeviceSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.name', read_only=True)
    profile_code = serializers.CharField(source='profile.code', read_only=True)
    screensavers = serializers.SerializerMethodField()

    class Meta:
        model = KioskDevice
        fields = [
            'id', 'device_id', 'name', 'store', 'store_name', 'profile', 'profile_code',
            'status', 'is_active', 'android_version', 'app_version', 'device_model',
            'manufacturer', 'screen_width', 'screen_height', 'screen_density',
            'serial_number', 'last_ip_address', 'network_type', 'last_seen_at',
            'last_heartbeat_at', 'last_sync_at', 'current_content_version',
            'desired_content_version', 'battery_percentage', 'screen_on',
            'app_running', 'last_error', 'screensavers', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']

    def get_screensavers(self, obj):
        # Determine orientation based on screen resolution if available
        orientation_filter = None
        if obj.screen_width and obj.screen_height:
            if obj.screen_width >= obj.screen_height:
                orientation_filter = 'LANDSCAPE'
            else:
                orientation_filter = 'PORTRAIT'
        
        qs = Screensaver.objects.filter(is_active=True)
        if orientation_filter:
            qs = qs.filter(models.Q(orientation=orientation_filter) | models.Q(orientation='BOTH'))
        
        # Filter by profile if set
        if obj.profile:
            qs = qs.filter(models.Q(kiosk_profile=obj.profile) | models.Q(kiosk_profile__isnull=True))

        serializer = ScreensaverSerializer(qs.order_by('display_order', '-created_at'), many=True, context=self.context)
        return serializer.data

class KioskRegistrationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=True)
    device_id = serializers.CharField(max_length=100, required=True)
    store_id = serializers.UUIDField(required=False, allow_null=True)
    profile_id = serializers.UUIDField(required=False, allow_null=True)


from .models import AppRelease, KioskUpdateLog

class AppReleaseSerializer(serializers.ModelSerializer):
    apk_download_url = serializers.SerializerMethodField()
    release_notes_list = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = AppRelease
        fields = [
            'id', 'version_name', 'version_code', 'release_title', 'release_notes',
            'release_notes_list', 'apk_file', 'apk_url', 'apk_download_url',
            'apk_file_size', 'checksum_sha256', 'is_mandatory', 'is_active',
            'is_published', 'minimum_supported_version', 'target_device_type',
            'staged_rollout_percentage', 'created_at', 'published_at',
            'created_by', 'created_by_username'
        ]
        read_only_fields = ['id', 'apk_file_size', 'checksum_sha256', 'created_at', 'published_at']

    def get_apk_download_url(self, obj):
        request = self.context.get('request')
        return obj.get_effective_apk_url(request)

    def get_release_notes_list(self, obj):
        return obj.get_release_notes_list()


class AppUpdateCheckResponseSerializer(serializers.Serializer):
    update_available = serializers.BooleanField()
    latest_version_name = serializers.CharField(required=False, allow_null=True)
    latest_version_code = serializers.IntegerField()
    current_version_code = serializers.IntegerField()
    mandatory = serializers.BooleanField(required=False)
    release_title = serializers.CharField(required=False, allow_null=True)
    release_notes = serializers.ListField(child=serializers.CharField(), required=False)
    apk_url = serializers.CharField(required=False, allow_null=True)
    apk_size = serializers.IntegerField(required=False, allow_null=True)
    sha256 = serializers.CharField(required=False, allow_null=True)


class AppUpdateStatusReportSerializer(serializers.Serializer):
    device_id = serializers.CharField(required=False, allow_blank=True)
    mac_address = serializers.CharField(required=False, allow_blank=True)
    version_name = serializers.CharField(required=True, max_length=50)
    version_code = serializers.IntegerField(required=True)
    status = serializers.ChoiceField(choices=KioskDevice.UpdateStatus.choices)
    message = serializers.CharField(required=False, allow_blank=True, default="")


