from django.db import models
from django.utils import timezone
import time


class Asset(models.Model):
    """
    Represents a physical asset with a unique identifier and optional descriptive name.

    Fields
    ------
    asset_number : str
        Unique code or number identifying the asset.
    asset_name : str, optional
        Human-readable name or description of the asset.
    Methods
    -------
    __str__()
        Returns "{asset_number} - {asset_name}" for display.
    """
    asset_number = models.CharField(max_length=100)
    asset_name = models.CharField(max_length=256, null=True, blank=True)

    def __str__(self):
        return f"{self.asset_number} - {self.asset_name}"


class Part(models.Model):
    """
    Represents a part with a unique identifier and optional descriptive name.

    Fields
    ------
    part_number : str
        Unique code or number identifying the part.
    part_name : str, optional
        Human-readable name or description of the part.
    Methods
    -------
    __str__()
        Returns "{part_number} - {part_name}" for display.
    """
    part_number = models.CharField(max_length=100)
    part_name = models.CharField(max_length=256, null=True, blank=True)

    def __str__(self):
        return f"{self.part_number} - {self.part_name}"


class SetupForManager(models.Manager):
    """
    Custom manager for SetupFor records, providing lookups by asset and time.

    Methods
    -------
    get_part_at_time(asset_number: str, timestamp: int) -> Part or None
        Returns the Part assigned to the given asset at or before the specified epoch,
        or None if no setup record exists.
    """
    def get_part_at_time(self, asset_number, timestamp):
        try:
            setup = (
                self.filter(asset__asset_number=asset_number, since__lte=timestamp)
                    .order_by('-since')
                    .first()
            )
            return setup.part if setup else None
        except self.model.DoesNotExist:
            return None


def current_epoch():
    """
    Utility function to return the current time as Unix epoch seconds (int).

    Returns
    -------
    int
        The current timestamp in seconds since the Unix epoch.
    """
    return int(time.time())


class SetupFor(models.Model):
    """
    Records which Part is set up on an Asset starting at a specific time.

    Fields
    ------
    asset : ForeignKey to Asset
        The asset that was set up.
    part : ForeignKey to Part
        The part that was installed on the asset.
    created_at : int
        Epoch timestamp when this record was created (auto-populated).
    since : int
        Epoch timestamp indicating when the part setup took effect.

    Methods
    -------
    __str__()
        Returns a string in the format "{asset_number} setup for {part_number}".
    """
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    part = models.ForeignKey(Part, on_delete=models.CASCADE)
    created_at = models.BigIntegerField(default=current_epoch, editable=False)
    since = models.BigIntegerField()

    def __str__(self):
        return f'{self.asset.asset_number} setup for {self.part.part_number}'




# ===============================================================================================
# ===============================================================================================
# =================== Example Usage Syntax for Manager Elsewhere in Django app ==================
# ===============================================================================================
# ===============================================================================================

# def get_asset_part_view(request):
#     """
#     Example view to demonstrate using the SetupForManager from a different application.

#     Args:
#     request (HttpRequest): The request object containing GET parameters 'asset_number' and 'timestamp'.

#     Returns:
#     HttpResponse: The part number or a message indicating no part found.
#     """
#     asset_number = request.GET.get('asset_number')
#     timestamp_str = request.GET.get('timestamp')

#     if asset_number and timestamp_str:
#         try:
#             # Convert timestamp string to datetime object
#             timestamp = timezone.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

#             # Use the custom manager to get the part
#             part = SetupFor.setupfor_manager.get_part_at_time(asset_number, timestamp)

#             # Check if part is found and return appropriate response
#             if part:
#                 return HttpResponse(f'The part at the given time was: {part.part_number}')
#             else:
#                 return HttpResponse('No part found for the given asset at the specified time.')
#         except Exception as e:
#             return HttpResponse(f'Error: {str(e)}')
#     else:
#         return HttpResponse('Please provide both asset_number and timestamp as GET parameters.')






class AssetCycleTimes(models.Model):
    """
    Record the cycle time of a specific part on an asset, effective from a given date.

    Fields
    ------
    asset : ForeignKey to Asset
        The asset to which this cycle time applies.
    part : ForeignKey to Part
        The part on the asset for which the cycle time is recorded.
    cycle_time : float
        The measured cycle time in seconds.
    effective_date : int
        Epoch timestamp (seconds since Unix epoch) indicating when this cycle time becomes effective.
    created_at : datetime
        Timestamp when the record was created (auto-populated).

    Methods
    -------
    __str__()
        Returns a string in the format:
        "{asset_number} - {part_number} - {cycle_time}s (Effective: {effective_date})"
    """
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    part = models.ForeignKey(Part, on_delete=models.CASCADE)
    cycle_time = models.FloatField()
    effective_date = models.BigIntegerField()  # Storing as an epoch timestamp
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.asset.asset_number} - {self.part.part_number} - {self.cycle_time}s (Effective: {self.effective_date})"
