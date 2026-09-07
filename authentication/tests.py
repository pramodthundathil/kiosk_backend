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
