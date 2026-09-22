from rest_framework import serializers

class KioskHeartbeatSerializer(serializers.Serializer):
    app_version = serializers.CharField(required=False, allow_blank=True, max_length=50)
    android_version = serializers.CharField(required=False, allow_blank=True, max_length=50)
    device_model = serializers.CharField(required=False, allow_blank=True, max_length=100)
    manufacturer = serializers.CharField(required=False, allow_blank=True, max_length=100)
    battery_percentage = serializers.IntegerField(required=False, allow_null=True)
    network_type = serializers.CharField(required=False, allow_blank=True, max_length=50)
    screen_on = serializers.BooleanField(required=False, default=True)
    app_running = serializers.BooleanField(required=False, default=True)
    current_content_version = serializers.CharField(required=False, allow_blank=True, max_length=50)
    last_error = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    mac_address = serializers.CharField(required=False, allow_blank=True, max_length=100)
    device_id = serializers.CharField(required=False, allow_blank=True, max_length=100)
    is_authenticated = serializers.BooleanField(required=False, default=False)

