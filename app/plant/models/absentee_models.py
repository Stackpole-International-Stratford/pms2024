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

    # Derived from PayCodeGroup (if mapping exists)
    pay_group                    = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # NEW: whether this row is scheduled or unscheduled, based on mapping table
    is_scheduled                 = models.BooleanField(blank=True, null=True, db_index=True)

    # NEW: derived from ShiftRotationMap (if mapping exists)
    shift                        = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    def __str__(self):
        return f"{self.employee_name} – {self.pay_date} ({self.pay_code})"


class PayCodeGroup(models.Model):
    """
    Minimal lookup table maintained by managers/admin:
    - No FK to AbsenteeReport (by request).
    - We’ll do case-insensitive, trimmed matching in code.
    """
    pay_code     = models.CharField(max_length=100, unique=True, db_index=True)
    group_name   = models.CharField(max_length=100)

    # True = scheduled, False = unscheduled
    is_scheduled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.pay_code} → {self.group_name} ({'Scheduled' if self.is_scheduled else 'Unscheduled'})"

    class Meta:
        verbose_name = "Pay Code Group"
        verbose_name_plural = "Pay Code Groups"


# NEW: table mirroring PayCodeGroup but for shift rotations
class ShiftRotationMap(models.Model):
    """
    Lookup table for mapping a free-form Shift Rotation Description to a canonical Shift string.
    Matching is case-insensitive and trimmed (done in code).
    """
    rotation_text = models.CharField(max_length=255, unique=True, db_index=True)
    shift         = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.rotation_text} → {self.shift}"

    class Meta:
        verbose_name = "Shift Rotation Map"
        verbose_name_plural = "Shift Rotation Maps"
