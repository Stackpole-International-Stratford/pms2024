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
    zone = forms.ChoiceField(label="Zone (humidex)", choices=[])
    humidex = forms.FloatField(
        label="Logged Humidex", required=False, disabled=True,
        help_text="Automatically filled from the selected zone"
    )

    class Meta:
        model  = HeatBreakEntry
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # pull live zone→humidex mapping
        zones = get_zones()    # e.g. [{'zone':0,'humidex':44.2},…]
        self.zone_map = { z['zone']: z['humidex'] for z in zones }

        # populate zone choices
        self.fields['zone'].choices = [
            (str(z), f"Zone {z} (humidex {self.zone_map[z]})")
            for z in sorted(self.zone_map)
        ]

        # set initial humidex based on existing instance or POSTed data
        initial_zone = None
        if self.instance and self.instance.zone is not None:
            initial_zone = self.instance.zone
        elif self.data.get('zone'):
            try:
                initial_zone = int(self.data['zone'])
            except ValueError:
                initial_zone = None

        if initial_zone in self.zone_map:
            self.fields['humidex'].initial = self.zone_map[initial_zone]

    def save(self, commit=True):
        instance = super().save(commit=False)
        # store the humidex corresponding to the chosen zone
        hz = instance.zone
        instance.humidex = self.zone_map.get(hz)
        if commit:
            instance.save()
        return instance


@admin.register(HeatBreakEntry)
class HeatBreakEntryAdmin(admin.ModelAdmin):
    form           = HeatBreakEntryAdminForm
    list_display   = (
        'first_name', 'last_name', 'area', 'zone', 'humidex',
        'timestamp', 'returned', 'return_timestamp'
    )
    list_filter    = ('area', 'returned', 'zone')
    search_fields  = ('first_name', 'last_name')
    readonly_fields= ('return_timestamp',)

