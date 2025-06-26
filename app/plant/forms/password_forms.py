# forms/password_forms.py
from django import forms
from ..models.password_models import Password
from ..models.setupfor_models import Asset  # Import the Asset model

class PasswordForm(forms.ModelForm):
    """
    Form for creating and editing Password records linked to assets.

    Provides fields for selecting the related asset, entering a label,
    and specifying optional username and password values.

    Fields
    ------
    password_asset : ModelChoiceField
        Dropdown selector for the associated Asset.
    label : CharField
        Human-readable label for the credential (e.g., “Admin Login”).
    username : CharField, optional
        Optional username for the credential.
    password : CharField
        Input for the secret password; rendered as a plain text field.

    Meta
    ----
    model : Password
        The Django model this form edits.
    fields : list
        Specifies the form fields to include.
    widgets : dict
        Customizes the asset selector and password input rendering.
    """
    class Meta:
        model = Password
        fields = ['password_asset', 'label', 'username', 'password']  # Updated field name
        widgets = {
            'password_asset': forms.Select(),  # Dropdown for selecting the asset
            'password': forms.TextInput(attrs={'type': 'text'}),  
        }

