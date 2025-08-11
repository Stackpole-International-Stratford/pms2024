# quality/forms.py
from django import forms
from .models import Feat, QualityPDFDocument, RedRabbitType
from plant.models.setupfor_models import Part
from .models import TPCRequest
from .models import RedRabbitType
from .models import QualityPDFDocument


class FeatForm(forms.ModelForm):
    part = forms.ModelChoiceField(queryset=Part.objects.all(), label="Part Number")

    class Meta:
        model = Feat
        fields = ['part', 'name', 'order', 'alarm']  # Include the alarm field



class PDFUploadForm(forms.ModelForm):
    associated_parts = forms.ModelMultipleChoiceField(
        queryset=Part.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = QualityPDFDocument
        fields = ['title', 'pdf_file', 'category', 'associated_parts']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'pdf_file': forms.FileInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
        }




class RedRabbitTypeForm(forms.ModelForm):
    class Meta:
        model = RedRabbitType
        fields = ['name', 'description', 'part']  # Include the part field
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'part': forms.Select(attrs={'class': 'form-control'}),  # Dropdown for parts
        }





class TPCRequestForm(forms.ModelForm):
    part = forms.ModelChoiceField(
        queryset=Part.objects.all().order_by('part_number'),
        widget=forms.Select(attrs={"class": "form-control"}),
        to_field_name="part_number",  # This makes it store the part_number instead of the ID
        empty_label="Select a part number",
        label="Part Number"
    )

    class Meta:
        model = TPCRequest
        fields = [
            "issuer_name", "part", "reason", "process",
            "supplier_issue", "machine_number", "reason_note",
            "feature", "current_process", "changed_to",
            "expiration_date", "expiration_notes",
        ]
        widgets = {
            "expiration_date": forms.DateTimeInput(attrs={
                "type": "datetime-local",
                "class": "form-control"
            }),
            "issuer_name":     forms.TextInput(attrs={"class": "form-control"}),
            "reason":          forms.TextInput(attrs={"class": "form-control"}),
            "process":         forms.TextInput(attrs={"class": "form-control"}),
            "supplier_issue":  forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "machine_number":  forms.TextInput(attrs={"class": "form-control"}),
            "reason_note":     forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "feature":         forms.TextInput(attrs={"class": "form-control"}),
            "current_process": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "changed_to":      forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "expiration_notes":forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Make sure the CharField stores just the part_number string
        if isinstance(self.cleaned_data["part"], Part):
            instance.part = self.cleaned_data["part"].part_number
        if commit:
            instance.save()
        return instance




