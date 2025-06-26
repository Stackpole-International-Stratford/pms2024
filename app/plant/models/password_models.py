# password_models.py
from django.db import models
from django.utils import timezone
from ..models.setupfor_models import Asset  # Import the Asset model

class Password(models.Model):
    """
    Store credentials associated with an asset, supporting soft-deletion.

    Fields
    ------
    password_asset : ForeignKey to Asset
        The related asset for which this credential applies.
    label : str
        A human-readable label for the credential (e.g., "Admin Panel").
    username : str or None
        Optional username for the credential; may be null or blank.
    password : str
        The secret value (password) itself.
    created_at : datetime
        Timestamp when this record was created (auto-populated).
    deleted : bool
        Soft-delete flag; True if the credential has been “deleted” without removal.
    deleted_at : datetime or None
        Timestamp when the record was soft-deleted, or None if still active.

    Methods
    -------
    __str__()
        Returns a string in the format:
        "{asset_number} - {label} - {username or 'No Username'}".
    delete(*args, **kwargs)
        Overrides default delete to perform a soft-delete by setting `deleted`
        to True and stamping `deleted_at` instead of removing the row.
    """
    password_asset = models.ForeignKey(Asset, on_delete=models.CASCADE, default=1)  # Changed from machine to password_asset
    label = models.CharField(max_length=100)
    username = models.CharField(max_length=100, blank=True, null=True)
    password = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.password_asset.asset_number} - {self.label} - {self.username or 'No Username'}"

    def delete(self, *args, **kwargs):
        self.deleted = True
        self.deleted_at = timezone.now()
        self.save()
