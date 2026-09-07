from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from stores.models import Store
from kiosks.models import KioskProfile, KioskDevice, KioskCredential
from kiosks.services import register_kiosk_device, issue_kiosk_jwt_tokens

class KioskAuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.store = Store.objects.create(
            name="Mumbai Main Store",
            code="MUM001",
            city="Mumbai"
        )
        self.profile = KioskProfile.objects.create(
            name="Standard Profile",
            code="STANDARD"
        )
        self.kiosk, self.secret = register_kiosk_device(
            name="Entrance Kiosk 1",
            device_id="DEV-MUM-001",
            store=self.store,
            profile=self.profile
        )

    def test_kiosk_registration_creates_hashed_credential(self):
        self.assertIsNotNone(self.kiosk.id)
        self.assertTrue(hasattr(self.kiosk, 'credential'))
        self.assertTrue(self.kiosk.credential.check_secret(self.secret))
        self.assertFalse(self.kiosk.credential.check_secret("wrong_secret"))

    def test_kiosk_login_success(self):
        url = "/api/kiosk/auth/login/"
        payload = {
            "device_id": "DEV-MUM-001",
            "device_secret": self.secret
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["device_id"], "DEV-MUM-001")
        self.assertEqual(response.data["kiosk_type"], "STANDARD")

    def test_kiosk_login_invalid_secret(self):
        url = "/api/kiosk/auth/login/"
        payload = {
            "device_id": "DEV-MUM-001",
            "device_secret": "invalid_secret_123"
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_kiosk_login_disabled_kiosk(self):
        self.kiosk.status = KioskDevice.Status.DISABLED
        self.kiosk.save()

        url = "/api/kiosk/auth/login/"
        payload = {
            "device_id": "DEV-MUM-001",
            "device_secret": self.secret
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_kiosk_authenticated_endpoint_access(self):
        # Obtain token
        tokens = issue_kiosk_jwt_tokens(self.kiosk)
        token = tokens["access"]

        url = "/api/kiosk/device/"
        # Without header
        unauth_response = self.client.get(url)
        self.assertIn(unauth_response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


        # With valid Kiosk Bearer Token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        auth_response = self.client.get(url)
        self.assertEqual(auth_response.status_code, status.HTTP_200_OK)
        self.assertEqual(auth_response.data["device_id"], "DEV-MUM-001")
        self.assertEqual(auth_response.data["name"], "Entrance Kiosk 1")

    def test_kiosk_registration_optional_store_coordinates_and_deployment(self):
        kiosk, secret = register_kiosk_device(
            name="Standalone Kiosk",
            device_id="DEV-STANDALONE-002",
            store=None,  # Store is optional
            profile=self.profile,
            custom_secret="CustomSuperSecret123!",
            latitude=12.971598,
            longitude=77.594566,
            is_deployed=True
        )
        self.assertIsNone(kiosk.store)
        self.assertEqual(secret, "CustomSuperSecret123!")
        self.assertTrue(kiosk.credential.check_secret("CustomSuperSecret123!"))
        self.assertEqual(float(kiosk.latitude), 12.971598)
        self.assertEqual(float(kiosk.longitude), 77.594566)
        self.assertTrue(kiosk.is_deployed)
        self.assertIsNotNone(kiosk.deployed_at)

    def test_kiosk_registration_with_hardware_specifications(self):
        kiosk, secret = register_kiosk_device(
            name="Hardware Test Kiosk",
            device_id="DEV-HW-003",
            manufacturer="Samsung",
            device_model="Galaxy Tab A8",
            serial_number="SN-789123",
            android_version="Android 13",
            app_version="v2.1.0",
            screen_width=1920,
            screen_height=1080
        )
        self.assertEqual(kiosk.manufacturer, "Samsung")
        self.assertEqual(kiosk.device_model, "Galaxy Tab A8")
        self.assertEqual(kiosk.serial_number, "SN-789123")
        self.assertEqual(kiosk.screen_width, 1920)

    def test_update_kiosk_credential_and_login(self):
        from kiosks.services import update_kiosk_credential
        update_kiosk_credential(self.kiosk, "NewUpdatedPassword999!")
        self.kiosk.credential.refresh_from_db()
        self.assertTrue(self.kiosk.credential.check_secret("NewUpdatedPassword999!"))
        
        # Test login with updated password
        url = "/api/kiosk/auth/login/"
        payload = {
            "device_id": "DEV-MUM-001",
            "device_secret": "NewUpdatedPassword999!"
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_custom_kiosk_profile_feature_toggles(self):
        profile = KioskProfile.objects.create(
            name="Interactive 3D Profile",
            code="3D_WHITEBOARD",
            show_products=True,
            show_3d_assets=True,
            show_whiteboard=True,
            screensaver_enabled=True,
            screensaver_timeout_seconds=180
        )
        self.assertTrue(profile.show_3d_assets)
        self.assertTrue(profile.show_whiteboard)
        self.assertEqual(profile.screensaver_timeout_seconds, 180)

