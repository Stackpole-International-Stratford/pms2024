from django.db import models

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
