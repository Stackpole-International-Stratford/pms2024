#forms/setupfor_forms.py
from django import forms
from ..models.setupfor_models import Asset, Part, SetupFor


class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = ['asset_number', 'asset_name']  # Added asset_name field

class PartForm(forms.ModelForm):
    class Meta:
        model = Part
        fields = ['part_number', 'part_name']  # Added part_name field
