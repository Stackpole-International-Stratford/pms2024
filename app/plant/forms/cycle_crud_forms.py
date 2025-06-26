from django import forms
from ..models.setupfor_models import Asset, Part

class AssetCycleTimeForm(forms.Form):
    """
    Form for recording the cycle time of a part on a specific asset at a given datetime.

    Fields
    ------
    asset : ModelChoiceField
        Dropdown of Asset instances; selects the asset being measured.
    part : ModelChoiceField
        Dropdown of Part instances; selects the part whose cycle time is recorded.
    cycle_time : FloatField
        The measured cycle time in seconds; must be non-negative.
    datetime : DateTimeField
        The effective date and time for this cycle time, rendered as an HTML
        `<input type="datetime-local">`.

    Usage
    -----
    - Render in a template to allow users to submit new cycle time entries.
    - On valid submission, convert `datetime` to an epoch timestamp for storage.
    """
    asset = forms.ModelChoiceField(queryset=Asset.objects.all(), label="Select Asset")
    part = forms.ModelChoiceField(queryset=Part.objects.all(), label="Select Part")
    cycle_time = forms.FloatField(label="Cycle Time", min_value=0)
    datetime = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}), label="Date & Time")
