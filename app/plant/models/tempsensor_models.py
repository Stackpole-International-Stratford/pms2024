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


class SentHeatBreakEntry(models.Model):
    zone                  = models.IntegerField()
    humidex               = models.FloatField()
    recommendation        = models.CharField(max_length=100)
    sent_on_break_epoch   = models.BigIntegerField(
                              null=True,
                              blank=True,
                              help_text="Timestamp (in seconds since epoch) when supervisor actually sent them on break"
                            )
    supervisor_id         = models.IntegerField(
                              null=True,
                              blank=True,
                              help_text="ID of the supervisor who sent them on break"
                            )
    created_at            = models.DateTimeField(
                              auto_now_add=True,
                              help_text="When this alert was recorded in the DB"
                            )

    def __str__(self):
        return f"Zone {self.zone} @ {self.humidex} → {self.recommendation}"