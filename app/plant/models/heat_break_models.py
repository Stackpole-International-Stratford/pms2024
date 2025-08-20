# models.py
from django.db import models
from django.conf import settings  # for linking to Django's User model
from django.utils import timezone

class HeatBreak(models.Model):
    machine = models.ForeignKey("DowntimeMachine", on_delete=models.CASCADE, related_name="heat_breaks")
    duration_minutes = models.PositiveIntegerField()  # 15, 30, 45
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)

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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.machine} Heat Break ({self.start_time} - {self.end_time or 'Active'})"
