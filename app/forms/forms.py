from django import forms
from .models import Form, FormQuestion, FormType
from django.forms.widgets import DateInput


# OIS Form
class OISForm(forms.ModelForm):
    """
    A ModelForm for creating and editing OIS-type Form instances, exposing
    metadata fields (part number, operation, etc.) as individual form inputs.

    This form:
      - Renders the `name` field from the underlying Form model.
      - Adds custom fields for each metadata key required by OIS forms.
      - Pre-populates metadata fields from an existing instance on edit.
      - On save, assigns the FormType "OIS" and consolidates cleaned metadata
        back into the Form.metadata JSON field.

    Fields:
        name (CharField):
            The descriptive name of the Form instance (from the Form model).
        part_number (CharField):
            The part number metadata for the OIS form.
        operation (CharField):
            The operation metadata for the OIS form.
        part_name (CharField):
            The part name metadata for the OIS form.
        year (CharField):
            The year metadata (4-digit string).
        mod_level (CharField):
            The modification level metadata.
        machine (CharField):
            The machine identifier metadata.
        mod_date (DateField):
            The modification date metadata.

    Methods:
        __init__(*args, **kwargs):
            If editing an existing Form instance, initializes each metadata field
            from instance.metadata.
        save(commit=True):
            Sets form_type to the OIS FormType, updates instance.metadata from
            cleaned_data, saves the Form, and returns it.
    """
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






# OIS Question form
class OISQuestionForm(forms.ModelForm):
    """
    A ModelForm for creating and editing OIS-specific FormQuestion instances.

    Exposes each question property stored in the JSON `question` field as individual form inputs:
      - feature
      - special_characteristic
      - characteristic
      - specifications
      - sample_frequency
      - sample_size
      - done_by
      - order (hidden)
      - checkmark (boolean)

    On initialization, if editing an existing FormQuestion, pre-populates each field
    from `instance.question`. On save, rebuilds the JSON payload combining cleaned_data
    and any provided `form_instance` or explicit `order`.

    Fields:
        feature (CharField): The feature name.
        special_characteristic (CharField): Optional special characteristic.
        characteristic (CharField): The measured characteristic.
        specifications (CharField): Specs to check against.
        sample_frequency (CharField): How often to sample.
        sample_size (CharField): Number of samples per check.
        done_by (CharField): Role or person who performs the check.
        order (IntegerField): Hidden field to maintain question ordering.
        checkmark (BooleanField): Indicates if this question uses a checkmark UI.

    Methods:
        __init__(*args, **kwargs):
            Pre-fill fields from `instance.question` when editing.
        save(form_instance=None, order=None, commit=True):
            Assigns `form_instance` if provided, rebuilds `question` JSON from cleaned_data,
            uses explicit `order` if passed, saves the model, and returns the instance.
    """
    feature = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    special_characteristic = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    characteristic = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    specifications = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    sample_frequency = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    sample_size = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    done_by = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    order = forms.IntegerField(widget=forms.HiddenInput(), required=False)  # Hidden order field
    checkmark = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))  # New Checkmark field

    class Meta:
        model = FormQuestion
        fields = ['feature', 'special_characteristic', 'characteristic', 'specifications', 'sample_frequency', 'sample_size', 'done_by', 'order', 'checkmark']  # Include checkmark in fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.question:
            # Prepopulate fields from the question JSON
            self.fields['feature'].initial = self.instance.question.get('feature', '')
            self.fields['special_characteristic'].initial = self.instance.question.get('special_characteristic', '')
            self.fields['characteristic'].initial = self.instance.question.get('characteristic', '')
            self.fields['specifications'].initial = self.instance.question.get('specifications', '')
            self.fields['sample_frequency'].initial = self.instance.question.get('sample_frequency', '')
            self.fields['sample_size'].initial = self.instance.question.get('sample_size', '')
            self.fields['done_by'].initial = self.instance.question.get('done_by', '')
            self.fields['order'].initial = self.instance.question.get('order', 1)  # Get 'order' from JSON
            self.fields['checkmark'].initial = self.instance.question.get('checkmark', False)  # Get 'checkmark' from JSON, default to False

    def save(self, form_instance=None, order=None, commit=True):
        question_instance = super().save(commit=False)
        if form_instance:
            question_instance.form = form_instance
        # Build the question data
        question_data = {
            'feature': self.cleaned_data['feature'],
            'special_characteristic': self.cleaned_data['special_characteristic'],
            'characteristic': self.cleaned_data['characteristic'],
            'specifications': self.cleaned_data['specifications'],
            'sample_frequency': self.cleaned_data['sample_frequency'],
            'sample_size': self.cleaned_data['sample_size'],
            'done_by': self.cleaned_data['done_by'],
            'order': order if order is not None else self.cleaned_data.get('order', 1),
            'checkmark': self.cleaned_data['checkmark'],  # Add checkmark to the question data
        }
        question_instance.question = question_data
        if commit:
            question_instance.save()
        return question_instance



# TPM Form
class TPMForm(forms.ModelForm):
    """
    A ModelForm for creating and editing TPM-type Form instances, exposing
    metadata fields (part number and operation) as individual form inputs.

    This form:
      - Renders the `name` field from the underlying Form model.
      - Adds custom fields for TPM-specific metadata: `part_number` and `operation`.
      - Pre-populates those fields from `instance.metadata` when editing.
      - On save, assigns the FormType "TPM" and consolidates cleaned metadata
        back into the Form.metadata JSON field.

    Fields:
        name (CharField):
            The descriptive name of the Form instance (inherited from Form).
        part_number (CharField):
            The part number metadata for the TPM form.
        operation (CharField):
            The operation metadata for the TPM form.

    Methods:
        __init__(*args, **kwargs):
            If editing an existing Form instance, initializes metadata fields
            from `instance.metadata`.
        save(commit=True):
            Sets `form_type` to the "TPM" FormType, updates `metadata` from
            `cleaned_data`, saves the Form, and returns it.
    """
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
    """
    A ModelForm for creating and editing TPM-specific FormQuestion instances,
    exposing a simple question text and hidden ordering field.

    This form:
      - Renders a `question_text` input for the question prompt.
      - Includes a hidden `order` field to control question ordering.
      - Pre-populates fields from `instance.question` JSON when editing.
      - On save, assigns the parent form (if provided) and rebuilds the JSON
        payload with `question_text` and `order`.

    Fields:
        question_text (CharField):
            The text of the TPM question.
        order (IntegerField):
            Hidden field indicating the question’s order in the form.

    Methods:
        __init__(*args, **kwargs):
            If editing an existing FormQuestion, initializes fields from
            `instance.question` JSON.
        save(form_instance=None, order=None, commit=True):
            Sets `form_instance` if provided, uses the explicit `order` argument
            or the cleaned_data value, rebuilds `question` JSON, saves the model,
            and returns the instance.
    """
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
    """
    A ModelForm for creating and editing LPA-type Form instances, exposing
    metadata fields (part number and operation) as individual form inputs.

    This form:
      - Renders the `name` field from the underlying Form model.
      - Adds custom fields for LPA-specific metadata: `part_number` and `operation`.
      - Pre-populates those fields from `instance.metadata` when editing.
      - On save, assigns the FormType "LPA" and consolidates cleaned metadata
        back into the Form.metadata JSON field.

    Fields:
        name (CharField):
            The descriptive name of the Form instance (inherited from Form).
        part_number (CharField):
            The part number metadata for the LPA form.
        operation (CharField):
            The operation metadata for the LPA form.

    Methods:
        __init__(*args, **kwargs):
            If editing an existing Form instance, initializes metadata fields
            from `instance.metadata`.
        save(commit=True):
            Sets `form_type` to the "LPA" FormType, updates `metadata` from
            `cleaned_data`, saves the Form, and returns it.
    """
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
    """
    A ModelForm for creating and editing LPA-specific FormQuestion instances.

    Exposes JSON-backed question properties as individual form fields:
      - question_text: the main question prompt.
      - what_to_look_for: optional guidance on what to inspect.
      - recommended_action: optional follow-up action.
      - typed_answer: boolean flag indicating free-text response.
      - order: hidden integer to control question ordering.
      - expiry_date: optional date after which the question expires.

    Initialization:
      - If editing an existing FormQuestion, each field is pre-populated
        from `instance.question` JSON.

    Saving:
      - Accepts an optional `form_instance` to associate the question with its Form.
      - Uses an explicit `order` argument if provided, otherwise the cleaned_data value.
      - Converts `expiry_date` to ISO format if present.
      - Rebuilds `question_instance.question` as a JSON dict from cleaned_data.
      - Saves and returns the FormQuestion instance.

    Fields:
        question_text (CharField): Required prompt text (max 600 chars).
        what_to_look_for (CharField): Optional guidance (max 600 chars).
        recommended_action (CharField): Optional action instructions (max 600 chars).
        typed_answer (BooleanField): Checkbox to indicate a typed response is allowed.
        order (IntegerField): Hidden ordering index (default 1).
        expiry_date (DateField): Optional expiration date (YYYY-MM-DD).

    Methods:
        __init__(*args, **kwargs): Pre-populate fields from JSON on edit.
        save(form_instance=None, order=None, commit=True): Build and save the JSON payload.
    """
    question_text = forms.CharField(
        max_length=600,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter a question'})
    )
    what_to_look_for = forms.CharField(
        max_length=600,
        required=False,  # Optional
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter what to look for (optional)'}))
    recommended_action = forms.CharField(
        max_length=600,
        required=False,  # Optional
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter recommended action (optional)'}))
    typed_answer = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    order = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=False,
        initial=1  # Default value for order if not provided
    )
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'placeholder': 'Select expiry date (optional)',
        }),
        label="Expiry date (optional)",  # Updated label
    )

    class Meta:
        model = FormQuestion
        fields = ['question_text', 'what_to_look_for', 'recommended_action', 'typed_answer', 'order', 'expiry_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.question:
            # Prepopulate the fields from the question JSON
            self.fields['question_text'].initial = self.instance.question.get('question_text', '')
            self.fields['what_to_look_for'].initial = self.instance.question.get('what_to_look_for', '')
            self.fields['recommended_action'].initial = self.instance.question.get('recommended_action', '')
            self.fields['typed_answer'].initial = self.instance.question.get('typed_answer', False)  # Prepopulate the checkbox
            self.fields['order'].initial = self.instance.question.get('order', 1)
            # Prepopulate the expiry date if available
            expiry_date = self.instance.question.get('expiry_date', None)
            self.fields['expiry_date'].initial = expiry_date

    def save(self, form_instance=None, order=None, commit=True):
        question_instance = super().save(commit=False)
        if form_instance:
            question_instance.form = form_instance
        # Build the question data
        question_data = {
            'question_text': self.cleaned_data['question_text'],
            'what_to_look_for': self.cleaned_data.get('what_to_look_for', ''),
            'recommended_action': self.cleaned_data.get('recommended_action', ''),
            'typed_answer': self.cleaned_data.get('typed_answer', False),  # Add the checkbox value to the JSON
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
    """
    A ModelForm for submitting answers to OIS questions, dynamically choosing
    the input widget based on the question's `checkmark` flag.

    - If `question.question['checkmark']` is True, renders a dropdown with
      Pass/Fail choices.
    - Otherwise, renders a text input for a free-form answer.

    Meta:
        model: FormAnswer
        fields: ['answer']

    Methods:
        __init__(*args, question=None, **kwargs):
            Initializes the form and, if a `question` is provided, inspects
            its JSON data to determine whether to use a ChoiceField (checkmark)
            or CharField (text input) for the `answer` field.
    """
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
        choices=[('', 'Select...'), ('Yes', 'Yes'), ('No', 'No'), ('N/A', 'N/A')],  # Added 'N/A' as an option
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

    def __init__(self, *args, user=None, machine=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user  # Store the user in the form instance
        self.machine = machine  # Store the machine in the form instance

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
 