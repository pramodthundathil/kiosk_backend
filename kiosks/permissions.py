from rest_framework.permissions import BasePermission

class IsKioskAuthenticated(BasePermission):
    """
    Allows access only to authenticated Kiosk Devices possessing a valid Kiosk JWT.
    Rejects requests from unauthenticated callers and normal CMS User tokens.
    """
    def has_permission(self, request, view):
        kiosk = getattr(request, 'kiosk', None)
        if not kiosk:
            return False
        
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_kiosk_device', False):
            return False

        if not kiosk.is_active or kiosk.status == 'DISABLED':
            return False

        return True
