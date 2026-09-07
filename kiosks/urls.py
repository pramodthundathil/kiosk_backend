from django.urls import path
from .views import KioskAuthLoginView, KioskDeviceSelfView

urlpatterns = [
    path("auth/login/", KioskAuthLoginView.as_view(), name="kiosk_auth_login"),
    path("device/", KioskDeviceSelfView.as_view(), name="kiosk_device_self"),
]
