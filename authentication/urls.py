from django.urls import path 
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # Session authentication views for Web Portal
    path("", views.signin, name="signin"),
    path("signout", views.signout, name="signout"),

    # REST API endpoints for CMS User authentication
    path("api/cms/auth/login/", views.CMSAuthLoginView.as_view(), name="cms_auth_login"),
    path("api/cms/auth/refresh/", TokenRefreshView.as_view(), name="cms_auth_refresh"),
]