# plant/models/maintenance_models.py

from django.db import models
from datetime import datetime as _datetime
from django.utils import timezone


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
    closeout_epoch     = models.BigIntegerField("Closeout (epoch)", null=True, blank=True)
    comment            = models.TextField("Comment")

    # new soft-delete fields
    is_deleted         = models.BooleanField(default=False)
    deleted_at         = models.DateTimeField(null=True, blank=True)

    created_at_UTC     = models.DateTimeField(auto_now_add=True)
    updated_at_UTC     = models.DateTimeField(auto_now=True)

    @property
    def start_at(self) -> _datetime:
        """
        Returns the start timestamp as a Python datetime for easy formatting.
        """
        return _datetime.fromtimestamp(self.start_epoch)

    def delete(self, using=None, keep_parents=False):
        """
        Soft-delete: mark the row as deleted instead of actually deleting.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def __str__(self):
        return f"{self.code} @ {self.start_epoch} on {self.line}/{self.machine}"