# plant/models/maintenance_models.py

from django.db import models
from datetime import datetime as _datetime


class MachineDowntimeEvent(models.Model):
    """
    Represents a single downtime event on a production line.
    """
    line               = models.CharField("Line",         max_length=50)
    machine            = models.CharField("Machine",      max_length=50)
    category           = models.TextField("Category")
    subcategory        = models.TextField("Subcategory")
    code               = models.CharField("Downtime Code",max_length=20,
                                          help_text="Same as subcategory")
    start_epoch        = models.BigIntegerField("Start (epoch)")
    closeout_timestamp = models.DateTimeField("Closed At",  null=True, blank=True)
    comment            = models.TextField("Comment")

    created_at_UTC = models.DateTimeField(auto_now_add=True)
    updated_at_UTC = models.DateTimeField(auto_now=True)

    @property
    def start_at(self) -> _datetime:
        """
        Returns the start timestamp as a Python datetime for easy formatting.
        """
        return _datetime.fromtimestamp(self.start_epoch)

    def __str__(self):
        return f"{self.code} @ {self.start_epoch} on {self.line}/{self.machine}"
    

