from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.db.models import Q
from kiosks.authentication import KioskJWTAuthentication
from kiosks.models import KioskDevice
from .serializers import KioskHeartbeatSerializer
from .services import update_kiosk_status_and_alerts
from .models import KioskEvent

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

class KioskHeartbeatView(views.APIView):
    """
    POST /api/kiosk/heartbeat/
    Receives periodic telemetry signal from active Android Kiosk applications.
    Supports both JWT-authenticated sessions and direct physical MAC address identification.
    Addresses dynamic IP environments by tracking kiosks strictly via unique hardware MAC ID.
    """
    authentication_classes = [KioskJWTAuthentication]
    permission_classes = [AllowAny]
    serializer_class = KioskHeartbeatSerializer

    def post(self, request):
        serializer = KioskHeartbeatSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        kiosk = getattr(request, 'kiosk', None)

        # In dynamic IP environments, resolve kiosk strictly by physical hardware MAC address
        if not kiosk:
            mac = (
                data.get('mac_address') or 
                data.get('device_id') or 
                request.headers.get('X-Device-MAC') or 
                request.headers.get('X-Device-Id')
            )
            if mac:
                clean_mac = mac.strip()
                kiosk = KioskDevice.objects.filter(
                    Q(device_id__iexact=clean_mac) | Q(name__iexact=clean_mac)
                ).first()

        if not kiosk:
            return Response(
                {"error": "Kiosk not recognized. Please provide a registered device MAC address or valid Bearer token."},
                status=status.HTTP_404_NOT_FOUND
            )

        if not kiosk.is_active:
            return Response({"error": "This kiosk device is marked inactive."}, status=status.HTTP_403_FORBIDDEN)

        if kiosk.status == KioskDevice.Status.DISABLED:
            return Response({"error": "This kiosk device has been disabled by an administrator."}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now()

        # Update telemetry fields (Dynamic IP is recorded for observation, MAC is identity)
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

        location_recorded = False
        if 'latitude' in data and data['latitude'] is not None:
            kiosk.latitude = data['latitude']
            location_recorded = True
        if 'longitude' in data and data['longitude'] is not None:
            kiosk.longitude = data['longitude']
            location_recorded = True

        kiosk.save()

        # Update status and process alerts
        current_status = update_kiosk_status_and_alerts(kiosk)

        # Log location event if coordinates updated
        if location_recorded:
            KioskEvent.objects.create(
                kiosk=kiosk,
                event_type=KioskEvent.EventType.HEARTBEAT,
                severity=KioskEvent.Severity.INFO,
                message=f"Terminal location recorded: Lat {kiosk.latitude}, Lon {kiosk.longitude}",
                metadata={"latitude": str(kiosk.latitude), "longitude": str(kiosk.longitude)}
            )

        # Check content sync requirement
        sync_required = (kiosk.current_content_version != kiosk.desired_content_version)

        # Pending commands placeholder (expandable in Phase 7)
        commands = []

        # Log occasional heartbeat event for telemetry stream (every 60s max per device)
        last_hb_event = KioskEvent.objects.filter(
            kiosk=kiosk,
            event_type=KioskEvent.EventType.HEARTBEAT
        ).order_by('-created_at').first()
        is_auth = data.get('is_authenticated', False) or hasattr(request, 'kiosk')
        state_label = "Logged In (Operational)" if is_auth else "Terminal Active (Login Screen)"
        if not last_hb_event or (now - last_hb_event.created_at).total_seconds() > 60:
            KioskEvent.objects.create(
                kiosk=kiosk,
                event_type=KioskEvent.EventType.HEARTBEAT,
                severity=KioskEvent.Severity.INFO,
                message=f"Node heartbeat ping received via MAC [{kiosk.device_id}]. State: {state_label}, Dynamic IP: {kiosk.last_ip_address}",
                metadata={
                    "mac_address": kiosk.device_id,
                    "is_authenticated": is_auth,
                    "battery": kiosk.battery_percentage,
                    "ip": kiosk.last_ip_address,
                    "screen_on": kiosk.screen_on,
                    "content_ver": kiosk.current_content_version
                }
            )

        return Response({
            "success": True,
            "device_id": kiosk.device_id,
            "name": kiosk.name,
            "latitude": str(kiosk.latitude) if kiosk.latitude is not None else None,
            "longitude": str(kiosk.longitude) if kiosk.longitude is not None else None,
            "has_location_recorded": (kiosk.latitude is not None and kiosk.longitude is not None),
            "server_time": now.isoformat(),
            "heartbeat_interval": 10,
            "status": current_status,
            "sync_required": sync_required,
            "desired_content_version": kiosk.desired_content_version,
            "commands": commands
        }, status=status.HTTP_200_OK)



