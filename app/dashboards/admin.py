# dashboards/admin.py

from django.contrib import admin
from .models import HourlyProductionReportRecipient
import json
from django import forms
from django.db.models import JSONField

@admin.register(HourlyProductionReportRecipient)
class HourlyProductionReportRecipientAdmin(admin.ModelAdmin):
    list_display    = ('email', 'added_at')
    search_fields   = ('email',)
    ordering        = ('-added_at',)


