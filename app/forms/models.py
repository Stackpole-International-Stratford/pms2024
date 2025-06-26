from django.db import models

class FormSubmission(models.Model):
    """
    Record a raw form submission, including its payload, timestamp, and form type.

    Attributes:
        payload (dict):
            The full JSON payload of the submitted form.
        created_at (datetime.datetime):
            Timestamp automatically set when the submission is first created.
        form_type (FormType):
            Reference to the FormType this submission corresponds to.
    """
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    form_type = models.ForeignKey('FormType', on_delete=models.CASCADE)

    def __str__(self):
        return f"Submission {self.id} - {self.form_type.name}"


class FormType(models.Model):
    """
    Represents a category of form, defining its display name and the template
    used to render instances of this form type.

    Attributes:
        name (str):
            The human-readable name of this form type.
        template_name (str):
            The filename (within the `forms/` templates directory) used to
            render forms of this type.
    """
    name = models.CharField(max_length=255)
    template_name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Form(models.Model):
    """
    An instance of a specific FormType, capturing its name, creation timestamp,
    and arbitrary metadata for additional properties.

    Attributes:
        name (str):
            A descriptive name for this form instance.
        form_type (FormType):
            The type/category of form this instance belongs to.
        created_at (datetime.datetime):
            Automatically set timestamp when the form was created.
        metadata (dict):
            A JSON field for storing extra key/value data (e.g., part number,
            operation, machine, etc.). Defaults to an empty dict.
    """
    name = models.CharField(max_length=255)
    form_type = models.ForeignKey(FormType, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)  # Add the metadata field


    def __str__(self):
        return f"Form {self.name} - {self.form_type.name}"


class FormQuestion(models.Model):
    """
    A single question belonging to a specific Form, with its details stored as JSON.

    Attributes:
        form (Form):
            The parent form to which this question belongs.
        question (dict):
            A JSON object containing the question’s properties, e.g.:
            `{ "question_text": "...", "order": 1, "feature": "...", ... }`.
        created_at (datetime.datetime):
            Timestamp when this question was created.
    """
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='questions')
    question = models.JSONField()  # Store the question details as a JSON object
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Question for Form: {self.form.name}"


class FormAnswer(models.Model):
    """
    A submitted answer to a FormQuestion, capturing the response data,
    the operator who submitted it, and the timestamp of submission.

    Attributes:
        question (FormQuestion):
            The question this answer corresponds to.
        answer (dict):
            A JSON object containing the answer data. Structure is flexible,
            e.g. `{"answer": "Yes", "notes": "...", "closed_out": True}`.
        operator_number (str):
            Identifier for the operator who submitted the answer.
        created_at (datetime.datetime):
            The timestamp when this answer was created. Must be set explicitly.
    """
    question = models.ForeignKey(FormQuestion, on_delete=models.CASCADE, related_name='answers')
    answer = models.JSONField()  # Storing the answer as a JSON object for flexibility
    operator_number = models.CharField(max_length=255)  # New field to store operator number
    created_at = models.DateTimeField()  # No auto_now_add

    def __str__(self):
        return f"Answer by {self.operator_number} for Question ID: {self.question.id} - Form: {self.question.form.name}"
