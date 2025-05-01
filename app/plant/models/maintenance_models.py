# plant/models/maintenance_models.py

from django.db import models

class MachineDowntimeEvent(models.Model):
    """
    Represents a single downtime event on a production line.
    """
    line               = models.CharField("Line",         max_length=50)
    machine            = models.CharField("Machine",      max_length=50)
    category           = models.CharField("Category",     max_length=16,
                                          help_text="e.g. 'MAT'")
    subcategory        = models.CharField("Subcategory",  max_length=20,
                                          help_text="e.g. 'MAT-DEF'")
    code               = models.CharField("Downtime Code",max_length=20,
                                          help_text="Same as subcategory")
    start_epoch        = models.BigIntegerField("Start (epoch)")
    closeout_timestamp = models.DateTimeField("Closed At",  null=True, blank=True)
    comment            = models.TextField("Comment")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} @ {self.start_epoch} on {self.line}/{self.machine}"
