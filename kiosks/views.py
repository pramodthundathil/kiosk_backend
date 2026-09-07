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
            kiosk = KioskDevice.objects.select_related('store', 'profile', 'credential').get(device_id=device_id)
        except KioskDevice.DoesNotExist:
            return Response(
                {"error": "Invalid device_id or credential."},
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


class KioskDeviceSelfView(views.APIView):
    """
    GET /api/kiosk/device/
    Returns device profile and information for the authenticated kiosk.
    """
    authentication_classes = [KioskJWTAuthentication]
    permission_classes = [IsKioskAuthenticated]

    def get(self, request):
        serializer = KioskDeviceSerializer(request.kiosk)
        return Response(serializer.data, status=status.HTTP_200_OK)
