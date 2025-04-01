from django.db import models
from django.utils import timezone
import time


class Asset(models.Model):
    asset_number = models.CharField(max_length=100)
    asset_name = models.CharField(max_length=256, null=True, blank=True)  # Updated to varchar(256)

    def __str__(self):
        return f"{self.asset_number} - {self.asset_name}"

class Part(models.Model):
    part_number = models.CharField(max_length=100)
    part_name = models.CharField(max_length=256, null=True, blank=True)  # Updated to varchar(256)

    def __str__(self):
        return f"{self.part_number} - {self.part_name}"


class SetupForManager(models.Manager):
    def get_part_at_time(self, asset_number, timestamp):
        try:
            setup = self.filter(asset__asset_number=asset_number, since__lte=timestamp).order_by('-since').first()
            return setup.part if setup else None
        except self.model.DoesNotExist:
            return None


def current_epoch():
    return int(time.time())

class SetupFor(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    part = models.ForeignKey(Part, on_delete=models.CASCADE)
    created_at = models.BigIntegerField(default=current_epoch, editable=False)
    since = models.BigIntegerField()  # Or adjust as needed

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
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    part = models.ForeignKey(Part, on_delete=models.CASCADE)
    cycle_time = models.FloatField()
    effective_date = models.BigIntegerField()  # Storing as an epoch timestamp
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.asset.asset_number} - {self.part.part_number} - {self.cycle_time}s (Effective: {self.effective_date})"
