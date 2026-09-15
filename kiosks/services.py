import secrets
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from .models import KioskDevice, KioskCredential, KioskProfile
from stores.models import Store

def generate_device_secret() -> str:
    """Generates a secure 32-character hex secret string."""
    return secrets.token_hex(16)

def register_kiosk_device(
    name: str,
    device_id: str,
    store: Store = None,
    profile: KioskProfile = None,
    custom_secret: str = None,
    latitude = None,
    longitude = None,
    is_deployed: bool = False,
    manufacturer: str = None,
    device_model: str = None,
    serial_number: str = None,
    android_version: str = None,
    app_version: str = None,
    screen_width: int = None,
    screen_height: int = None
) -> tuple[KioskDevice, str]:
    """
    Creates a new KioskDevice record and associated KioskCredential with a generated or custom secret.
    Returns (kiosk_device, raw_device_secret).
    The raw secret must be shown only once to the administrator/installer.
    """
    raw_secret = custom_secret.strip() if custom_secret and custom_secret.strip() else generate_device_secret()
    
    deployed_timestamp = timezone.now() if is_deployed else None

    kiosk = KioskDevice.objects.create(
        name=name,
        device_id=device_id,
        store=store,
        profile=profile,
        latitude=latitude if latitude != '' else None,
        longitude=longitude if longitude != '' else None,
        is_deployed=is_deployed,
        deployed_at=deployed_timestamp,
        manufacturer=manufacturer.strip() if manufacturer else None,
        device_model=device_model.strip() if device_model else None,
        serial_number=serial_number.strip() if serial_number else None,
        android_version=android_version.strip() if android_version else None,
        app_version=app_version.strip() if app_version else None,
        screen_width=screen_width if screen_width else None,
        screen_height=screen_height if screen_height else None,
        status=KioskDevice.Status.OFFLINE,
        is_active=True
    )
    
    credential = KioskCredential(kiosk=kiosk)
    credential.set_secret(raw_secret)
    credential.save()
    
    return kiosk, raw_secret


def update_kiosk_credential(kiosk: KioskDevice, new_raw_secret: str) -> KioskCredential:
    """Updates or creates the hashed credential for a kiosk device."""
    credential, _ = KioskCredential.objects.get_or_create(kiosk=kiosk)
    credential.set_secret(new_raw_secret)
    credential.revoked_at = None
    credential.save()
    return credential

def issue_kiosk_jwt_tokens(kiosk: KioskDevice) -> dict:
    """
    Generates JWT access and refresh tokens explicitly tagged with `token_category="kiosk"`
    containing kiosk device claims.
    """
    refresh = RefreshToken()
    refresh["token_category"] = "kiosk"
    refresh["device_id"] = kiosk.device_id
    refresh["kiosk_id"] = str(kiosk.id)
    refresh["store_id"] = str(kiosk.store.id) if kiosk.store else None
    refresh["profile_id"] = str(kiosk.profile.id) if kiosk.profile else None

    access = refresh.access_token
    access["token_category"] = "kiosk"
    access["device_id"] = kiosk.device_id
    access["kiosk_id"] = str(kiosk.id)
    access["store_id"] = str(kiosk.store.id) if kiosk.store else None
    access["profile_id"] = str(kiosk.profile.id) if kiosk.profile else None

    return {
        "access": str(access),
        "refresh": str(refresh),
        "kiosk_id": str(kiosk.id),
        "device_id": kiosk.device_id,
        "name": kiosk.name,
        "kiosk_type": kiosk.profile.code if kiosk.profile else "DEFAULT",
        "store_id": str(kiosk.store.id) if kiosk.store else None,
        "content_version": kiosk.current_content_version,
    }

