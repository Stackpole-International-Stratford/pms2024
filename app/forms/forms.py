from django import forms
from .models import Form, FormQuestion, FormType
from django.forms.widgets import DateInput
from django.forms import ValidationError



# OIS Form
class OISForm(forms.ModelForm):
    part_number = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    operation = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    part_name = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    year = forms.CharField(max_length=4, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    mod_level = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    machine = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    mod_date = forms.DateField(required=True, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))

    class Meta:
        model = Form
        fields = ['name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.metadata:
            # Prepopulate fields from the metadata JSON
            self.fields['part_number'].initial = self.instance.metadata.get('part_number', '')
            self.fields['operation'].initial = self.instance.metadata.get('operation', '')
            self.fields['part_name'].initial = self.instance.metadata.get('part_name', '')
            self.fields['year'].initial = self.instance.metadata.get('year', '')
            self.fields['mod_level'].initial = self.instance.metadata.get('mod_level', '')
            self.fields['machine'].initial = self.instance.metadata.get('machine', '')
            self.fields['mod_date'].initial = self.instance.metadata.get('mod_date', '')

    def save(self, commit=True):
        form_instance = super().save(commit=False)
        form_instance.form_type = FormType.objects.get(name="OIS")
        form_instance.metadata = {
            'part_number': self.cleaned_data['part_number'],
            'operation': self.cleaned_data['operation'],
            'part_name': self.cleaned_data['part_name'],
            'year': self.cleaned_data['year'],
            'mod_level': self.cleaned_data['mod_level'],
            'machine': self.cleaned_data['machine'],
            'mod_date': self.cleaned_data['mod_date'].isoformat()
        }
        if commit:
            form_instance.save()
        return form_instance





class OISQuestionForm(forms.ModelForm):
    # Specification Type Selector
    specification_type = forms.ChoiceField(
        choices=[
            ('string', 'Text-based Specification'),
            ('range', 'Numeric Range Specification'),
        ],
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # String Specification (Legacy Support)
    specification_string = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Acceptable YES / NO'
        })
    )

    # Numeric Range Specification
    min_value = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Min Value'
        })
    )
    nominal_value = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nominal Value'
        })
    )
    max_value = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Max Value'
        })
    )
    units = forms.ChoiceField(
        choices=[
            ('nm', 'nm'), ('μm', 'μm'), ('mm', 'mm'), ('cm', 'cm'), ('m', 'm'),
            ('in', 'in'), ('ft', 'ft'), ('mg', 'mg'), ('g', 'g'), ('kg', 'kg'),
            ('lb', 'lb'), ('N', 'N'), ('kN', 'kN'), ('MPa', 'MPa'), ('psi', 'psi'),
            ('Nm', 'Nm'), ('lb-ft', 'lb-ft'), ('°C', '°C'), ('°F', '°F'),
            ('deg', 'deg'), ('rad', 'rad')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # New Fields: Lower and Upper Control Limits (optional)
    lower_control_limit = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Lower Control Limit'
        })
    )
    upper_control_limit = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Upper Control Limit'
        })
    )

    # New Field: Inspection Type as Dropdown
    inspection_type = forms.ChoiceField(
        choices=[
            ('', 'Select Inspection Type'),
            ('OIS', 'OIS'),
            ('First Off', 'First Off'),
            ('Last Off', 'Last Off'),
            ('First Off and Last Off', 'First Off and Last Off'),
        ],
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # Existing Fields
    feature = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    special_characteristic = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    characteristic = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    sample_frequency = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    sample_size = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    done_by = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    order = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=False
    )
    checkmark = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = FormQuestion
        fields = [
            'feature', 'special_characteristic', 'characteristic', 
            'specification_type', 'specification_string', 
            'min_value', 'nominal_value', 'max_value', 'units',
            'lower_control_limit', 'upper_control_limit',
            'sample_frequency', 'sample_size', 'done_by', 
            'order', 'checkmark', 'inspection_type'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.question:
            q = self.instance.question
            specification_type = q.get('specification_type', 'string')
            self.fields['specification_type'].initial = specification_type
            
            if specification_type == 'string':
                self.fields['specification_string'].initial = q.get('specifications', '')
            elif specification_type == 'range':
                specs = q.get('specifications', {})
                self.fields['min_value'].initial = specs.get('min', '')
                self.fields['nominal_value'].initial = specs.get('nominal', '')
                self.fields['max_value'].initial = specs.get('max', '')
                self.fields['units'].initial = specs.get('units', '')
                # Set initial values for the new control limits if present
                self.fields['lower_control_limit'].initial = specs.get('lower_control_limit', '')
                self.fields['upper_control_limit'].initial = specs.get('upper_control_limit', '')

            self.fields['feature'].initial = q.get('feature', '')
            self.fields['special_characteristic'].initial = q.get('special_characteristic', '')
            self.fields['characteristic'].initial = q.get('characteristic', '')
            self.fields['sample_frequency'].initial = q.get('sample_frequency', '')
            self.fields['sample_size'].initial = q.get('sample_size', '')
            self.fields['done_by'].initial = q.get('done_by', '')
            self.fields['order'].initial = q.get('order', 1)
            self.fields['checkmark'].initial = q.get('checkmark', False)
            self.fields['inspection_type'].initial = q.get('inspection_type', '')

    def clean(self):
        cleaned_data = super().clean()
        spec_type = cleaned_data.get('specification_type')

        if spec_type == 'string' and not cleaned_data.get('specification_string'):
            self.add_error('specification_string', 'Please provide a specification string.')
        elif spec_type == 'range':
            min_v = cleaned_data.get('min_value')
            nominal_v = cleaned_data.get('nominal_value')
            max_v = cleaned_data.get('max_value')
            if min_v is None or nominal_v is None or max_v is None:
                self.add_error('min_value', 'Min, Nominal, and Max are required for numeric range.')
            elif min_v > nominal_v or nominal_v > max_v:
                self.add_error('nominal_value', 'Nominal value must be between Min and Max.')

            # If both lower and upper control limits are provided, check that lower <= upper.
            lcl = cleaned_data.get('lower_control_limit')
            ucl = cleaned_data.get('upper_control_limit')
            if lcl is not None and ucl is not None:
                if lcl > ucl:
                    self.add_error('lower_control_limit', 'Lower Control Limit must be less than or equal to Upper Control Limit.')
        if not cleaned_data.get('inspection_type'):
            self.add_error('inspection_type', 'Please select an inspection type.')

        return cleaned_data

    def save(self, form_instance=None, order=None, commit=True):
        question_instance = super().save(commit=False)
        if form_instance:
            question_instance.form = form_instance
            if order is None:
                last_question = form_instance.questions.order_by('-id').first()
                if last_question and last_question.question.get('order'):
                    order = last_question.question.get('order') + 1
                else:
                    order = 1

        cd = self.cleaned_data
        spec_type = cd.get('specification_type')

        if spec_type == 'string':
            specs = cd.get('specification_string', '')
        else:
            specs = {
                'min': cd.get('min_value'),
                'nominal': cd.get('nominal_value'),
                'max': cd.get('max_value'),
                'units': cd.get('units'),
                'lower_control_limit': cd.get('lower_control_limit'),
                'upper_control_limit': cd.get('upper_control_limit'),
            }

        question_data = {
            'feature': cd.get('feature'),
            'special_characteristic': cd.get('special_characteristic'),
            'characteristic': cd.get('characteristic'),
            'specification_type': spec_type,
            'specifications': specs,
            'sample_frequency': cd.get('sample_frequency'),
            'sample_size': cd.get('sample_size'),
            'done_by': cd.get('done_by'),
            'order': order,
            'checkmark': cd.get('checkmark', False),
            'inspection_type': cd.get('inspection_type'),
        }
        question_instance.question = question_data

        if commit:
            question_instance.save()
        return question_instance








# TPM Form
class TPMForm(forms.ModelForm):
    part_number = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    operation = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = Form
        fields = ['name']  # Assuming 'name' is a standard field for all forms

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.metadata:
            # Prepopulate fields from the metadata JSON
            self.fields['part_number'].initial = self.instance.metadata.get('part_number', '')
            self.fields['operation'].initial = self.instance.metadata.get('operation', '')

    def save(self, commit=True):
        form_instance = super().save(commit=False)
        form_instance.form_type = FormType.objects.get(name="TPM")  # Assuming FormType for TPM exists
        form_instance.metadata = {
            'part_number': self.cleaned_data['part_number'],
            'operation': self.cleaned_data['operation'],
        }
        if commit:
            form_instance.save()
        return form_instance


# Updated TPM Question Form with order field
class TPMQuestionForm(forms.ModelForm):
    question_text = forms.CharField(
        # max_length=255,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter a question'})
    )
    order = forms.IntegerField(
        widget=forms.HiddenInput(), 
        required=False, 
        initial=1  # Default value for order if not provided
    )

    class Meta:
        model = FormQuestion
        fields = ['question_text', 'order']  # Include order field

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.question:
            # Prepopulate the field from the question JSON
            self.fields['question_text'].initial = self.instance.question.get('question_text', '')
            self.fields['order'].initial = self.instance.question.get('order', 1)  # Get 'order' from JSON, default to 1

    def save(self, form_instance=None, order=None, commit=True):
        question_instance = super().save(commit=False)
        if form_instance:
            question_instance.form = form_instance
        # Build the question data
        question_data = {
            'question_text': self.cleaned_data['question_text'],
            'order': order if order is not None else self.cleaned_data.get('order', 1),  # Use provided order or fallback to field value
        }
        question_instance.question = question_data
        if commit:
            question_instance.save()
        return question_instance


# LPA Form
class LPAForm(forms.ModelForm):
    part_number = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    operation = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = Form
        fields = ['name']  # Assuming 'name' is a standard field for all forms

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.metadata:
            # Prepopulate fields from the metadata JSON
            self.fields['part_number'].initial = self.instance.metadata.get('part_number', '')
            self.fields['operation'].initial = self.instance.metadata.get('operation', '')

    def save(self, commit=True):
        form_instance = super().save(commit=False)
        form_instance.form_type = FormType.objects.get(name="LPA")  # Assuming FormType for LPA exists
        form_instance.metadata = {
            'part_number': self.cleaned_data['part_number'],
            'operation': self.cleaned_data['operation'],
        }
        if commit:
            form_instance.save()
        return form_instance


class LPAQuestionForm(forms.ModelForm):
    question_text = forms.CharField(
        max_length=600,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter a question'})
    )
    what_to_look_for = forms.CharField(
        max_length=600,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter what to look for (optional)'})
    )
    recommended_action = forms.CharField(
        max_length=600,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter recommended action (optional)'})
    )
    typed_answer = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    order = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=False,
        initial=1
    )
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'placeholder': 'Select expiry date (optional)',
        }),
        label="Expiry date (optional)",
    )

    class Meta:
        model = FormQuestion
        fields = ['question_text', 'what_to_look_for', 'recommended_action', 'typed_answer', 'order', 'expiry_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.question:
            self.fields['question_text'].initial = self.instance.question.get('question_text', '')
            self.fields['what_to_look_for'].initial = self.instance.question.get('what_to_look_for', '')
            self.fields['recommended_action'].initial = self.instance.question.get('recommended_action', '')
            self.fields['typed_answer'].initial = self.instance.question.get('typed_answer', False)
            self.fields['order'].initial = self.instance.question.get('order', 1)
            expiry_date = self.instance.question.get('expiry_date', None)
            self.fields['expiry_date'].initial = expiry_date

    def save(self, form_instance=None, order=None, commit=True):
        question_instance = super().save(commit=False)
        if form_instance:
            question_instance.form = form_instance

            # If no order is provided, compute it based on existing questions for the form.
            if order is None:
                # Assuming the questions are stored as JSON with an "order" key.
                # Order the existing questions in descending order and get the highest order value.
                last_question = form_instance.questions.order_by('-id').first()
                if last_question and last_question.question.get('order'):
                    order = last_question.question.get('order') + 1
                else:
                    order = 1

        # Build the question data using the computed order.
        question_data = {
            'question_text': self.cleaned_data['question_text'],
            'what_to_look_for': self.cleaned_data.get('what_to_look_for', ''),
            'recommended_action': self.cleaned_data.get('recommended_action', ''),
            'typed_answer': self.cleaned_data.get('typed_answer', False),
            'order': order if order is not None else self.cleaned_data.get('order', 1),
            'expiry_date': self.cleaned_data.get('expiry_date', None).isoformat() if self.cleaned_data.get('expiry_date') else None
        }
        question_instance.question = question_data
        if commit:
            question_instance.save()
        return question_instance




# Dictionary for dynamically mapping form types to form classes
FORM_TYPE_FORMS = {
    'OIS': OISForm,
    'TPM': TPMForm,  # Added TPM form
    'LPA': LPAForm,
}

# Dictionary for dynamically mapping form types to question form classes
QUESTION_FORM_CLASSES = {
    'OIS': OISQuestionForm,
    'TPM': TPMQuestionForm,  # Added TPM question form
    'LPA': LPAQuestionForm,
}










from django.core.exceptions import ValidationError
from django import forms
from .models import FormAnswer

class OISAnswerForm(forms.ModelForm):
    class Meta:
        model = FormAnswer
        fields = ['answer']

    def __init__(self, *args, question=None, **kwargs):
        """Adjust the answer field based on whether the question requires a checkmark."""
        super().__init__(*args, **kwargs)
        if question and question.question.get('checkmark', False):  # Use dropdown for checkmark questions
            self.fields['answer'] = forms.ChoiceField(
                choices=[('', 'Select...'), ('Pass', 'Pass'), ('Fail', 'Fail')],
                widget=forms.Select(attrs={'class': 'form-select'})  # Use Bootstrap's form-select for styling
            )
        else:
            # Default to a text input for non-checkmark questions
            self.fields['answer'] = forms.CharField(
                max_length=255,
                required=True,
                widget=forms.TextInput(attrs={
                    'class': 'form-control input-box',
                    'style': 'width: 100px;',
                    'placeholder': 'Answer'
                })
            )





class LPAAnswerForm(forms.ModelForm):
    """
    Form for capturing Yes/No/N/A answers for LPA questions,
    with fields for 'Issue', 'Action Taken', and an additional char input field.
    """
    answer = forms.ChoiceField(
        choices=[('', 'Select...'), ('Yes', 'Yes'), ('No', 'No'), ('N/A', 'N/A')],
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False
    )
    issue = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Describe the issue',
            'rows': 3
        })
    )
    action_taken = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Describe the action taken',
            'rows': 3
        })
    )
    additional_input = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Answer Here'
        })
    )

    class Meta:
        model = FormAnswer
        fields = ['answer']  # We'll dynamically store everything in 'answer'

    def __init__(self, *args, question=None, user=None, machine=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user  # Store the user in the form instance
        self.machine = machine  # Store the machine in the form instance
        # Optionally process the 'question' parameter if needed.
        if question:
            # For example, you might want to adjust field properties based on the question's metadata.
            pass

    def clean(self):
        """
        Validate the form and ensure that at least one of 'answer' or 'additional_input' is provided.
        Also, include the username and machine in the answer JSON.
        """
        cleaned_data = super().clean()
        answer = cleaned_data.get('answer')
        issue = cleaned_data.get('issue')
        action_taken = cleaned_data.get('action_taken')
        additional_input = cleaned_data.get('additional_input')

        # Validate that at least one of 'answer' or 'additional_input' is provided
        if not answer and not additional_input:
            raise forms.ValidationError("You must provide either an answer (Yes/No/N/A) or additional input.")

        # Validate that 'issue' and 'action_taken' are provided if 'answer' is 'No'
        if answer == 'No':
            if not issue:
                self.add_error('issue', "This field is required when 'No' is selected.")
            if not action_taken:
                self.add_error('action_taken', "This field is required when 'No' is selected.")

        # Construct the answer JSON
        answer_data = {}
        if answer:
            answer_data['answer'] = answer
        if answer == 'No' and issue and action_taken:
            answer_data.update({
                'issue': issue,
                'action_taken': action_taken,
            })
        if additional_input:
            answer_data['answer'] = additional_input

        # Add submitted_by and machine to the answer data
        if self.user and self.user.is_authenticated:
            answer_data['submitted_by'] = self.user.username
        else:
            answer_data['submitted_by'] = 'Anonymous'

        if self.machine:
            answer_data['machine'] = self.machine  # Include the machine value in the JSON

        # Debug print to check the final answer JSON
        print(f"[DEBUG] Final answer data: {answer_data}")

        # Store the constructed JSON in the 'answer' field
        cleaned_data['answer'] = answer_data

        return cleaned_data
