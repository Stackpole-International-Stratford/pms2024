Module barcode.forms
====================

Classes
-------

`BarcodeScanForm(data=None, files=None, auto_id='id_%s', prefix=None, initial=None, error_class=django.forms.utils.ErrorList, label_suffix=None, empty_permitted=False, field_order=None, use_required_attribute=None, renderer=None)`
:   Form for entering a single barcode scan.
    
    Attributes:
        barcode (str): The scanned barcode string. Renders as a text input
            with autofocus enabled and is not required (can be empty).

    ### Ancestors (in MRO)

    * django.forms.forms.Form
    * django.forms.forms.BaseForm
    * django.forms.utils.RenderableFormMixin
    * django.forms.utils.RenderableMixin

    ### Class variables

    `base_fields`
    :

    `declared_fields`
    :

    ### Instance variables

    `media`
    :

    ### Methods

    `clean_barcode(self)`
    :

`BatchBarcodeScanForm(data=None, files=None, auto_id='id_%s', prefix=None, initial=None, error_class=django.forms.utils.ErrorList, label_suffix=None, empty_permitted=False, field_order=None, use_required_attribute=None, renderer=None)`
:   Form for entering multiple barcode scans in a batch.
    
    Attributes:
        barcodes (str): Newline-separated barcode strings. Renders as a textarea
            and is optional (can be left empty).

    ### Ancestors (in MRO)

    * django.forms.forms.Form
    * django.forms.forms.BaseForm
    * django.forms.utils.RenderableFormMixin
    * django.forms.utils.RenderableMixin

    ### Class variables

    `base_fields`
    :

    `declared_fields`
    :

    ### Instance variables

    `media`
    :

    ### Methods

    `clean_barcodes(self)`
    :

`UnlockCodeForm(data=None, files=None, auto_id='id_%s', prefix=None, initial=None, error_class=django.forms.utils.ErrorList, label_suffix=None, empty_permitted=False, field_order=None, use_required_attribute=None, renderer=None)`
:   Form for submitting an unlock code along with employee identification and a reason.
    
    Fields:
        employee_id (str): The ID of the employee entering the unlock code (3–10 chars).
        unlock_code (str): The three‐character unlock code provided after a duplicate scan.
        reason (str): A radio‐select choice indicating why the duplicate occurred.
        other_reason (str): An optional free‐text reason, required if "Other" is selected.
    
    Validation:
        - Ensures `other_reason` is non‐empty when `reason == 'other'`.

    ### Ancestors (in MRO)

    * django.forms.forms.Form
    * django.forms.forms.BaseForm
    * django.forms.utils.RenderableFormMixin
    * django.forms.utils.RenderableMixin

    ### Class variables

    `REASON_CHOICES`
    :

    `base_fields`
    :

    `declared_fields`
    :

    ### Instance variables

    `media`
    :

    ### Methods

    `clean(self)`
    :   Hook for doing any extra form-wide cleaning after Field.clean() has been
        called on every field. Any ValidationError raised by this method will
        not be associated with a particular field; it will have a special-case
        association with the field named '__all__'.