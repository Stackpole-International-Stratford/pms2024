# dashboards/admin.py

from django.contrib import admin
from .models import HourlyProductionReportRecipient
from .models import PagesConfig
import json
from django import forms
from django.db.models import JSONField

@admin.register(HourlyProductionReportRecipient)
class HourlyProductionReportRecipientAdmin(admin.ModelAdmin):
    list_display    = ('email', 'added_at')
    search_fields   = ('email',)
    ordering        = ('-added_at',)




class PrettyJSONWidget(forms.Textarea):
    def format_value(self, value):
        if value is None:
            return ""
        try:
            return json.dumps(value, indent=2, sort_keys=True)
        except (TypeError, ValueError):
            return super().format_value(value)

@admin.register(PagesConfig)
class PagesConfigAdmin(admin.ModelAdmin):
    list_display = ("name",)
    formfield_overrides = {
        JSONField: {
            "widget": PrettyJSONWidget(
                attrs={
                    "style": (
                      "font-family: monospace; "
                      "width: 100%; height: 600px; white-space: pre;"
                    )
                }
            )
        },
    }


