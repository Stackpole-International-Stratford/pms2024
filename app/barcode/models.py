from django.db import models

# Create your models here.


class LaserMark(models.Model):
    """A record of a single barcode scan in the system.

    Attributes:
        part_number (str):
            The part number from the associated `BarCodePUN` record.
        bar_code (str):
            The full scanned barcode; guaranteed unique.
        created_at (datetime.datetime):
            Timestamp when this record was first created.
        grade (str | None):
            One‐letter quality grade ('A'–'F'), or `None` if not yet graded.
        asset (str | None):
            Identifier of the machine or station where the scan occurred.
        unique_portion (str | None):
            The portion of the barcode matched by the PUN’s regex (for quick lookup).
    """
    part_number = models.CharField(max_length=20)
    bar_code = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    grade = models.CharField(max_length=1, null=True)
    asset = models.CharField(max_length=8, null=True)
    unique_portion = models.CharField(max_length=14, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.bar_code


class LaserMarkMeasurementData(models.Model):
    """Holds detailed measurement data for a single LaserMark scan.

    Each LaserMark can have exactly one associated MeasurementData record,
    storing whatever raw or serialized measurement results were captured.

    Attributes:
        laser_mark (LaserMark):
            One-to-one link to the corresponding LaserMark record.
        measurement_data (str):
            Free-form text (e.g. JSON, CSV, or plain text) containing the
            detailed measurements captured during the scan.
    """
    laser_mark = models.OneToOneField(
        LaserMark, on_delete=models.CASCADE, primary_key=True)
    measurement_data = models.TextField()

    class Meta:
        ordering = ['laser_mark']

    def __str__(self):
        return self.laser_mark.bar_code


class LaserMarkDuplicateScan(models.Model):
    """Record the timestamp of a duplicate scan for a LaserMark barcode.

    Attributes:
        laser_mark (LaserMark):
            One-to-one link to the original `LaserMark` record that was scanned again.
        scanned_at (datetime.datetime):
            Timestamp (auto-set at creation) when the duplicate scan occurred.
    """
    laser_mark = models.OneToOneField(
        LaserMark, on_delete=models.CASCADE, primary_key=True)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scanned_at']

    def __str__(self):
        return f'{self.laser_mark.bar_code} scanned at {self.scanned_at}'


class BarCodePUN(models.Model):
    """Define a Part Number Unit (PUN) with its barcode validation pattern and metadata.

    Attributes:
        name (str): A human-readable identifier for this PUN entry.
        part_number (str): The exact part number string this PUN applies to.
        regex (str): The regular expression used to validate scanned barcodes for this part.
        active (bool): Whether this PUN is currently enabled for scanning operations.
        parts_per_tray (int): Expected number of parts per tray when performing batch scans.
    """
    name = models.CharField(max_length=50)
    part_number = models.CharField(max_length=50)
    regex = models.CharField(max_length=120)
    active = models.BooleanField()
    parts_per_tray = models.IntegerField(default=0)

    class Meta:
        ordering = ['part_number']

    def __str__(self):
        return self.name


class DuplicateBarcodeEvent(models.Model):
    """Log an occurrence of a duplicate barcode scan along with unlock details.

    Attributes:
        barcode (str):
            The barcode string that was scanned a second time.
        part_number (str):
            The part number associated with this barcode.
        scan_time (datetime.datetime):
            Original timestamp when the duplicate scan occurred.
        unlock_code (str):
            The three‐character code generated to unlock after a duplicate is detected.
        employee_id (str | None):
            Identifier of the employee who entered the unlock code (nullable until submitted).
        event_time (datetime.datetime):
            Timestamp when this event record was created.
        user_reason (str | None):
            Optional free‐text reason provided by the user for the duplicate scan.
    """
    barcode = models.CharField(max_length=50)
    part_number = models.CharField(max_length=50)
    scan_time = models.DateTimeField()
    unlock_code = models.CharField(max_length=3)
    employee_id = models.CharField(max_length=10, null=True)
    event_time = models.DateTimeField()
    user_reason = models.CharField(max_length=255, null=True)  # Add this field


    class Meta:
        ordering = ['-event_time']

    def __str__(self):
        return f"{self.barcode} scanned at {self.scan_time} with unlock code {self.unlock_code}"



from django.db import models
from django.utils import timezone

class LockoutEvent(models.Model):
    """
    Model to log lockout events and track when and by whom they are unlocked.
    """
    created_at = models.DateTimeField(default=timezone.now)  # Time of the lockout event
    unlock_code = models.CharField(max_length=10)  # Random unlock code for the event
    is_unlocked = models.BooleanField(default=False)  # Status: whether it's unlocked or not
    supervisor_id = models.CharField(max_length=50, null=True, blank=True)  # Supervisor ID who unlocked it
    unlocked_at = models.DateTimeField(null=True, blank=True)  # Time when the event was unlocked
    location = models.CharField(max_length=50, default='Unknown')  # Station location where lockout occurred

    def __str__(self):
        return f"LockoutEvent at {self.location} - {'Unlocked' if self.is_unlocked else 'Locked'}"
