from django.db import models

class TempSensorEmailList(models.Model):
    """
    Stores email addresses subscribed to temperature sensor alerts, with tracking of the last alert sent.

    Fields
    ------
    email : str
        Unique email address to receive temperature sensor alert notifications.
    email_sent : int or None
        Epoch timestamp (seconds since Unix epoch) of the last alert email successfully sent,
        or None if no alert has been sent yet.

    Methods
    -------
    __str__()
        Returns the email address for display.
    """
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
