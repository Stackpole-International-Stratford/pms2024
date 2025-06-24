# plant/forms.py
from django import forms
from django.utils import timezone
from ..models.tempsensor_models import HeatBreakEntry
from ..utils import get_zones

class PublicHeatBreakEntryForm(forms.ModelForm):
    zone = forms.ChoiceField(label="Zone (humidex)", choices=[])

    class Meta:
        model  = HeatBreakEntry
        fields = ['first_name', 'last_name', 'area', 'zone']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        zones = get_zones()   # [{'zone':0,'humidex':44.2},…]
        self._zone_data = { str(z['zone']): z['humidex'] for z in zones }
        self.fields['zone'].choices = [
            (zone, f"Zone {zone} (humidex {humidex})")
            for zone, humidex in self._zone_data.items()
        ]

    def save(self, commit=True):
        # create but don't yet write to DB
        instance = super().save(commit=False)
        instance.timestamp = timezone.now()

        # look up humidex for the selected zone
        sel = self.cleaned_data.get('zone')
        if sel in self._zone_data:
            instance.humidex = self._zone_data[sel]

        if commit:
            instance.save()
        return instance