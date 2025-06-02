# plant/models/plantSpine_models.py

from django.db import models

class PlantSpine(models.Model):
    """
    Stores the entire lines → operations → machines structure as JSON.
    """
    name = models.CharField(
        max_length=50,
        unique=True,
        default="default",
        help_text="Identifier for this configuration (e.g. 'default')"
    )
    data = models.JSONField(
        default=list,
        help_text="Full lines → operations → machines nested structure"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this JSON blob was last modified"
    )

    class Meta:
        db_table            = 'plant_spine'
        verbose_name        = 'Plant Spine Config'
        verbose_name_plural = 'Plant Spine Configs'

    def __str__(self):
        return self.name
