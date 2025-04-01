from django import forms
from ..models.setupfor_models import Asset, Part

class AssetCycleTimeForm(forms.Form):
    asset = forms.ModelChoiceField(queryset=Asset.objects.all(), label="Select Asset")
    part = forms.ModelChoiceField(queryset=Part.objects.all(), label="Select Part")
    cycle_time = forms.FloatField(label="Cycle Time", min_value=0)
    datetime = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}), label="Date & Time")
