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

    def test_kiosk_assigned_products_many_to_many(self):
        from products.models import Product
        p1 = Product.objects.create(name="Copper Bonded Rod", sku="CBR-001", price=1200.00)
        p2 = Product.objects.create(name="Chemical Earthing Compound", sku="CEC-002", price=450.00)

        # Assign products to kiosk
        self.kiosk.assigned_products.add(p1, p2)
        self.assertEqual(self.kiosk.assigned_products.count(), 2)

        # Check reverse relation from Product
        self.assertIn(self.kiosk, p1.assigned_kiosks.all())
        self.assertIn(self.kiosk, p2.assigned_kiosks.all())


from kiosks.models import AppRelease, KioskUpdateLog
from django.core.files.uploadedfile import SimpleUploadedFile
import zipfile
import io

def create_dummy_apk_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('AndroidManifest.xml', b'<manifest package="com.kiosk.app"/>')
        zf.writestr('classes.dex', b'dex\n035\x00')
    return buf.getvalue()

class AppUpdateSystemTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.store = Store.objects.create(name="Pune Store", code="PUN01", city="Pune")
        self.profile = KioskProfile.objects.create(name="Standard", code="STD")
        self.kiosk, self.secret = register_kiosk_device(
            name="Pune Kiosk 1",
            device_id="KIOSK-PUN-001",
            store=self.store,
            profile=self.profile
        )
        self.kiosk.current_app_version_code = 101
        self.kiosk.app_version = "1.0.1"
        self.kiosk.save()

        # Login to get JWT
        login_res = self.client.post("/api/kiosk/auth/login/", {
            "device_id": "KIOSK-PUN-001",
            "device_secret": self.secret
        }, format="json")
        self.token = login_res.data["access"]
        self.auth_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def test_app_update_check_when_no_releases(self):
        res = self.client.get(
            "/api/kiosk/app-update/",
            {"device_id": "KIOSK-PUN-001", "version_code": 101},
            **self.auth_headers
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["update_available"])
        self.assertEqual(res.data["current_version_code"], 101)

    def test_app_update_check_detects_published_release(self):
        apk_content = create_dummy_apk_bytes()
        dummy_file = SimpleUploadedFile("kiosk-1.0.5.apk", apk_content, content_type="application/vnd.android.package-archive")

        release = AppRelease.objects.create(
            version_name="1.0.5",
            version_code=105,
            release_title="Major Performance Boost",
            release_notes="• Faster loading\n• Bug fixes",
            apk_file=dummy_file,
            is_mandatory=True,
            is_published=True
        )

        res = self.client.get(
            "/api/kiosk/app-update/",
            {"device_id": "KIOSK-PUN-001", "version_code": 101},
            **self.auth_headers
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["update_available"])
        self.assertEqual(res.data["latest_version_name"], "1.0.5")
        self.assertEqual(res.data["latest_version_code"], 105)
        self.assertEqual(res.data["current_version_code"], 101)
        self.assertTrue(res.data["mandatory"])
        self.assertEqual(res.data["release_title"], "Major Performance Boost")
        self.assertEqual(res.data["release_notes"], ["Faster loading", "Bug fixes"])
        self.assertTrue(len(res.data["sha256"]) == 64)
        self.assertTrue(".apk" in res.data["apk_url"])
        self.assertTrue(res.data["apk_url"].startswith("http"))


    def test_selective_release_targets_only_chosen_kiosk(self):
        other_kiosk, _ = register_kiosk_device(name="Other Kiosk", device_id="KIOSK-OTHER-999")
        
        release = AppRelease.objects.create(
            version_name="1.0.6",
            version_code=106,
            release_title="Beta Test",
            apk_url="https://example.com/kiosk-1.0.6.apk",
            is_published=True
        )
        release.target_kiosks.add(other_kiosk)

        # KIOSK-PUN-001 is NOT targeted
        res = self.client.get(
            "/api/kiosk/app-update/",
            {"device_id": "KIOSK-PUN-001", "version_code": 101},
            **self.auth_headers
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["update_available"])

    def test_app_update_status_reporting_flow(self):
        # 1. Report DOWNLOADING
        res = self.client.post("/api/kiosk/app-update/status/", {
            "device_id": "KIOSK-PUN-001",
            "version_name": "1.0.5",
            "version_code": 105,
            "status": "DOWNLOADING",
            "message": "Downloading 50MB APK"
        }, format="json", **self.auth_headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.update_status, "DOWNLOADING")
        self.assertIsNotNone(self.kiosk.update_started_at)

        # 2. Report FAILED
        res = self.client.post("/api/kiosk/app-update/status/", {
            "device_id": "KIOSK-PUN-001",
            "version_name": "1.0.5",
            "version_code": 105,
            "status": "FAILED",
            "message": "APK checksum verification failed"
        }, format="json", **self.auth_headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.update_status, "FAILED")
        self.assertEqual(self.kiosk.update_error, "APK checksum verification failed")

        # 3. Report UPDATED
        res = self.client.post("/api/kiosk/app-update/status/", {
            "device_id": "KIOSK-PUN-001",
            "version_name": "1.0.5",
            "version_code": 105,
            "status": "UPDATED",
            "message": "App upgraded and restarted successfully"
        }, format="json", **self.auth_headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.update_status, "UP_TO_DATE")
        self.assertEqual(self.kiosk.app_version, "1.0.5")
        self.assertEqual(self.kiosk.current_app_version_code, 105)
        self.assertIsNone(self.kiosk.update_error)

        # Verify audit logs created
        logs = KioskUpdateLog.objects.filter(kiosk=self.kiosk)
        self.assertEqual(logs.count(), 3)

    def test_heartbeat_dispatches_app_update_commands(self):
        # Request check_update
        self.kiosk.check_update_requested = True
        self.kiosk.save()

        hb_res = self.client.post("/api/kiosk/heartbeat/", {
            "device_id": "KIOSK-PUN-001",
            "app_version": "1.0.1",
            "app_version_code": 101
        }, format="json", **self.auth_headers)
        self.assertEqual(hb_res.status_code, status.HTTP_200_OK)
        commands = hb_res.data.get("commands", [])
        self.assertTrue(any(c.get("command") == "CHECK_APP_UPDATE" for c in commands))

        # Request force_update
        self.kiosk.force_update_requested = True
        self.kiosk.save()

        hb_res = self.client.post("/api/kiosk/heartbeat/", {
            "device_id": "KIOSK-PUN-001"
        }, format="json", **self.auth_headers)
        commands = hb_res.data.get("commands", [])
        self.assertTrue(any(c.get("command") == "FORCE_APP_UPDATE" for c in commands))


