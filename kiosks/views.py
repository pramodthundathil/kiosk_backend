from django.db.models import Q
from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from .models import KioskDevice, KioskCredential
from .serializers import KioskLoginSerializer, KioskDeviceSerializer
from .services import issue_kiosk_jwt_tokens
from .authentication import KioskJWTAuthentication
from .permissions import IsKioskAuthenticated

class KioskAuthLoginView(views.APIView):
    """
    POST /api/kiosk/auth/login/
    Authenticates a physical Android Kiosk device using device_id and device_secret.
    Returns Kiosk-specific JWT access & refresh tokens.
    """
    permission_classes = [AllowAny]
    serializer_class = KioskLoginSerializer

    def post(self, request):
        serializer = KioskLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        device_id = serializer.validated_data['device_id']
        device_secret = serializer.validated_data['device_secret']

        try:
            kiosk = KioskDevice.objects.select_related('store', 'profile', 'credential').get(
                Q(device_id__iexact=device_id) | Q(serial_number__iexact=device_id)
            )
        except KioskDevice.DoesNotExist:
            return Response(
                {"error": "Invalid MAC address / Device ID or credential."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not kiosk.is_active:
            return Response(
                {"error": "This kiosk device is inactive."},
                status=status.HTTP_403_FORBIDDEN
            )

        if kiosk.status == KioskDevice.Status.DISABLED:
            return Response(
                {"error": "This kiosk device has been disabled by an administrator."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not hasattr(kiosk, 'credential') or not kiosk.credential.check_secret(device_secret):
            return Response(
                {"error": "Invalid device_id or secret."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Update last used timestamp
        kiosk.credential.last_used_at = timezone.now()
        kiosk.credential.save(update_fields=['last_used_at'])

        # Generate JWT tokens
        tokens = issue_kiosk_jwt_tokens(kiosk)
        return Response(tokens, status=status.HTTP_200_OK)


from django.db.models import Q
from content.models import Screensaver
from .serializers import KioskLoginSerializer, KioskDeviceSerializer, ScreensaverSerializer

class KioskDeviceSelfView(views.APIView):
    """
    GET /api/kiosk/device/
    Returns device profile and information for the authenticated kiosk.
    """
    authentication_classes = [KioskJWTAuthentication]
    permission_classes = [IsKioskAuthenticated]

    def get(self, request):
        serializer = KioskDeviceSerializer(request.kiosk, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class ScreensaverListAPIView(views.APIView):
    """
    GET /api/kiosk/screensavers/
    Returns list of active screensavers.
    Optional query parameters:
      - orientation: LANDSCAPE, PORTRAIT, or BOTH
      - profile_id: Filter by Kiosk Profile UUID
      - device_id: Filter by Kiosk Device ID
    """
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Screensaver.objects.filter(is_active=True)

        orientation = request.query_params.get('orientation', '').upper()
        if orientation in ['LANDSCAPE', 'PORTRAIT']:
            qs = qs.filter(Q(orientation=orientation) | Q(orientation='BOTH'))

        profile_id = request.query_params.get('profile_id')
        if profile_id:
            qs = qs.filter(Q(kiosk_profile_id=profile_id) | Q(kiosk_profile__isnull=True))

        device_id = request.query_params.get('device_id')
        if device_id:
            try:
                device = KioskDevice.objects.get(device_id=device_id)
                if device.profile:
                    qs = qs.filter(Q(kiosk_profile=device.profile) | Q(kiosk_profile__isnull=True))
            except KioskDevice.DoesNotExist:
                pass

        qs = qs.order_by('display_order', '-created_at')
        serializer = ScreensaverSerializer(qs, many=True, context={'request': request})
        return Response({
            'count': qs.count(),
            'screensavers': serializer.data
        }, status=status.HTTP_200_OK)


import hashlib
from .models import AppRelease, KioskUpdateLog
from .serializers import AppUpdateCheckResponseSerializer, AppUpdateStatusReportSerializer
from monitoring.models import KioskEvent

class AppUpdateCheckView(views.APIView):
    """
    GET /api/kiosk/app-update/
    Checks whether a newer published APK release is available for the requesting kiosk terminal.
    Supports JWT authentication as well as dynamic IP hardware identification via MAC / Device ID headers.
    Enforces selective kiosk targeting and deterministic staged rollout percentages.
    """
    authentication_classes = [KioskJWTAuthentication]
    permission_classes = [AllowAny]

    def get(self, request):
        kiosk = getattr(request, 'kiosk', None)
        device_id = (
            request.query_params.get('device_id') or
            request.query_params.get('mac_address') or
            request.headers.get('X-Device-Id') or
            request.headers.get('X-Device-MAC')
        )

        if not kiosk and device_id:
            clean_id = device_id.strip()
            kiosk = KioskDevice.objects.filter(
                Q(device_id__iexact=clean_id) | Q(serial_number__iexact=clean_id) | Q(name__iexact=clean_id)
            ).first()

        now = timezone.now()

        # Extract current version code reported by client query params or device record
        client_version_code_raw = (
            request.query_params.get('version_code') or 
            request.query_params.get('current_version_code')
        )
        client_version_name_raw = request.query_params.get('version_name')

        client_version_code = None
        if client_version_code_raw is not None:
            try:
                client_version_code = int(client_version_code_raw)
            except (ValueError, TypeError):
                pass

        if kiosk:
            kiosk.last_update_check = now
            if client_version_code is not None:
                kiosk.current_app_version_code = client_version_code
            else:
                client_version_code = kiosk.current_app_version_code

            if client_version_name_raw:
                kiosk.app_version = client_version_name_raw.strip()

            kiosk.check_update_requested = False
            kiosk.force_update_requested = False
            kiosk.save(update_fields=[
                'last_update_check', 
                'current_app_version_code', 
                'app_version', 
                'check_update_requested',
                'force_update_requested'
            ])
        else:
            if client_version_code is None:
                client_version_code = 1

        # Query all active and published releases ordered from highest to lowest version_code
        releases_qs = AppRelease.objects.filter(is_active=True, is_published=True).prefetch_related('target_kiosks').order_by('-version_code')

        matching_release = None
        for rel in releases_qs:
            # 1. Target device type check
            if rel.target_device_type != AppRelease.DeviceType.ALL and kiosk:
                if rel.target_device_type == AppRelease.DeviceType.ANDROID_TV:
                    if kiosk.android_version and 'tv' not in kiosk.android_version.lower() and 'android' not in (kiosk.device_model or '').lower():
                        continue

            # 2. Selective kiosk targeting
            if rel.target_kiosks.exists():
                if not kiosk or not rel.target_kiosks.filter(id=kiosk.id).exists():
                    continue

            # 3. Minimum supported version check
            if rel.minimum_supported_version and client_version_code < rel.minimum_supported_version:
                continue

            # 4. Staged rollout check (deterministic hash bucket per device_id)
            if rel.staged_rollout_percentage < 100:
                seed = (kiosk.device_id if kiosk else (device_id or "default")).lower().strip()
                bucket = int(hashlib.md5(seed.encode('utf-8')).hexdigest(), 16) % 100
                if bucket >= rel.staged_rollout_percentage:
                    continue

            matching_release = rel
            break

        # Check if matching release is newer than current installed version
        if matching_release and matching_release.version_code > client_version_code:
            if kiosk:
                kiosk.update_status = KioskDevice.UpdateStatus.UPDATE_AVAILABLE
                kiosk.pending_update_release = matching_release
                kiosk.save(update_fields=['update_status', 'pending_update_release'])

            download_url = matching_release.get_effective_apk_url(request)
            return Response({
                "update_available": True,
                "latest_version_name": matching_release.version_name,
                "latest_version_code": matching_release.version_code,
                "current_version_code": client_version_code,
                "mandatory": matching_release.is_mandatory,
                "release_title": matching_release.release_title,
                "release_notes": matching_release.get_release_notes_list(),
                "apk_url": download_url,
                "apk_size": matching_release.apk_file_size or 0,
                "sha256": matching_release.checksum_sha256 or ""
            }, status=status.HTTP_200_OK)

        # Already up to date
        if kiosk:
            kiosk.update_status = KioskDevice.UpdateStatus.UP_TO_DATE
            kiosk.pending_update_release = None
            kiosk.force_update_requested = False
            kiosk.update_error = None
            kiosk.save(update_fields=['update_status', 'pending_update_release', 'force_update_requested', 'update_error'])

        return Response({
            "update_available": False,
            "latest_version_code": matching_release.version_code if matching_release else client_version_code,
            "current_version_code": client_version_code
        }, status=status.HTTP_200_OK)


class AppUpdateStatusView(views.APIView):
    """
    POST /api/kiosk/app-update/status/
    Receives update lifecycle transition reports from the Kiosk application:
    (DOWNLOADING, INSTALLING, UPDATED, FAILED).
    Updates KioskDevice state, logs audit entry in KioskUpdateLog, and broadcasts telemetry event.
    """
    authentication_classes = [KioskJWTAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AppUpdateStatusReportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        kiosk = getattr(request, 'kiosk', None)

        device_id = data.get('device_id') or data.get('mac_address') or request.headers.get('X-Device-Id')
        if not kiosk and device_id:
            clean_id = device_id.strip()
            kiosk = KioskDevice.objects.filter(
                Q(device_id__iexact=clean_id) | Q(serial_number__iexact=clean_id) | Q(name__iexact=clean_id)
            ).first()

        if not kiosk:
            return Response(
                {"error": "Kiosk device not recognized. Please provide a registered device_id or valid token."},
                status=status.HTTP_404_NOT_FOUND
            )

        new_status = data['status']
        version_name = data['version_name']
        version_code = data['version_code']
        message = data.get('message', '').strip()
        now = timezone.now()

        prev_version_code = kiosk.current_app_version_code
        kiosk.update_status = new_status

        if new_status == KioskDevice.UpdateStatus.DOWNLOADING:
            kiosk.update_started_at = now
            kiosk.update_error = None
        elif new_status == KioskDevice.UpdateStatus.INSTALLING:
            pass
        elif new_status == KioskDevice.UpdateStatus.UPDATED:
            kiosk.update_completed_at = now
            kiosk.app_version = str(version_name).strip()
            kiosk.current_app_version_code = version_code
            kiosk.force_update_requested = False
            kiosk.pending_update_release = None
            kiosk.update_status = KioskDevice.UpdateStatus.UP_TO_DATE
            kiosk.update_error = None
        elif new_status == KioskDevice.UpdateStatus.FAILED:
            kiosk.update_error = message or "Update failed"
            kiosk.force_update_requested = False
            kiosk.pending_update_release = None

        kiosk.save()

        # Audit log entry
        KioskUpdateLog.objects.create(
            kiosk=kiosk,
            release=kiosk.pending_update_release,
            from_version_code=prev_version_code,
            to_version_code=version_code,
            status=new_status,
            message=message
        )

        # Telemetry stream event
        severity = (
            KioskEvent.Severity.ERROR if new_status == KioskDevice.UpdateStatus.FAILED else
            KioskEvent.Severity.INFO
        )
        KioskEvent.objects.create(
            kiosk=kiosk,
            event_type=KioskEvent.EventType.APP_UPDATE,
            severity=severity,
            message=f"App Update state [{new_status}]: v{version_name} ({version_code}). {message}".strip(),
            metadata={
                "version_name": version_name,
                "version_code": version_code,
                "status": new_status,
                "error": kiosk.update_error
            }
        )

        return Response({
            "success": True,
            "device_id": kiosk.device_id,
            "status": kiosk.update_status,
            "version_name": kiosk.app_version,
            "version_code": kiosk.current_app_version_code
        }, status=status.HTTP_200_OK)


