# plant/models.py
from django.db import models
from django.utils import timezone


class AbsenteeReport(models.Model):
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
