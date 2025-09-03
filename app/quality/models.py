from django.db import models
from plant.models.setupfor_models import Part  # Importing the Part model
from decimal import Decimal
from django.core.exceptions import ValidationError
from plant.models.setupfor_models import Asset
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import JSONField


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


class Program(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ("name",)

class ScrapCategory(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Scrap categories"

class ScrapSystemOperation(models.Model):
    # NEW: each op can belong to one or more programs
    programs = models.ManyToManyField(Program, blank=True, related_name="operations")

    # existing fields
    assets = models.ManyToManyField(Asset, blank=True)
    scrap_categories = models.ManyToManyField(ScrapCategory, blank=True)

    part_number = models.CharField(max_length=100)
    operation   = models.CharField(max_length=256)
    cost        = models.DecimalField(max_digits=10, decimal_places=2)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.part_number} – {self.operation}"

class ScrapSubmission(models.Model):
    # (unchanged)
    scrap_system_operation = models.ForeignKey(
        ScrapSystemOperation,
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='scrap_submissions'
    )
    scrap_category = models.ForeignKey(
        ScrapCategory,
        on_delete=models.CASCADE,
        related_name='scrap_submissions'
    )

    # denormalized fields for reporting (unchanged)
    part_number     = models.CharField(max_length=100)
    machine         = models.CharField(max_length=100)
    operation_name  = models.CharField(max_length=256)
    category_name   = models.CharField(max_length=100)
    came_from_op    = models.CharField(
        max_length=256,
        blank=True,
        default='',
        null=False,
        help_text='Optional: operation where this scrap originated'
    )

    operator_number = models.CharField(max_length=50)

    quantity   = models.PositiveIntegerField()
    unit_cost  = models.DecimalField(max_digits=10, decimal_places=2)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"{self.part_number} @ {self.machine} – "
            f"{self.operation_name}/{self.category_name} "
            f"(qty {self.quantity})"
        )
    





# ==========================================================================
# ==========================================================================
# ======================= TPC Requests =====================================
# ==========================================================================
# ==========================================================================

class TPCRequest(models.Model):
    date_requested   = models.DateField(default=timezone.now)
    issuer_name      = models.CharField(max_length=120)
    parts            = models.JSONField(default=list)
    reason           = models.CharField(max_length=200)
    process          = models.CharField(max_length=120)
    supplier_issue   = models.BooleanField(default=False)
    machines         = models.JSONField(default=list)
    reason_note      = models.TextField(blank=True)
    feature          = models.CharField(max_length=120, blank=True)
    current_process  = models.TextField(blank=True)
    changed_to       = models.TextField(blank=True)
    expiration_date  = models.DateTimeField()

    # approvals
    approved         = models.BooleanField(default=False)
    approved_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_tpc'
    )
    approved_at      = models.DateTimeField(null=True, blank=True)

    # NEW: soft-delete flag
    rejected         = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-date_requested"]

    def __str__(self):
        return f"TPC #{self.pk} – {self.issuer_name} on {self.date_requested}"

    def approver_queryset(self):
        return User.objects.filter(is_active=True, groups__name="tpc_approvers").distinct()

    def approvals_count(self):
        return self.approvals.count()

    def required_approvals_count(self):
        return self.approver_queryset().count()

    def has_user_approved(self, user):
        return self.approvals.filter(user=user).exists()

    def approve(self, user):
        if self.rejected:
            raise PermissionError("This TPC has been rejected and cannot be approved.")
        if not user.groups.filter(name="tpc_approvers").exists():
            raise PermissionError("User is not allowed to approve TPCs.")

        TPCApproval.objects.get_or_create(tpc=self, user=user)

        if self.approvals_count() >= self.required_approvals_count() and self.required_approvals_count() > 0:
            self.approved = True
            self.approved_by = user
            self.approved_at = timezone.now()
            self.save(update_fields=["approved", "approved_by", "approved_at"])

class TPCApproval(models.Model):
    tpc = models.ForeignKey(TPCRequest, related_name="approvals", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    approved_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("tpc", "user")  # one approval per user per TPC

    def __str__(self):
        return f"Approval: TPC #{self.tpc_id} by {self.user}"


# models.py
class VerbalApproval(models.Model):
    tpc = models.ForeignKey(TPCRequest, related_name="verbal_approvals", on_delete=models.CASCADE)
    issuer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # who logged it
    issuer_username = models.CharField(max_length=150, db_index=True)  # NEW: denormalized username

    approver_name = models.CharField(max_length=200)
    approver_phone = models.CharField(max_length=50)
    approver_response = models.TextField()
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"VerbalApproval for TPC #{self.tpc_id} by {self.approver_name}"

