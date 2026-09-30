from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()

class CMSAuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="Password123!"
        )

    def test_cms_session_signin_success(self):
        url = "/"
        payload = {
            "username": "admin",
            "password": "Password123!"
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)  # Redirects to admin_dashboard

    def test_cms_jwt_login_api_success(self):
        url = "/api/cms/auth/login/"
        payload = {
            "username": "admin",
            "password": "Password123!"
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["role"], "super_admin")

    def test_cms_change_password_api_success(self):
        login_url = "/api/cms/auth/login/"
        payload = {
            "username": "admin",
            "password": "Password123!"
        }
        res = self.client.post(login_url, payload, format="json")
        access_token = res.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        change_url = "/api/cms/auth/change-password/"
        change_payload = {
            "old_password": "Password123!",
            "new_password": "NewSecretPassword123!"
        }
        response = self.client.post(change_url, change_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify new password login
        self.client.credentials()
        new_login_res = self.client.post(login_url, {"username": "admin", "password": "NewSecretPassword123!"}, format="json")
        self.assertEqual(new_login_res.status_code, status.HTTP_200_OK)

