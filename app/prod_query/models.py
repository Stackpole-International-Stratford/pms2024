from datetime import date, timedelta
from django.db import models
from django.core.exceptions import ValidationError


# Create your models here.
# id, part, week, year, goal


class Weekly_Production_Goal(models.Model):
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
    machine_id = models.CharField(max_length=50)
    effective_date_unix = models.BigIntegerField()
    target = models.IntegerField()
    line = models.CharField(max_length=50, null=True, blank=True)
    comment = models.TextField(blank=True, null=True)  # NEW

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
