# dashboards/admin.py

from django.contrib import admin
from .models import HourlyProductionReportRecipient

@admin.register(HourlyProductionReportRecipient)
class HourlyProductionReportRecipientAdmin(admin.ModelAdmin):
    list_display    = ('email', 'added_at')
    search_fields   = ('email',)
    ordering        = ('-added_at',)
