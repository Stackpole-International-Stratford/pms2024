# models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

def unix_now() -> int:
    # timezone-aware, migration-serializable callable
    return int(timezone.now().timestamp())

class HeatBreak(models.Model):
    machine = models.ForeignKey("DowntimeMachine", on_delete=models.CASCADE, related_name="heat_breaks")
    duration_minutes = models.PositiveIntegerField()  # 15, 30, 45

    # epoch fields
    start_time_epoch = models.BigIntegerField(default=unix_now)
    end_time_epoch = models.BigIntegerField(null=True, blank=True)

    turned_on_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="heatbreaks_started",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    turned_off_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="heatbreaks_stopped",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    created_at_epoch = models.BigIntegerField(default=unix_now, editable=False)
    updated_at_epoch = models.BigIntegerField(default=unix_now, editable=False)

    class Meta:
        ordering = ["-created_at_epoch"]

    def save(self, *args, **kwargs):
        self.updated_at_epoch = unix_now()
        super().save(*args, **kwargs)

    def __str__(self):
        end_display = self.end_time_epoch if self.end_time_epoch is not None else "Active"
        return f"{self.machine} Heat Break ({self.start_time_epoch} - {end_display})"
