from django.db import models

class PlantSpine(models.Model):
    line_name                  = models.TextField()
    operation                  = models.TextField()
    machine_name               = models.TextField()
    part_number                = models.TextField()
    cycle_time                 = models.FloatField()
    cycle_time_effective_date  = models.BigIntegerField(
        help_text="Epoch timestamp (in seconds) when this cycle time takes effect"
    )
    created_at                 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = 'plant_spine'
        ordering            = ['-created_at']
        verbose_name        = 'Plant Spine'
        verbose_name_plural = 'Plant Spine'

    def __str__(self):
        return (
            f"{self.line_name} | {self.operation} | "
            f"{self.machine_name} | {self.part_number} @ {self.cycle_time}s "
            f"(effective {self.cycle_time_effective_date})"
        )
