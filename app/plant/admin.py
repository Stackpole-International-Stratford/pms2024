# plant/admin.py
from django.contrib import admin
from .models.maintenance_models import *
from .models.absentee_models import *

@admin.register(DowntimeMachine)
class DowntimeMachineAdmin(admin.ModelAdmin):
    list_display   = ('line', 'operation', 'machine_number', 'is_tracked', 'created_at_UTC')
    list_filter    = ('line', 'operation', 'is_tracked')
    search_fields  = ('line', 'operation', 'machine_number')
    readonly_fields = ('created_at_UTC', 'updated_at_UTC')


@admin.register(PayCodeGroup)
class PayCodeGroupAdmin(admin.ModelAdmin):
    list_display  = ("pay_code", "group_name", "is_scheduled")
    list_editable = ("group_name", "is_scheduled")   # inline editing from the list view
    search_fields = ("pay_code", "group_name")
    list_filter   = ("group_name", "is_scheduled")
    ordering      = ("pay_code",)

    actions = ["mark_scheduled", "mark_unscheduled"]

    @admin.action(description="Mark selected as Scheduled")
    def mark_scheduled(self, request, queryset):
        updated = queryset.update(is_scheduled=True)
        self.message_user(request, f"Updated {updated} row(s) to Scheduled.")

    @admin.action(description="Mark selected as Unscheduled")
    def mark_unscheduled(self, request, queryset):
        updated = queryset.update(is_scheduled=False)
        self.message_user(request, f"Updated {updated} row(s) to Unscheduled.")



# NEW: admin for the shift-rotation mapping table
@admin.register(ShiftRotationMap)
class ShiftRotationMapAdmin(admin.ModelAdmin):
    list_display  = ("rotation_text", "shift")
    list_editable = ("shift",)
    search_fields = ("rotation_text", "shift")
    list_filter   = ("shift",)
    ordering      = ("rotation_text",)