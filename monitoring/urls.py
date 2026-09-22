from django.urls import path
from .views import KioskHeartbeatView, KioskSyncCompleteView
from .analytics_views import KioskAnalyticsIngestionView

urlpatterns = [
    path("heartbeat/", KioskHeartbeatView.as_view(), name="kiosk_heartbeat"),
    path("sync-complete/", KioskSyncCompleteView.as_view(), name="kiosk_sync_complete"),
    path("analytics/events/", KioskAnalyticsIngestionView.as_view(), name="kiosk_analytics_events"),
]

