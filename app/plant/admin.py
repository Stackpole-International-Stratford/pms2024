# plant/admin.py
from django.contrib import admin
from .models.maintenance_models import *
# admin.py (or in forms.py and imported here)
from django import forms
from django.contrib import admin
from .models.tempsensor_models import HeatBreakEntry
from .utils import get_zones    # or wherever you put that util

@admin.register(DowntimeMachine)
class DowntimeMachineAdmin(admin.ModelAdmin):
    list_display   = ('line', 'operation', 'machine_number', 'is_tracked', 'created_at_UTC')
    list_filter    = ('line', 'operation', 'is_tracked')
    search_fields  = ('line', 'operation', 'machine_number')
    readonly_fields = ('created_at_UTC', 'updated_at_UTC')






class HeatBreakEntryAdminForm(forms.ModelForm):
    zone = forms.ChoiceField(label="Zone (humidex)",
        choices=[]
    )

    class Meta:
        model = HeatBreakEntry
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # populate choices fresh on each form instantiation
        zones = get_zones()  # returns [{'zone': 0, 'humidex': 44.2}, …]
        self.fields['zone'].choices = [
            (z['zone'], f"Zone {z['zone']} (humidex {z['humidex']})")
            for z in zones
        ]


@admin.register(HeatBreakEntry)
class HeatBreakEntryAdmin(admin.ModelAdmin):
    form           = HeatBreakEntryAdminForm
    list_display   = ('first_name', 'last_name', 'area', 'zone',
                      'timestamp', 'returned', 'return_timestamp')
    list_filter    = ('area', 'returned', 'zone')
    search_fields  = ('first_name', 'last_name')
    readonly_fields= ('return_timestamp',)

