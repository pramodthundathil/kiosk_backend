from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from stores.models import Store
from kiosks.models import KioskProfile, KioskDevice
from kiosks.services import register_kiosk_device, issue_kiosk_jwt_tokens
from monitoring.models import Alert, KioskEvent
from monitoring.services import calculate_kiosk_status, update_kiosk_status_and_alerts

class HeartbeatAndMonitoringTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.store = Store.objects.create(name="Cochin Store", code="COCHIN01")
        self.profile = KioskProfile.objects.create(name="Standard Profile", code="STANDARD")
        self.kiosk, self.secret = register_kiosk_device(
            name="Kiosk-101",
            device_id="DEV-101",
            store=self.store,
            profile=self.profile
        )
        self.tokens = issue_kiosk_jwt_tokens(self.kiosk)
        self.token = self.tokens["access"]

    def test_status_calculation_rules(self):
        now = timezone.now()

        # Online (<= 60s)
        self.kiosk.last_heartbeat_at = now - timedelta(seconds=20)
        self.assertEqual(calculate_kiosk_status(self.kiosk), KioskDevice.Status.ONLINE)

        # Warning (61s to 90s)
        self.kiosk.last_heartbeat_at = now - timedelta(seconds=75)
        self.assertEqual(calculate_kiosk_status(self.kiosk), KioskDevice.Status.WARNING)

        # Offline (> 90s)
        self.kiosk.last_heartbeat_at = now - timedelta(seconds=105)
        self.assertEqual(calculate_kiosk_status(self.kiosk), KioskDevice.Status.OFFLINE)

    def test_heartbeat_api_endpoint(self):
        url = "/api/kiosk/heartbeat/"
        payload = {
            "app_version": "1.2.0",
            "android_version": "14",
            "device_model": "Tab-S8",
            "battery_percentage": 92,
            "network_type": "wifi",
            "screen_on": True,
            "app_running": True,
            "current_content_version": "1"
        }
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["status"], "ONLINE")
        self.assertIn("server_time", response.data)
        self.assertEqual(response.data["heartbeat_interval"], 30)

        # Verify DB model update
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.app_version, "1.2.0")
        self.assertEqual(self.kiosk.battery_percentage, 92)
        self.assertIsNotNone(self.kiosk.last_heartbeat_at)

    def test_alert_creation_and_auto_resolution(self):
        now = timezone.now()
        # Set initial status to ONLINE
        self.kiosk.status = KioskDevice.Status.ONLINE
        self.kiosk.save()

        # Set heartbeat > 90s (OFFLINE transition)
        self.kiosk.last_heartbeat_at = now - timedelta(seconds=100)
        update_kiosk_status_and_alerts(self.kiosk)


        self.assertEqual(self.kiosk.status, KioskDevice.Status.OFFLINE)
        offline_alerts = Alert.objects.filter(kiosk=self.kiosk, alert_type=Alert.AlertType.KIOSK_OFFLINE, resolved_at__isnull=True)
        self.assertEqual(offline_alerts.count(), 1)

        # Re-trigger status check -> should deduplicate (still 1 alert)
        update_kiosk_status_and_alerts(self.kiosk)
        self.assertEqual(Alert.objects.filter(kiosk=self.kiosk, alert_type=Alert.AlertType.KIOSK_OFFLINE, resolved_at__isnull=True).count(), 1)

        # Reconnect heartbeat (ONLINE transition)
        self.kiosk.last_heartbeat_at = timezone.now()
        update_kiosk_status_and_alerts(self.kiosk)

        self.assertEqual(self.kiosk.status, KioskDevice.Status.ONLINE)
        # Verify offline alert was auto-resolved
        open_alerts = Alert.objects.filter(kiosk=self.kiosk, alert_type=Alert.AlertType.KIOSK_OFFLINE, resolved_at__isnull=True)
        self.assertEqual(open_alerts.count(), 0)
