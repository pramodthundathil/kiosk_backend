from rest_framework import serializers
from .models import KioskDevice, KioskProfile, KioskCredential
from stores.models import Store

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

    class Meta:
        model = KioskDevice
        fields = [
            'id', 'device_id', 'name', 'store', 'store_name', 'profile', 'profile_code',
            'status', 'is_active', 'android_version', 'app_version', 'device_model',
            'manufacturer', 'screen_width', 'screen_height', 'screen_density',
            'serial_number', 'last_ip_address', 'network_type', 'last_seen_at',
            'last_heartbeat_at', 'last_sync_at', 'current_content_version',
            'desired_content_version', 'battery_percentage', 'screen_on',
            'app_running', 'last_error', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']

class KioskRegistrationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=True)
    device_id = serializers.CharField(max_length=100, required=True)
    store_id = serializers.UUIDField(required=False, allow_null=True)
    profile_id = serializers.UUIDField(required=False, allow_null=True)
