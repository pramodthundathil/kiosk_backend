from django.urls import path
from .views import (
    KioskAuthLoginView, 
    KioskDeviceSelfView, 
    ScreensaverListAPIView,
    AppUpdateCheckView,
    AppUpdateStatusView
)
from products.views import ProductListAPIView

urlpatterns = [
    path("auth/login/", KioskAuthLoginView.as_view(), name="kiosk_auth_login"),
    path("device/", KioskDeviceSelfView.as_view(), name="kiosk_device_self"),
    path("products/", ProductListAPIView.as_view(), name="kiosk_products_api"),
    path("screensavers/", ScreensaverListAPIView.as_view(), name="kiosk_screensavers_api"),
    path("app-update/", AppUpdateCheckView.as_view(), name="kiosk_app_update_check"),
    path("app-update/status/", AppUpdateStatusView.as_view(), name="kiosk_app_update_status"),
]


