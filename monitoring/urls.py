from django.urls import path
from .views import KioskHeartbeatView

urlpatterns = [
    path("heartbeat/", KioskHeartbeatView.as_view(), name="kiosk_heartbeat"),
]
