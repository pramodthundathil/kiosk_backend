from rest_framework import status, views
from rest_framework.response import Response
from django.utils import timezone
from kiosks.authentication import KioskJWTAuthentication
from kiosks.permissions import IsKioskAuthenticated
from kiosks.models import KioskDevice
from .serializers import KioskHeartbeatSerializer
from .services import update_kiosk_status_and_alerts

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

class KioskHeartbeatView(views.APIView):
    """
    POST /api/kiosk/heartbeat/
    Receives periodic telemetry signal from active Android Kiosk applications.
    Updates connection status, telemetry flags, checks content sync requirements, and returns commands.
    """
    authentication_classes = [KioskJWTAuthentication]
    permission_classes = [IsKioskAuthenticated]
    serializer_class = KioskHeartbeatSerializer

    def post(self, request):
        serializer = KioskHeartbeatSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        kiosk = request.kiosk
        data = serializer.validated_data

        now = timezone.now()

        # Update telemetry fields
        kiosk.last_heartbeat_at = now
        kiosk.last_seen_at = now
        kiosk.last_ip_address = get_client_ip(request)

        if 'app_version' in data and data['app_version']:
            kiosk.app_version = data['app_version']
        if 'android_version' in data and data['android_version']:
            kiosk.android_version = data['android_version']
        if 'device_model' in data and data['device_model']:
            kiosk.device_model = data['device_model']
        if 'manufacturer' in data and data['manufacturer']:
            kiosk.manufacturer = data['manufacturer']
        if 'battery_percentage' in data and data['battery_percentage'] is not None:
            kiosk.battery_percentage = data['battery_percentage']
        if 'network_type' in data and data['network_type']:
            kiosk.network_type = data['network_type']
        if 'screen_on' in data:
            kiosk.screen_on = data['screen_on']
        if 'app_running' in data:
            kiosk.app_running = data['app_running']
        if 'current_content_version' in data and data['current_content_version']:
            kiosk.current_content_version = data['current_content_version']
        if 'last_error' in data:
            kiosk.last_error = data['last_error']

        kiosk.save()

        # Update status and process alerts
        current_status = update_kiosk_status_and_alerts(kiosk)

        # Check content sync requirement
        sync_required = (kiosk.current_content_version != kiosk.desired_content_version)

        # Pending commands placeholder (expandable in Phase 7)
        commands = []

        return Response({
            "success": True,
            "server_time": now.isoformat(),
            "heartbeat_interval": 30,
            "status": current_status,
            "sync_required": sync_required,
            "desired_content_version": kiosk.desired_content_version,
            "commands": commands
        }, status=status.HTTP_200_OK)
