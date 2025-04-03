import datetime
from django import forms
from django.core.exceptions import ValidationError
from django.forms.widgets import DateInput, TimeInput

class WeeklyProdDate(forms.Form):
  date = forms.DateField(widget = DateInput(
            attrs={
                'class': '', 
                'type': 'date',
            }
        ))

class MultiStringListField(forms.Field):
  def to_python(self, value):
    if not value:
      return []
    return value.split(',')

  def validate(self, value):
    pass

class WeeklyProdUpdate(forms.Form):
  effective_date = forms.DateField(widget = DateInput(
            attrs={
                'class': '', 
                'type': 'date',
            }
        ))
  goal = forms.IntegerField()
  part_number = forms.CharField(max_length=12)

class TruncatingCharField(forms.Field):
  def to_python(self, value):
    if not value:
      return None
    return value.split(',')[0]

  def validate(self, value):
    pass

# class CycleQueryForm(forms.Form):
#   machine = TruncatingCharField()
#   CHOICES = [
#     (1, '10pm - 6am'),
#     (2, '11pm - 7am'),
#     (3, '6am - 2pm'),
#     (4, '7am - 3pm'),
#     (5, '2pm - 10pm'),
#     (6, '3pm - 11pm'),
#     (7, '6am - 6am'),
#     (8, '7am - 7am'),
#   ]
#   times = forms.ChoiceField(choices=CHOICES)
#   target_date = forms.DateField(initial=datetime.date.today, widget=DateInput)



class CycleQueryForm(forms.Form):
    machine = forms.CharField(label='Machine', max_length=100)
    start_date = forms.DateField(widget=DateInput(attrs={'type': 'date'}))
    start_time = forms.TimeField(widget=TimeInput(attrs={'type': 'time'}), initial='00:00')
    end_date = forms.DateField(widget=DateInput(attrs={'type': 'date'}))
    end_time = forms.TimeField(widget=TimeInput(attrs={'type': 'time'}), initial='23:59')

class ShiftLineForm(forms.Form):
  CHOICES = [
    ('50-8670', 'AB1V Reaction Gas'),
    ('50-5401', 'AB1V Input Gas'),
    ('50-5404', 'AB1V OverDrive Gas'),
    ('50-3214', '10R140 Gas'),
    ('50-5214', '10R140 Diesel'),
  ]
  line = forms.ChoiceField(choices=CHOICES)
  # start_date = DatePickerInput()
  # end_date = DatePickerInput(range_from="start_date")
  # start_time = TimePickerInput()
  # end_time = TimePickerInput(range_from="start_time")

class MachineInquiryForm(forms.Form):
  CHOICES = [
    (1, '10pm - 6am'),
    (2, '11pm - 7am'),
    (3, '6am - 2pm'),
    (4, '7am - 3pm'),
    (5, '2pm - 10pm'),
    (6, '3pm - 11pm'),
    (7, '6am - 6am'),
    (8, '7am - 7am'),
    (9, 'Week from Sunday @ 10pm'),
    (10, 'Week from Sunday @ 11pm'),
    (11, 'Week by Shifts (Sunday 10pm start)'),
    (12, 'Week by Shifts (Sunday 11pm start)'),

  ]

  machines = MultiStringListField(
    required=False,
    widget=forms.TextInput(attrs={"title":"A comma seperated list of Machine numbers"})
  )
  parts = MultiStringListField(
    required=False,
    widget=forms.TextInput(attrs={"title":"A comma seperated list of Asset numbers"})
  )
  inquiry_date = forms.DateField(initial=datetime.date.today)
  times = forms.ChoiceField(choices=CHOICES)

  def clean(self):
    cleaned_data = super().clean()
    machines = cleaned_data.get("machines")
    parts = cleaned_data.get("parts")

    if not parts and not machines:
      # Only do something if both fields are not present.
      raise ValidationError(
          "You need to specify at least one machine or part number"
      )
    


class ShiftTotalsForm(forms.Form):
    machine_number = forms.CharField(label='Machine Number', max_length=100)
    start_date = forms.DateTimeField(label='Start Date', widget=forms.DateTimeInput(attrs={'type': 'date'}))
    end_date = forms.DateTimeField(label='End Date', widget=forms.DateTimeInput(attrs={'type': 'date'}))