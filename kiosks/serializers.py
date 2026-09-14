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
    device_id = serializers.CharField(required=True, max_length=100)
    device_secret = serializers.CharField(required=True, write_only=True)

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

