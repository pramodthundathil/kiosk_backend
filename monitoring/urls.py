from django.urls import path
from .views import KioskHeartbeatView
from .analytics_views import KioskAnalyticsIngestionView

urlpatterns = [
    path("heartbeat/", KioskHeartbeatView.as_view(), name="kiosk_heartbeat"),
    path("analytics/events/", KioskAnalyticsIngestionView.as_view(), name="kiosk_analytics_events"),
]

