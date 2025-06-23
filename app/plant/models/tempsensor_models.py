from django.db import models
import pytz
from django.utils import timezone

class TempSensorEmailList(models.Model):
    email = models.EmailField(
        unique=True,
        help_text="Email address to receive temp sensor alerts"
    )

    # new—store the last‐sent time as an integer epoch (seconds since 1970)
    email_sent = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Last alert sent (epoch seconds)"
    )

    def __str__(self):
        return self.email

    class Meta:
        verbose_name = "Temp Sensor Email"
        verbose_name_plural = "Temp Sensor Email List"


class HeatBreakEntry(models.Model):
    AREA_CHOICES = [
        ('1', 'Area 1'),
        ('2', 'Area 2'),
        ('3', 'Area 3'),
    ]

    first_name = models.CharField(max_length=50)
    last_name  = models.CharField(max_length=50)
    area       = models.CharField(max_length=1, choices=AREA_CHOICES)
    timestamp  = models.DateTimeField()

    def __str__(self):
        return f"{self.first_name} {self.last_name} – Area {self.area}"