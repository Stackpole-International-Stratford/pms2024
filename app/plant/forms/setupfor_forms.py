#forms/setupfor_forms.py
from django import forms
from ..models.setupfor_models import Asset, Part, SetupFor


class AssetForm(forms.ModelForm):
    """
    Form for creating and editing Asset records.

    Fields
    ------
    asset_number : CharField
        Unique code or identifier for the asset.
    asset_name : CharField, optional
        Human-readable name or description of the asset.
    """
    class Meta:
        model = Asset
        fields = ['asset_number', 'asset_name']


class PartForm(forms.ModelForm):
    """
    Form for creating and editing Part records.

    Fields
    ------
    part_number : CharField
        Unique code or identifier for the part.
    part_name : CharField, optional
        Human-readable name or description of the part.
    """
    class Meta:
        model = Part
        fields = ['part_number', 'part_name']

