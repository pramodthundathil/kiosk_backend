from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.db.models import Q
from kiosks.authentication import KioskJWTAuthentication
from kiosks.models import KioskDevice, AppRelease
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
            kiosk.app_version = str(data['app_version']).strip()

        if 'app_version_code' in data and data['app_version_code'] is not None:
            try:
                kiosk.current_app_version_code = int(data['app_version_code'])
            except (ValueError, TypeError):
                pass

        # Reconcile OTA update status with active published releases
        latest_rel = AppRelease.objects.filter(is_active=True, is_published=True).order_by('-version_code').first()
        if latest_rel:
            current_code = kiosk.current_app_version_code or 1
            if current_code >= latest_rel.version_code:
                kiosk.update_status = KioskDevice.UpdateStatus.UP_TO_DATE
                kiosk.pending_update_release = None
                kiosk.force_update_requested = False
                kiosk.update_error = None
            else:
                if kiosk.update_status == KioskDevice.UpdateStatus.UP_TO_DATE:
                    kiosk.update_status = KioskDevice.UpdateStatus.UPDATE_AVAILABLE
                    kiosk.pending_update_release = latest_rel
                elif kiosk.update_status in [KioskDevice.UpdateStatus.DOWNLOADING, KioskDevice.UpdateStatus.INSTALLING]:
                    # If stuck in DOWNLOADING or INSTALLING for more than 15 minutes, mark as failed/timeout
                    if not kiosk.update_started_at or (now - kiosk.update_started_at).total_seconds() > 900:
                        kiosk.update_status = KioskDevice.UpdateStatus.FAILED
                        kiosk.update_error = "Installation timed out or was interrupted"

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
        prev_content_ver = kiosk.current_content_version
        if 'current_content_version' in data and data['current_content_version']:
            kiosk.current_content_version = str(data['current_content_version']).strip()
            # If kiosk has synchronized to desired_content_version, mark last_sync_at
            if kiosk.current_content_version == kiosk.desired_content_version:
                if prev_content_ver != kiosk.desired_content_version or not kiosk.last_sync_at:
                    kiosk.last_sync_at = now
                    KioskEvent.objects.create(
                        kiosk=kiosk,
                        event_type=KioskEvent.EventType.SYNC_COMPLETED,
                        severity=KioskEvent.Severity.INFO,
                        message=f"Terminal synchronized successfully to content version v{kiosk.current_content_version}.",
                        metadata={"content_version": kiosk.current_content_version}
                    )

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

        # Commands for device execution
        commands = []
        if sync_required:
            commands.append({
                "command": "SYNC_CONTENT",
                "target_version": kiosk.desired_content_version
            })

        # Check remote app update commands
        if kiosk.force_update_requested:
            commands.append({
                "command": "FORCE_APP_UPDATE"
            })
            kiosk.force_update_requested = False
            kiosk.save(update_fields=['force_update_requested'])
        elif kiosk.check_update_requested:
            commands.append({
                "command": "CHECK_APP_UPDATE"
            })
            kiosk.check_update_requested = False
            kiosk.save(update_fields=['check_update_requested'])


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
            "current_content_version": kiosk.current_content_version,
            "commands": commands
        }, status=status.HTTP_200_OK)


class KioskSyncCompleteView(views.APIView):
    """
    POST /api/kiosk/sync-complete/
    Receives notification when a kiosk finishes downloading and updating its local catalog,
    screensavers, and categories.
    Payload:
      - device_id or mac_address
      - content_version (string)
      - status (e.g. 'SUCCESS' or 'FAILED')
      - synced_items (dict: e.g. {"products": 5, "screensavers": 4, "categories": 3})
      - error (optional error message if failed)
    """
    authentication_classes = [KioskJWTAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data or {}
        kiosk = getattr(request, 'kiosk', None)

        if not kiosk:
            mac = (
                data.get('device_id') or
                data.get('mac_address') or
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
                {"error": "Kiosk not recognized."},
                status=status.HTTP_404_NOT_FOUND
            )

        sync_status = data.get('status', 'SUCCESS').upper()
        content_version = str(data.get('content_version', kiosk.desired_content_version)).strip()
        synced_items = data.get('synced_items', {})
        now = timezone.now()

        if sync_status == 'SUCCESS':
            kiosk.current_content_version = content_version
            kiosk.last_sync_at = now
            kiosk.save(update_fields=['current_content_version', 'last_sync_at', 'updated_at'])

            prod_count = synced_items.get('products', kiosk.assigned_products.count())
            ss_count = synced_items.get('screensavers', 0)
            msg = f"Kiosk content synchronization completed (v{content_version}). Synced {prod_count} assigned products and {ss_count} screensavers."

            KioskEvent.objects.create(
                kiosk=kiosk,
                event_type=KioskEvent.EventType.SYNC_COMPLETED,
                severity=KioskEvent.Severity.INFO,
                message=msg,
                metadata={
                    "content_version": content_version,
                    "synced_items": synced_items
                }
            )
            return Response({
                "success": True,
                "message": msg,
                "current_content_version": kiosk.current_content_version,
                "last_sync_at": kiosk.last_sync_at.isoformat()
            }, status=status.HTTP_200_OK)
        else:
            err_msg = data.get('error', 'Unknown synchronization error')
            KioskEvent.objects.create(
                kiosk=kiosk,
                event_type=KioskEvent.EventType.SYNC_FAILED,
                severity=KioskEvent.Severity.WARNING,
                message=f"Kiosk content sync failed for v{content_version}: {err_msg}",
                metadata={"error": err_msg, "content_version": content_version}
            )
            return Response({
                "success": False,
                "error": err_msg
            }, status=status.HTTP_400_BAD_REQUEST)



