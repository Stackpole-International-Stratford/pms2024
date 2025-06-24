# plant/forms.py
from django import forms
from django.utils import timezone
from ..models.tempsensor_models import HeatBreakEntry
from ..utils import get_zones

class PublicHeatBreakEntryForm(forms.ModelForm):
    zone = forms.ChoiceField(label="Zone (humidex)", choices=[])
    class Meta:
        model = HeatBreakEntry
        fields = ['first_name', 'last_name', 'area', 'zone']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # dynamically load zones + humidex
        zones = get_zones()   # [{'zone':0,'humidex':44.2},…]
        self.fields['zone'].choices = [
            (str(z['zone']), f"Zone {z['zone']} (humidex {z['humidex']})")
            for z in zones
        ]

    def save(self, commit=True):
        # set the “left” timestamp at save-time
        instance = super().save(commit=False)
        instance.timestamp = timezone.now()
        if commit:
            instance.save()
        return instance
