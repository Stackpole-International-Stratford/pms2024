from django import forms

class BarcodeScanForm(forms.Form):
    """Form for entering a single barcode scan.

    Attributes:
        barcode (str): The scanned barcode string. Renders as a text input
            with autofocus enabled and is not required (can be empty).

    """
    barcode = forms.CharField(widget=forms.TextInput(attrs={'autofocus': 'autofocus'}), required=False)

    def clean_barcode(self):
        data = self.cleaned_data['barcode']
        return data

class BatchBarcodeScanForm(forms.Form):
    """Form for entering multiple barcode scans in a batch.

    Attributes:
        barcodes (str): Newline-separated barcode strings. Renders as a textarea
            and is optional (can be left empty).
    """
    barcodes = forms.CharField(widget=forms.Textarea(), required=False)

    def clean_barcodes(self):
        data = self.cleaned_data['barcodes']
        return data

class UnlockCodeForm(forms.Form):
    """Form for submitting an unlock code along with employee identification and a reason.

    Fields:
        employee_id (str): The ID of the employee entering the unlock code (3–10 chars).
        unlock_code (str): The three‐character unlock code provided after a duplicate scan.
        reason (str): A radio‐select choice indicating why the duplicate occurred.
        other_reason (str): An optional free‐text reason, required if "Other" is selected.

    Validation:
        - Ensures `other_reason` is non‐empty when `reason == 'other'`.
    """
    REASON_CHOICES = [
        ('a', 'Unsure, part scrapped'),
        ('b', 'One part scanned twice'),
        ('c', 'Duplicate found, part tagged and in QA'),
        ('other', 'Other')
    ]

    employee_id = forms.CharField(max_length=10, min_length=3, required=True)
    unlock_code = forms.CharField(max_length=3, required=True)
    reason = forms.ChoiceField(choices=REASON_CHOICES, widget=forms.RadioSelect, required=True)
    other_reason = forms.CharField(max_length=255, required=False)

    def clean(self):
        cleaned_data = super().clean()
        reason = cleaned_data.get('reason')
        other_reason = cleaned_data.get('other_reason')

        if reason == 'other' and not other_reason:
            self.add_error('other_reason', 'This field is required when "Other" is selected.')

        return cleaned_data
