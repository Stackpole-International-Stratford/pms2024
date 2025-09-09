
from django.db import models
from datetime import datetime as _datetime
from django.utils import timezone
from django.conf import settings
from datetime import datetime

class MachineDowntimeEventNEWTEST(models.Model):
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

    # 🔥 NEW: store the generated work-order ID from the API
    work_order_id      = models.IntegerField(
        "Work Order #",
        null=True,
        blank=True,
        default=None,
        help_text="ID returned by the work-order API"
    )

    closedout_by = models.CharField(
        "Closed-out By",
        max_length=150,
        null=True,
        blank=True,
        help_text="Username of the person who closed out the downtime event"
    )

    # new:
    LABOUR_CHOICES = [
        ('ELECTRICIAN', 'Need Electrician'),
        ('TECH',        'Need Tech'),
        ('MILLWRIGHT',  'Need Millwright'),
        ('PLCTECH',     'Need PLC Technician'),
        ('IMT',         'Need IMT'),
        ('PLUMBER',     'Need Plumber'),
        ('WFP',         'Need Parts'),
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
            return _datetime.fromtimestamp(self.closeout_epoch)
        return None

    def __str__(self):
        return f"{self.code} @ {self.start_epoch} on {self.line}/{self.machine}"





class LinePriorityNEWTEST(models.Model):
    """
    A single Line and its priority (lower = more urgent).
    """
    line     = models.CharField(max_length=50, unique=True)
    priority = models.PositiveIntegerField(default=0, help_text="Lower numbers are higher priority")

    class Meta:
        ordering = ['priority']

    def __str__(self):
        return f"{self.line} (prio {self.priority})"




class DowntimeParticipationNEWTEST(models.Model):
    event = models.ForeignKey(
        MachineDowntimeEventNEWTEST,
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





class DowntimeCodeNEWTEST(models.Model):
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




class AreaZoneNEWTEST(models.Model):
        """
        Defines an optional area/zone grouping for machines.
        """
        name        = models.CharField("Area/Zone", max_length=100, unique=True)
        description = models.TextField("Description", blank=True, default="")

        created_at_UTC = models.DateTimeField(auto_now_add=True)
        updated_at_UTC = models.DateTimeField(auto_now=True)

        class Meta:
            ordering = ['name']
            verbose_name = "Area / Zone"
            verbose_name_plural = "NEWTEST Area / Zones"

        def __str__(self):
            return self.name


class DowntimeMachineNEWTEST(models.Model):
    line           = models.CharField("Line", max_length=50)
    operation      = models.CharField("Operation", max_length=100)
    machine_number = models.CharField("Machine #", max_length=50)
    is_tracked     = models.BooleanField("Tracked?", default=True)

    # 🔥 new
    areazone = models.ForeignKey(
        AreaZoneNEWTEST,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="machines",
        help_text="Optional Area/Zone this machine belongs to",
    )

    created_at_UTC = models.DateTimeField(auto_now_add=True)
    updated_at_UTC = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('line', 'operation', 'machine_number')
        ordering = ['line', 'operation', 'machine_number']
        verbose_name = "Downtime Machine"
        verbose_name_plural = "NEWTEST Downtime Machines"

    def __str__(self):
        return f"{self.line} / {self.operation} / #{self.machine_number}"

    
