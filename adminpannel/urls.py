from django.urls import path 
from . import views 

urlpatterns = [
    path("", views.admin_dashboard, name="admin_dashboard"),
    path("dashboard/", views.admin_dashboard, name="admin_dashboard_alias"),
    path("kiosks/", views.admin_kiosks, name="admin_kiosks"),
    path("kiosks/add/", views.admin_kiosk_add, name="admin_kiosk_add"),
    path("kiosks/<uuid:kiosk_id>/", views.admin_kiosk_detail, name="admin_kiosk_detail"),
    path("kiosks/<uuid:kiosk_id>/edit/", views.admin_kiosk_edit, name="admin_kiosk_edit"),
    path("products/", views.admin_products, name="admin_products"),
    path("stores/", views.admin_stores, name="admin_stores"),
    path("users/", views.admin_users, name="admin_users"),
    path("monitoring/", views.admin_monitoring, name="admin_monitoring"),
    path("media/", views.admin_media, name="admin_media"),
]