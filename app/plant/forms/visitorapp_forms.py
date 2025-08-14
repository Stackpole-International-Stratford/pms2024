# plant/forms.py
from django import forms
from django.contrib.auth import get_user_model
from ..models.visitorapp_models import *
import base64

User = get_user_model()

class HostMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        full_name = (obj.get_full_name() or "").strip()
        label = full_name if full_name else obj.username
        if obj.email:
            label = f"{label} ({obj.email})"
        return label

class VisitorLogForm(forms.ModelForm):
    # Extra fields for photo handling (not stored in DB)
    photo = forms.ImageField(required=False)
    photo_data = forms.CharField(widget=forms.HiddenInput(), required=False)

    hosts = HostMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": "8"}),
        help_text="Choose one or more hosts."
    )

    visitor_type = forms.ChoiceField(
        choices=VisitorLog.VISITOR_TYPES,
        widget=forms.RadioSelect
    )

    class Meta:
        model = VisitorLog
        fields = ["first_name", "last_name", "email", "visitor_type", "hosts"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate hosts from group 'visitor_hosts'
        self.fields["hosts"].queryset = (
            User.objects.filter(groups__name="visitor_hosts", is_active=True)
            .order_by("first_name", "last_name")
            .distinct()
        )
        # Bootstrap styling
        for name in ("first_name", "last_name", "email"):
            self.fields[name].widget.attrs.update({"class": "form-control", "required": True})

    def clean(self):
        cleaned = super().clean()
        # Require at least one host
        hosts = cleaned.get("hosts")
        if not hosts or len(hosts) == 0:
            self.add_error("hosts", "Please choose at least one host.")

        # Require a photo either via upload or captured data
        file_obj = cleaned.get("photo")
        data_url = cleaned.get("photo_data")

        if not file_obj and not data_url:
            # Non-field error makes it show at the top
            self.add_error(None, "Please add a photo (use the camera or upload a file).")

        # If data_url present, validate it looks like an image data URL and is decodable
        if data_url:
            if not data_url.startswith("data:image"):
                self.add_error(None, "Captured photo is invalid.")
            else:
                try:
                    header, b64 = data_url.split(",", 1)
                    base64.b64decode(b64)
                except Exception:
                    self.add_error(None, "Captured photo could not be processed.")
        return cleaned
