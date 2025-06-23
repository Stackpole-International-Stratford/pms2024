# plant/admin.py
from django.contrib import admin
from .models.maintenance_models import *

@admin.register(DowntimeMachine)
class DowntimeMachineAdmin(admin.ModelAdmin):
    list_display   = ('line', 'operation', 'machine_number', 'is_tracked', 'created_at_UTC')
    list_filter    = ('line', 'operation', 'is_tracked')
    search_fields  = ('line', 'operation', 'machine_number')
    readonly_fields = ('created_at_UTC', 'updated_at_UTC')
