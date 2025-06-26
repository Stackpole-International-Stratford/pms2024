# plant/models/maintenance_models.py

from django.db import models
from datetime import datetime as _datetime
from django.utils import timezone
from django.conf import settings
from datetime import datetime




class MachineDowntimeEvent(models.Model):
    """
    Represents a single downtime event on a production line, with support for soft-deletion,
    labour requirements, and tracking of participant actions.

    Fields
    ------
    line : str
        Production line identifier.
    machine : str
        Machine identifier within the line.
    category : str
        High-level category of the downtime.
    subcategory : str
        Optional sub-category (defaults to empty string).
    code : str
        Downtime code (typically matches subcategory if provided).
    start_epoch : int
        Event start time expressed as seconds since the Unix epoch.
    closeout_epoch : int or None
        Event close-out time as epoch seconds, or None if not yet closed out.
    comment : str
        Description or notes about the downtime event.
    is_deleted : bool
        Soft-delete flag; True if the record has been “deleted” without removal.
    deleted_at : datetime or None
        Timestamp when the record was soft-deleted, or None.
    created_at_UTC : datetime
        Auto-populated creation timestamp (UTC).
    updated_at_UTC : datetime
        Auto-populated last-modified timestamp (UTC).
    labour_types : list of str
        JSON field listing one or more labour role codes required
        (choices defined in LABOUR_CHOICES).
    employee_id : str or None
        Optional identifier of the person who logged the downtime.
    closeout_comment : str or None
        Notes added at close-out describing corrective actions taken.

    Class Attributes
    ----------------
    LABOUR_CHOICES : list of tuple
        Permissible labour role codes and their human-readable labels.

    Properties
    ----------
    start_at : datetime
        Converts `start_epoch` into a Python `datetime` for display or formatting.
    closeout_at : datetime or None
        Converts `closeout_epoch` into a `datetime`, or returns None if not set.

    Methods
    -------
    delete(using=None, keep_parents=False)
        Overrides Model.delete() to perform a soft-delete by setting `is_deleted`
        and stamping `deleted_at` instead of removing the record.
    __str__()
        Returns a concise string representation: 
        "{code} @ {start_epoch} on {line}/{machine}".
    """
    """
    Represents a single downtime event on a production line.
    """
    line               = models.CharField("Line",         max_length=50)
    machine            = models.CharField("Machine",      max_length=50)
    category           = models.TextField("Category")
    subcategory        = models.TextField(
        "Subcategory",
        blank=True,
        default="",
        help_text="Optional sub-category"
    )
    code               = models.CharField(
        "Downtime Code",
        max_length=20,
        blank=True,
        default="",
        help_text="Optional, same as subcategory if provided"
    )
    start_epoch        = models.BigIntegerField("Start (epoch)")
    closeout_epoch     = models.BigIntegerField("Closeout (epoch)", null=True, blank=True)
    comment            = models.TextField("Comment")

    # new soft-delete fields
    is_deleted         = models.BooleanField(default=False)
    deleted_at         = models.DateTimeField(null=True, blank=True)

    created_at_UTC     = models.DateTimeField(auto_now_add=True)
    updated_at_UTC     = models.DateTimeField(auto_now=True)

    # new:
    LABOUR_CHOICES = [
        ('ELECTRICIAN', 'Need Electrician'),
        ('TECH',        'Need Tech'),
        ('MILLWRIGHT',  'Need Millwright'),
        ('PLCTECH',    'Need PLC Technician'),
        ('IMT',        'Need IMT'),
        ('NA',          'N/A'),
    ]
    labour_types = models.JSONField(
        default=list,
        blank=True,
        help_text="List of labour roles needed (one or more of OPERATOR,ELECTRICIAN,TECH,MILLWRIGHT)"
    )
    employee_id = models.TextField(
        "Employee ID",
        null=True,
        blank=True,
        help_text="(optional) ID of the person who logged this downtime"
    )
    closeout_comment = models.TextField(
        "Close-out Comment",
        null=True,
        blank=True,
        help_text="What the labourer did to fix the issue when closing out",
    )

    @property
    def start_at(self) -> _datetime:
        """
        Returns the start timestamp as a Python datetime for easy formatting.
        """
        return _datetime.fromtimestamp(self.start_epoch)

    def delete(self, using=None, keep_parents=False):
        """
        Soft-delete: mark the row as deleted instead of actually deleting.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    @property
    def closeout_at(self):
        """
        Returns a datetime if closeout_epoch is set,
        else None.
        """
        if self.closeout_epoch:
            return datetime.fromtimestamp(self.closeout_epoch)
        return None

    def __str__(self):
        return f"{self.code} @ {self.start_epoch} on {self.line}/{self.machine}"
    

    




class LinePriority(models.Model):
    """
    Map a production line to its urgency priority.

    Each instance represents a single production line and an associated
    priority value, where lower numbers indicate higher urgency.

    Fields
    ------
    line : str
        Unique identifier for the production line.
    priority : int
        Urgency level of the line (lower numbers are higher priority).

    Meta
    ----
    ordering = ['priority']
        Default queryset ordering by ascending priority.

    Methods
    -------
    __str__()
        Returns a human-readable string in the format "{line} (prio {priority})".
    """
    """
    A single Line and its priority (lower = more urgent).
    """
    line     = models.CharField(max_length=50, unique=True)
    priority = models.PositiveIntegerField(default=0, help_text="Lower numbers are higher priority")

    class Meta:
        ordering = ['priority']

    def __str__(self):
        return f"{self.line} (prio {self.priority})"




class DowntimeParticipation(models.Model):
    """
    Track a user’s participation in a machine downtime event, including join/leave times and comments.

    Fields
    ------
    event : ForeignKey to MachineDowntimeEvent
        The downtime event this participation pertains to.
    user : ForeignKey to AUTH_USER_MODEL
        The user who joined the event.
    join_epoch : int
        The timestamp (seconds since Unix epoch) when the user joined.
    leave_epoch : int or None
        The timestamp when the user left; null if still active.
    join_comment : str
        Optional note provided by the user upon joining.
    leave_comment : str or None
        Optional note provided by the user upon leaving.
    total_minutes : int or None
        The computed duration of participation in minutes; null until set.

    Meta
    ----
    ordering = ['-join_epoch']
        Participation records are ordered by most recent join first.
    unique_together = ('event', 'user', 'join_epoch')
        Prevents duplicate participation entries for the same event, user, and join time.

    Methods
    -------
    (Uses default Django ORM methods; no custom methods defined.)
    """
    event = models.ForeignKey(
        MachineDowntimeEvent,
        related_name='participants',
        on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    join_epoch     = models.BigIntegerField()
    leave_epoch    = models.BigIntegerField(null=True, blank=True)
    join_comment   = models.TextField(blank=True, default='')
    leave_comment  = models.TextField(null=True, blank=True)
    total_minutes  = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-join_epoch']
        # If you want to prevent duplicates:
        unique_together = ('event', 'user', 'join_epoch')





class DowntimeCode(models.Model):
    """
    Lookup table for downtime codes, mapping each unique code to its category and subcategory.

    Fields
    ------
    code : str
        Unique downtime code identifier (e.g., "MECH-TOOL").
    category : str
        High-level category description (e.g., "Mechanical / Equipment Failure").
    subcategory : str
        Detailed, human-readable subcategory (e.g., "Tooling Failure").
    updated_at : datetime
        Timestamp of the last change to this record (auto-updated).

    Meta
    ----
    ordering : list
        Default ordering by category, then subcategory, then code.
    verbose_name : str
        Singular display name "Downtime Code".
    verbose_name_plural : str
        Plural display name "Downtime Codes".

    Methods
    -------
    __str__()
        Returns a string in the format:
        "{code}: {category} → {subcategory}".
    """
    """
    Lookup table for all downtime codes, with their category
    and subcategory, plus a last‐updated stamp.
    """
    code = models.CharField(
        "Code",
        max_length=20,
        unique=True,
        help_text="Unique downtime code, e.g. MECH-TOOL"
    )
    category = models.CharField(
        "Category",
        max_length=100,
        help_text="High‐level category, e.g. Mechanical / Equipment Failure"
    )
    subcategory = models.CharField(
        "Subcategory",
        max_length=100,
        help_text="Human‐readable subcategory, e.g. Tooling Failure"
    )
    updated_at = models.DateTimeField(
        "Last Updated",
        auto_now=True,
        help_text="When this lookup row was last changed"
    )

    class Meta:
        ordering = ['category', 'subcategory', 'code']
        verbose_name = "Downtime Code"
        verbose_name_plural = "Downtime Codes"

    def __str__(self):
        return f"{self.code}: {self.category} → {self.subcategory}"




class DowntimeMachine(models.Model):
    """
    Master list of all machines available for downtime tracking, organized by line and operation.

    Fields
    ------
    line : str
        Production line identifier where this machine is located.
    operation : str
        Name of the operation or process performed by the machine.
    machine_number : str
        Unique machine identifier or code within the line/operation.
    is_tracked : bool
        Flag indicating whether downtime should be recorded for this machine.
    created_at_UTC : datetime
        Timestamp (UTC) when this machine record was created.
    updated_at_UTC : datetime
        Timestamp (UTC) when this machine record was last updated.

    Meta
    ----
    unique_together : tuple
        Ensures that (line, operation, machine_number) is unique.
    ordering : list
        Default ordering by line, then operation, then machine_number.
    verbose_name : str
        Singular name "Downtime Machine".
    verbose_name_plural : str
        Plural name "Downtime Machines".

    Methods
    -------
    __str__()
        Returns a string in the format:
        "{line} / {operation} / #{machine_number}".
    """
    """
    Master list of all machines you can track downtime against.
    """
    line           = models.CharField(
        "Line",
        max_length=50,
        help_text="Production line this machine lives on",
    )
    operation      = models.CharField(
        "Operation",
        max_length=100,
        help_text="Operation or process name",
    )
    machine_number = models.CharField(
        "Machine #",
        max_length=50,
        help_text="Unique number or code for the machine",
    )
    is_tracked     = models.BooleanField(
        "Tracked?",
        default=True,
        help_text="Whether downtime is being recorded for this machine",
    )
    created_at_UTC = models.DateTimeField(
        auto_now_add=True,
        help_text="When this machine record was created (UTC)",
    )
    updated_at_UTC = models.DateTimeField(
        auto_now=True,
        help_text="When this machine record was last updated (UTC)",
    )

    class Meta:
        unique_together = ('line', 'operation', 'machine_number')
        ordering = ['line', 'operation', 'machine_number']
        verbose_name = "Downtime Machine"
        verbose_name_plural = "Downtime Machines"

    def __str__(self):
        return f"{self.line} / {self.operation} / #{self.machine_number}"