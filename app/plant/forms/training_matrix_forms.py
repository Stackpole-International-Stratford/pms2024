from django import forms
from ..models.training_matrix_models import TrainingJob

class TrainingJobForm(forms.ModelForm):
    class Meta:
        model = TrainingJob
        fields = ['area', 'line', 'operation', 'description']
        widgets = {
            'area': forms.Select(attrs={
                'class': 'form-select',
                'required': 'required',
            }),
            'line': forms.TextInput(attrs={
                'class': 'form-control',
                'required': 'required',
            }),
            'operation': forms.TextInput(attrs={
                'class': 'form-control',
                'required': 'required',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'required': 'required',
            }),
        }