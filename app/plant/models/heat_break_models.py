# models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

def unix_now() -> int:
    # timezone-aware, migration-serializable callable
    return int(timezone.now().timestamp())

class HeatBreak(models.Model):
    machine = models.ForeignKey("DowntimeMachine", on_delete=models.CASCADE, related_name="heat_breaks")
    duration_minutes = models.PositiveIntegerField()

    start_time_epoch = models.BigIntegerField(default=unix_now)
    end_time_epoch = models.BigIntegerField(null=True, blank=True)

    turned_on_by_username = models.CharField(max_length=150, null=True, blank=True)
    turned_off_by_username = models.CharField(max_length=150, null=True, blank=True)

    created_at_epoch = models.BigIntegerField(default=unix_now, editable=False)
    updated_at_epoch = models.BigIntegerField(default=unix_now, editable=False)

    class Meta:
        ordering = ["-created_at_epoch"]
