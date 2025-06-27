from django.db import models
from plant.models.setupfor_models import Part  # Importing the Part model
from decimal import Decimal
from django.core.exceptions import ValidationError

class SupervisorAuthorization(models.Model):
    supervisor_id = models.CharField(max_length=256)
    part_number = models.CharField(max_length=256)
    feat_name = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Authorization by {self.supervisor_id} for {self.feat_name} (Part {self.part_number}) at {self.created_at}'

class Feat(models.Model):
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='feat_set')
    name = models.CharField(max_length=256)
    order = models.PositiveIntegerField(default=1)
    alarm = models.IntegerField(default=0)  # New alarm field
    critical = models.BooleanField(default=False)  # New critical field


    class Meta:
        unique_together = ('part', 'name')
        ordering = ['order']

    def __str__(self):
        return f'{self.name} ({self.part})'


class ScrapForm(models.Model):
    partNumber = models.CharField(max_length=256)
    date = models.DateField()
    operator = models.CharField(max_length=256, blank=True, null=True)
    shift = models.IntegerField(blank=True, null=True)
    qtyPacked = models.IntegerField(blank=True, null=True)  # Updated field name
    totalDefects = models.IntegerField(blank=True, null=True)
    totalInspected = models.IntegerField(blank=True, null=True)  # Updated field name
    comments = models.TextField(blank=True, null=True)
    detailOther = models.TextField(blank=True, null=True)
    tpc_number = models.CharField(max_length=256, blank=True, null=True)  # New field for TPC #
    payload = models.JSONField()  # Storing the entire payload as JSON
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Scrap Form {self.id} for Part {self.partNumber}'


class FeatEntry(models.Model):
    scrap_form = models.ForeignKey(ScrapForm, related_name='feat_entries', on_delete=models.CASCADE)
    featName = models.CharField(max_length=256)
    defects = models.IntegerField()
    partNumber = models.CharField(max_length=256)  # Add the partNumber field

    def __str__(self):
        return f'FeatEntry for {self.featName} with {self.defects} defects, Part Number: {self.partNumber}'





from django.db import models
from plant.models.setupfor_models import Part

class PartMessage(models.Model):
    FONT_SIZE_CHOICES = [
        ('small', 'Small'),
        ('medium', 'Medium'),
        ('large', 'Large'),
        ('xl', 'Extra Large'),
        ('xxl', 'Double Extra Large'),
        ('xxxl', 'Triple Extra Large'),
    ]

    part = models.OneToOneField(Part, on_delete=models.CASCADE, related_name='custom_message')
    message = models.TextField(blank=True, null=True)
    font_size = models.CharField(max_length=10, choices=FONT_SIZE_CHOICES, default='medium')  # Default size

    def __str__(self):
        return f"Message for {self.part.part_number}"



# =====================================================
# ===================== QA V2 =========================
# =====================================================

from django.db import models
from plant.models.setupfor_models import Part
from django.utils import timezone
from datetime import timedelta
from django.db.models.signals import post_delete
from django.dispatch import receiver
import os


class QualityPDFDocument(models.Model):
    CATEGORY_CHOICES = [
        ('QA', 'Quality Alerts'),
        ('SI', 'Special Instruction'),
        ('TPC', 'TPC'),
        ('VAC', 'Visual Acceptance Criteria'),
        ('PMR', 'Part Marking Requirement'),
        ('CT', 'Certification Tag'),
        ('SA', 'Safety Alert'),
    ]

    title = models.CharField(max_length=256)
    pdf_file = models.FileField(upload_to='pdfs/')  # Stores the PDF file
    associated_parts = models.ManyToManyField(Part, related_name='pdf_documents')  # Many-to-Many relation with parts
    uploaded_at = models.DateTimeField(auto_now_add=True)
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default='QA')

    def __str__(self):
        return self.title

    def is_new(self):
        # Return True if the PDF was uploaded within the last 8 hours
        return timezone.now() - self.uploaded_at < timedelta(hours=4)

# Automatically delete the PDF file from the media folder when a QualityPDFDocument instance is deleted
@receiver(post_delete, sender=QualityPDFDocument)
def delete_file_on_delete(sender, instance, **kwargs):
    if instance.pdf_file:
        if os.path.isfile(instance.pdf_file.path):
            os.remove(instance.pdf_file.path)


class ViewingRecord(models.Model):
    operator_number = models.CharField(max_length=20)  # Operator's clock number (string for flexibility)
    pdf_document = models.ForeignKey(QualityPDFDocument, on_delete=models.CASCADE, related_name='viewing_records')
    viewed_at = models.DateTimeField(auto_now_add=True)  # Automatically set the timestamp when viewed

    def __str__(self):
        return f"Operator {self.operator_number} viewed {self.pdf_document.title} on {self.viewed_at}"
    






# =================================================================
# =================================================================
# ====================== Red Rabbits ==============================
# =================================================================
# =================================================================

from django.db import models
from plant.models.setupfor_models import Part

class RedRabbitType(models.Model):
    name = models.CharField(max_length=256, unique=True)
    description = models.TextField(blank=True, null=True)  # Optional description
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name="red_rabbit_types", default=1)  # Default to part ID 1

    def __str__(self):
        return f"{self.name} (Part: {self.part.part_number})"



class RedRabbitsEntry(models.Model):
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='red_rabbits_entries')
    red_rabbit_type = models.ForeignKey(RedRabbitType, on_delete=models.CASCADE, related_name='entries', default=1)
    date = models.DateField(auto_now_add=True)
    clock_number = models.CharField(max_length=20)
    shift = models.PositiveSmallIntegerField()
    verification_okay = models.BooleanField()
    supervisor_comments = models.TextField(blank=True, null=True)
    supervisor_id = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.red_rabbit_type} Entry for {self.part.part_number} by {self.clock_number}'








# =================================================================
# =================================================================
# ================ New Scrap System Models ========================
# =================================================================
# =================================================================



class NewScrapSystemScrapCategory(models.Model):
    """New Scrap System – a single record tying Part #, Operation, Category & Cost"""
    part_number = models.CharField(
        "New Scrap System Part Number",
        max_length=100,
        help_text="Enter the part number (free-form)"
    )
    operation = models.CharField(
        "New Scrap System Operation",
        max_length=100,
        help_text="Enter the operation name"
    )
    category = models.CharField(
        "New Scrap System Category",
        max_length=100,
        help_text="Enter the scrap category"
    )
    cost = models.DecimalField(
        "New Scrap System Cost",
        max_digits=10,
        decimal_places=2,
        help_text="Enter the cost for this part/operation/category"
    )

    class Meta:
        verbose_name = "New Scrap System Scrap Category"
        verbose_name_plural = "New Scrap System Scrap Categories"
        db_table = "new_scrap_system_scrap_category"
        unique_together = ("part_number", "operation", "category")
        ordering = ["part_number", "operation", "category"]

    def __str__(self):
        return f"{self.part_number} – {self.operation} – {self.category}: {self.cost}"
    


class NewScrapSystemScrapEntry(models.Model):
    """New Scrap System – every line the operator submits"""
    created_at   = models.DateTimeField(auto_now_add=True)
    machine      = models.CharField("New Scrap System Machine", max_length=100)

    # free-text so the view can copy them straight from the operator;
    # switch to FK if you have master tables
    part_number  = models.CharField("New Scrap System Part #",  max_length=100)
    operation    = models.CharField("New Scrap System Operation", max_length=100)
    category     = models.CharField("New Scrap System Category",  max_length=100)

    quantity     = models.PositiveIntegerField("New Scrap System Qty")
    unit_cost    = models.DecimalField("New Scrap System $/unit", max_digits=10, decimal_places=2)
    total_cost   = models.DecimalField("New Scrap System Total $", max_digits=12, decimal_places=2,
                                       editable=False)

    class Meta:
        db_table = "new_scrap_system_scrap_entry"
        verbose_name = "New Scrap System Scrap Entry"
        verbose_name_plural = "New Scrap System Scrap Entries"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # If price wasn’t filled in the form, pull it from the master price table
        if self.unit_cost in (None, 0):
            price = (
                NewScrapSystemScrapCategory.objects
                .filter(part_number=self.part_number,
                        operation=self.operation,
                        category=self.category)
                .values_list("cost", flat=True)
                .first()
            )
            if price is None:
                raise ValidationError("No unit cost found for this part/operation/category.")
            self.unit_cost = price

        self.total_cost = (self.unit_cost or Decimal("0")) * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d} | {self.machine} | {self.part_number} | " \
               f"{self.operation} | {self.category} × {self.quantity} = {self.total_cost}"