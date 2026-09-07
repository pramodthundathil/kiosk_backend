from django.contrib import admin
from .models import Store

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'city', 'state', 'contact_person', 'contact_phone', 'is_active', 'created_at')
    list_filter = ('is_active', 'state', 'country')
    search_fields = ('name', 'code', 'city', 'contact_person')
    ordering = ('name',)
