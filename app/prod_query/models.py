from datetime import date, timedelta
from django.db import models
from django.core.exceptions import ValidationError


# Create your models here.
# id, part, week, year, goal


class Weekly_Production_Goal(models.Model):
    """
    Define a weekly production target for a given part.

    Fields
    ------
    part_number : str
        Identifier of the part (e.g., "555-22").
    week : int
        ISO week number (1–53) for which this goal applies.
    year : int
        Four-digit year of the goal.
    goal : int
        Target production quantity for that week.

    Methods
    -------
    __str__()
        Returns a human-readable description in the format:
        "{part_number}, week of: YYYY-MM-DD" where the date is the Sunday
        of the specified ISO week and year.

    Meta
    ----
    ordering : list
        Default ordering by descending year, then descending week.
    unique_together : tuple (commented out)
        Intended to enforce one record per (part_number, week, year), but
        currently disabled due to a migration conflict.
    """
    part_number = models.CharField(max_length=20)
    week = models.IntegerField()
    year = models.IntegerField()
    goal = models.IntegerField()

    def __str__(self):
        #display weekly_production_goal as something other than 'object(x)' in admin view
        #part number, week of: day/month/year
        #day is sunday which based on isocalendar is 7
        iso_sunday = 7
        date_for_string = date.fromisocalendar(self.year, self.week, iso_sunday)
            
        return f'{self.part_number}, week of: {date_for_string}'

    class Meta:
        ordering = ["-year", "-week"]
        # migration failed for following restraint ... 
        # django.db.utils.IntegrityError: (1062, "Duplicate entry '555-22-2023' for key 'prod_query_weekly_production_goal.prod_query_weekly_produc_part_number_week_year_fe916b4d_uniq'")
        # unique_together = ('part_number', 'week', 'year')





class OAMachineTargets(models.Model):
    """
    Store production targets for machines, with support for soft deletion and comment validation.

    Fields
    ------
    machine_id : str
        Identifier of the machine.
    effective_date_unix : int
        Unix epoch timestamp when this target takes effect.
    target : int
        Production target value.
    line : str, optional
        Production line identifier (nullable).
    part : str, optional
        Part identifier associated with this target (nullable).
    comment : str, optional
        Free-form comment; must not exceed 100 words.
    isDeleted : bool
        Soft-delete flag (False = visible, True = hidden).
    created_at : datetime
        Timestamp when the record was created (auto-populated).

    Methods
    -------
    clean()
        Ensures that `comment`, if provided, does not exceed 100 words.
    __str__()
        Returns a human-readable summary:
        "Machine {machine_id}, Target {target}, Line {line}, Effective {effective_date_unix}".
    """
    machine_id = models.CharField(max_length=50)
    effective_date_unix = models.BigIntegerField()
    target = models.IntegerField()
    line = models.CharField(max_length=50, null=True, blank=True)
    part = models.CharField(max_length=50, null=True, blank=True) # NEW
    comment = models.TextField(blank=True, null=True)  


    # New “soft‐delete” flag: 0 = visible, 1 = deleted
    isDeleted = models.BooleanField(
        default=False,
        help_text="Soft‑delete flag; set to True to hide this record"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.comment:
            # simple word count
            word_count = len(self.comment.split())
            if word_count > 100:
                raise ValidationError({
                    'comment': f'Comment cannot exceed 100 words (you have {word_count}).'
                })

    def __str__(self):
        return (f"Machine {self.machine_id}, Target {self.target}, "
                f"Line {self.line}, Effective {self.effective_date_unix}")
