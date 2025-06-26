# quality/forms.py
from django import forms
from .models import Feat, QualityPDFDocument, RedRabbitType
from plant.models.setupfor_models import Part

class FeatForm(forms.ModelForm):
    """
    Form for creating or updating Feat records.

    This form exposes the following fields from the Feat model:
      - part:        Select the associated Part instance.
      - name:        Name of the feature.
      - order:       Display or execution order for the feature.
      - alarm:       Numeric alarm threshold for the feature.

    Usage
    -----
    Render this form in templates to allow users to add or edit features,
    automatically validating against the underlying Feat model constraints.
    """
    part = forms.ModelChoiceField(queryset=Part.objects.all(), label="Part Number")

    class Meta:
        model = Feat
        fields = ['part', 'name', 'order', 'alarm']  # Include the alarm field


from django import forms
from .models import QualityPDFDocument
from plant.models.setupfor_models import Part

class PDFUploadForm(forms.ModelForm):
    """
    Form for uploading and categorizing QualityPDFDocument instances.

    Fields
    ------
    title : CharField
        Text input for the document title.
    pdf_file : FileField
        File input for selecting the PDF to upload.
    category : ChoiceField
        Dropdown to select one of the predefined document categories.
    associated_parts : ModelMultipleChoiceField
        Checkbox list to select one or more Part instances with which the
        document should be associated.

    Widgets
    -------
    - title: TextInput with CSS class 'form-control'
    - pdf_file: FileInput with CSS class 'form-control'
    - category: Select with CSS class 'form-control'
    - associated_parts: CheckboxSelectMultiple with CSS class 'form-check-input'

    Usage
    -----
    Render this form in a template to allow users to upload a new PDF document,
    choose its category, and link it to relevant parts. The form automatically
    handles saving the uploaded file and creating the QualityPDFDocument record
    along with its many-to-many associations.
    """
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
