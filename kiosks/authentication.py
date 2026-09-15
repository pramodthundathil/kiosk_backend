from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.utils import timezone
from .models import KioskDevice

class KioskDeviceWrapper:
    """
    Wrapper class attached to request.user when authenticated as a Kiosk Device.
    Ensures compatibility with DRF request context while clearly marking as a Kiosk.
    """
    def __init__(self, kiosk: KioskDevice):
        self.kiosk = kiosk
        self.is_authenticated = True
        self.is_kiosk_device = True

    def __str__(self):
        return f"KioskDeviceWrapper({self.kiosk.device_id})"


class KioskJWTAuthentication(BaseAuthentication):
    """
    Custom DRF Authentication class for Kiosk Android Application requests.
    Validates Kiosk JWT tokens containing claim token_type='kiosk'.
    """
    def authenticate(self, request):
        header = request.headers.get("Authorization")
        if not header or not header.startswith("Bearer "):
            return None

        raw_token = header.split(" ")[1]
        try:
            token = AccessToken(raw_token)
        except (TokenError, InvalidToken):
            return None

        # Enforce that token is specifically a Kiosk device token
        if token.get("token_category") != "kiosk":
            return None


        kiosk_id = token.get("kiosk_id")
        device_id = token.get("device_id")

        if not kiosk_id or not device_id:
            raise AuthenticationFailed("Invalid token payload: missing kiosk identification claims.")

        try:
            kiosk = KioskDevice.objects.select_related("store", "profile", "credential").get(
                id=kiosk_id,
                device_id=device_id
            )
        except KioskDevice.DoesNotExist:
            raise AuthenticationFailed("Kiosk device not found.")

        if not kiosk.is_active:
            raise AuthenticationFailed("This kiosk device is inactive.")

        if kiosk.status == KioskDevice.Status.DISABLED:
            raise AuthenticationFailed("This kiosk device has been disabled by an administrator.")

        if hasattr(kiosk, "credential") and kiosk.credential.revoked_at is not None:
            raise AuthenticationFailed("This kiosk device credential has been revoked.")

        request.kiosk = kiosk
        return (KioskDeviceWrapper(kiosk), raw_token)
