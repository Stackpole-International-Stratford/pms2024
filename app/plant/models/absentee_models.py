# plant/models.py
from django.db import models
from django.utils import timezone


class AbsenteeReport(models.Model):
    """
    Record of an employee’s absentee report for payroll purposes.

    Fields
    ------
    employee_name : str
        Full name of the employee.
    job : str
        Job title or position.
    pay_date : date
        The date to which this absentee record applies.
    pay_code : str
        Code representing the type of pay (e.g., absence reason).
    pay_category : str
        Higher-level category grouping of the pay code.
    hours : Decimal
        Number of hours absent.
    pay_group_name : str
        Name of the pay group (e.g., department or union group).
    shift_rotation_description : str
        Description of the employee’s shift rotation at the time.
    uploaded_at : datetime
        Timestamp (UTC) when this record was uploaded to the system.

    Methods
    -------
    __str__()
        Returns a human-readable representation: 
        "{employee_name} – {pay_date} ({pay_code})".
    """
    employee_name                = models.CharField(max_length=255)
    job                          = models.CharField(max_length=255)
    pay_date                     = models.DateField()
    pay_code                     = models.CharField(max_length=100)
    pay_category                 = models.CharField(max_length=100)
    hours                        = models.DecimalField(max_digits=6, decimal_places=2)
    pay_group_name               = models.CharField(max_length=255)
    shift_rotation_description   = models.CharField(max_length=255)
    uploaded_at                  = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.employee_name} – {self.pay_date} ({self.pay_code})"
