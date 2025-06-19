from django.db import models

class TrainingJob(models.Model):
    AREA_1 = 1
    AREA_2 = 2
    AREA_3 = 3
    AREA_CHOICES = [
        (AREA_1, "Area 1"),
        (AREA_2, "Area 2"),
        (AREA_3, "Area 3"),
    ]

    area        = models.IntegerField(choices=AREA_CHOICES)
    line        = models.CharField(max_length=50, help_text="Which line this job runs on")
    operation   = models.CharField(max_length=100, help_text="Operation name or code")
    description = models.TextField(help_text="Describe the job")

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_area_display()} – {self.line} – {self.operation}"
