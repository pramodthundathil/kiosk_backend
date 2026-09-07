from django.contrib import admin
from .models import KioskEvent, Alert

@admin.register(KioskEvent)
class KioskEventAdmin(admin.ModelAdmin):
    list_display = ('kiosk', 'event_type', 'severity', 'message', 'created_at')
    list_filter = ('event_type', 'severity', 'created_at')
    search_fields = ('kiosk__device_id', 'message')
    readonly_fields = ('id', 'created_at')

@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('kiosk', 'alert_type', 'severity', 'is_resolved', 'opened_at', 'resolved_at')
    list_filter = ('alert_type', 'severity', 'resolved_at', 'opened_at')
    search_fields = ('kiosk__device_id', 'message')
    readonly_fields = ('id', 'opened_at')
