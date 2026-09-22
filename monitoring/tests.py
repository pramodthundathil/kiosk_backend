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

        # Online (<= 15s)
        self.kiosk.last_heartbeat_at = now - timedelta(seconds=5)
        self.assertEqual(calculate_kiosk_status(self.kiosk), KioskDevice.Status.ONLINE)

        # Warning (16s to 25s)
        self.kiosk.last_heartbeat_at = now - timedelta(seconds=20)
        self.assertEqual(calculate_kiosk_status(self.kiosk), KioskDevice.Status.WARNING)

        # Offline (> 25s)
        self.kiosk.last_heartbeat_at = now - timedelta(seconds=35)
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
        self.assertEqual(response.data["heartbeat_interval"], 10)

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

        # Set heartbeat > 25s (OFFLINE transition)
        self.kiosk.last_heartbeat_at = now - timedelta(seconds=35)
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

    def test_sync_trigger_and_sync_complete_api(self):
        # 1. Admin bumps desired_content_version
        self.kiosk.desired_content_version = "2"
        self.kiosk.current_content_version = "1"
        self.kiosk.save()

        # 2. Kiosk sends heartbeat with current_content_version "1"
        hb_url = "/api/kiosk/heartbeat/"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        response = self.client.post(hb_url, {"current_content_version": "1"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["sync_required"])
        self.assertEqual(response.data["desired_content_version"], "2")
        self.assertTrue(any(c.get("command") == "SYNC_CONTENT" for c in response.data.get("commands", [])))

        # 3. Kiosk finishes download and calls /api/kiosk/sync-complete/
        complete_url = "/api/kiosk/sync-complete/"
        complete_payload = {
            "device_id": self.kiosk.device_id,
            "content_version": "2",
            "status": "SUCCESS",
            "synced_items": {"products": 3, "screensavers": 4, "categories": 2}
        }
        res_complete = self.client.post(complete_url, complete_payload, format="json")
        self.assertEqual(res_complete.status_code, status.HTTP_200_OK)
        self.assertTrue(res_complete.data["success"])

        # 4. Verify kiosk DB state
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.current_content_version, "2")
        self.assertIsNotNone(self.kiosk.last_sync_at)

        # 5. Verify KioskEvent SYNC_COMPLETED logged
        sync_events = KioskEvent.objects.filter(kiosk=self.kiosk, event_type=KioskEvent.EventType.SYNC_COMPLETED)
        self.assertTrue(sync_events.exists())
