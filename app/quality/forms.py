# quality/forms.py
from django import forms
from .models import Feat, QualityPDFDocument, RedRabbitType
from plant.models.setupfor_models import Part

class FeatForm(forms.ModelForm):
    part = forms.ModelChoiceField(queryset=Part.objects.all(), label="Part Number")

    class Meta:
        model = Feat
        fields = ['part', 'name', 'order', 'alarm']  # Include the alarm field


from django import forms
from .models import QualityPDFDocument
from plant.models.setupfor_models import Part

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




from django import forms
from .models import RedRabbitType
from plant.models.setupfor_models import Part

class RedRabbitTypeForm(forms.ModelForm):
    class Meta:
        model = RedRabbitType
        fields = ['name', 'description', 'part']  # Include the part field
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'part': forms.Select(attrs={'class': 'form-control'}),  # Dropdown for parts
        }
