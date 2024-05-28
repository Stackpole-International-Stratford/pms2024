from datetime import date, timedelta
from django.db import models

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
