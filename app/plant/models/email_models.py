# your_app/models.py

from django.conf import settings
from django.db import models


class EmailRecipient(models.Model):
    """
    A single email address (optionally with a name) that can be reused
    across multiple email campaigns.
    """
    email = models.EmailField(unique=True)
    name  = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name or self.email


class EmailCampaign(models.Model):
    """
    An email campaign: has a name, optional description, a set of
    EmailRecipients, and a set of Users who are allowed to manage it.
    """
    name        = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)

    # Recipients of this campaign
    recipients = models.ManyToManyField(
        EmailRecipient,
        related_name="email_campaigns",
        blank=True,
    )

    # Users who can edit this campaign
    editors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="editable_email_campaigns",
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
