from django.db import models
from plant.models.setupfor_models import Part  # Importing the Part model

class SupervisorAuthorization(models.Model):
    """
    Record supervisor approvals for feature work on specific parts.

    Each instance represents a single authorization event, capturing:
      - supervisor_id (str):  Identifier of the approving supervisor.
      - part_number (str):    The part for which authorization is granted.
      - feat_name (str):      The name of the feature or operation authorized.
      - created_at (datetime): Timestamp when the authorization was created (auto-set).

    The string representation includes the supervisor, feature, part, and creation time.
    """
    supervisor_id = models.CharField(max_length=256)
    part_number = models.CharField(max_length=256)
    feat_name = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Authorization by {self.supervisor_id} for {self.feat_name} (Part {self.part_number}) at {self.created_at}'

class Feat(models.Model):
    """
    Define a feature or operation associated with a specific Part.

    Fields
    ------
    part : ForeignKey to Part
        The Part to which this feature belongs; cascading delete applies.
    name : str
        The unique name of the feature for the given part.
    order : int
        Display or execution order of this feature (ascending).
    alarm : int
        Numeric alarm threshold or code for this feature (default 0).
    critical : bool
        Flag indicating whether this feature is critical (default False).

    Meta
    ----
    unique_together : (part, name)
        Enforce that each feature name is unique per part.
    ordering : ['order']
        Default queryset ordering by the `order` field.

    __str__
    -------
    Returns a string in the format: "<name> (<part>)".
    """
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
    """
    Record daily scrap inspection and packing data for a specific part.

    Fields
    ------
    partNumber : str
        Identifier of the part being reported.
    date : date
        The calendar date of this scrap report.
    operator : str, optional
        The name or ID of the operator on that date.
    shift : int, optional
        The shift number during which the data was collected.
    qtyPacked : int, optional
        Quantity of parts packed that day.
    totalDefects : int, optional
        Total number of defects found.
    totalInspected : int, optional
        Total number of parts inspected.
    comments : str, optional
        Any general remarks or notes.
    detailOther : str, optional
        Additional detail on other defect types or observations.
    tpc_number : str, optional
        TPC (Third-Party Certification) number if applicable.
    payload : dict
        Raw JSON payload of the full submission, for audit or replay.
    created_at : datetime
        Timestamp when this record was created (auto-set).

    Methods
    -------
    __str__()
        Returns a human-readable identifier for this scrap form.

    Usage
    -----
    Instances capture both summarized and raw data for daily scrap/inspection
    operations, allowing both structured queries (via columns) and full
    payload replay via the `payload` JSON field.
    """
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
    """
    Represent defect counts for a specific feature within a scrap form.

    Each FeatEntry links to a parent ScrapForm and records:
      - featName (str):      The name of the feature being inspected.
      - defects (int):       The number of defects observed for that feature.
      - partNumber (str):    The identifier of the part associated with this feature entry.

    Relationships
    -------------
    scrap_form : ForeignKey to ScrapForm
        The ScrapForm instance to which this feature entry belongs. Deletion of the
        parent ScrapForm cascades to its FeatEntry records.

    Fields
    ------
    scrap_form    : ScrapForm
    featName      : CharField(max_length=256)
    defects       : IntegerField
    partNumber    : CharField(max_length=256)

    Methods
    -------
    __str__()
        Returns a human-readable string summarizing the feature name, defect count,
        and part number.
    """
    scrap_form = models.ForeignKey(ScrapForm, related_name='feat_entries', on_delete=models.CASCADE)
    featName = models.CharField(max_length=256)
    defects = models.IntegerField()
    partNumber = models.CharField(max_length=256)  # Add the partNumber field

    def __str__(self):
        return f'FeatEntry for {self.featName} with {self.defects} defects, Part Number: {self.partNumber}'





from django.db import models
from plant.models.setupfor_models import Part

class PartMessage(models.Model):
    """
    Store a custom display message and font size for a specific Part.

    Each PartMessage is a one-to-one extension of a Part, allowing you to:
      - Define a free-form `message` to show alongside that part.
      - Choose a `font_size` from predefined options ('small', 'medium', 'large', 'xl', 'xxl', 'xxxl').

    Fields
    ------
    part : OneToOneField to Part
        The Part instance this message customizes. Deletion of the Part
        cascades to its PartMessage.
    message : TextField, optional
        The custom text to display; may be blank or null if no message is set.
    font_size : CharField
        The display size for the message text. Choices are defined in
        `FONT_SIZE_CHOICES`, defaulting to 'medium'.

    Methods
    -------
    __str__()
        Returns a concise identifier: "Message for <part_number>".
    """
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
    """
    Store and categorize PDF documents related to quality processes and associate them with parts.

    Fields
    ------
    title : str
        Human-readable title of the document.
    pdf_file : FileField
        The uploaded PDF file; stored under ‘pdfs/’ in media.
    associated_parts : ManyToManyField to Part
        Parts to which this document applies.
    uploaded_at : datetime
        Timestamp when the document was uploaded (auto-set).
    category : str
        The document category, chosen from:
          - 'QA'  (Quality Alerts)
          - 'SI'  (Special Instruction)
          - 'TPC' (TPC)
          - 'VAC' (Visual Acceptance Criteria)
          - 'PMR' (Part Marking Requirement)
          - 'CT'  (Certification Tag)
          - 'SA'  (Safety Alert)
        Defaults to 'QA'.

    Methods
    -------
    __str__()
        Returns the document’s title.
    is_new()
        Returns True if `uploaded_at` is within the last 4 hours.

    Notes
    -----
    A post-delete signal ensures that when a database record is removed,
    its corresponding file is also deleted from disk.
    """
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
    """
    Remove the PDF file from disk when its database record is deleted.

    Triggered automatically after a QualityPDFDocument is deleted.
    Checks that the file exists on disk before attempting removal.
    """
    if instance.pdf_file:
        if os.path.isfile(instance.pdf_file.path):
            os.remove(instance.pdf_file.path)


class ViewingRecord(models.Model):
    """
    Log when an operator views a quality PDF document.

    Each record captures:
      - operator_number (str): The operator's clock number or identifier.
      - pdf_document (QualityPDFDocument): The document that was viewed.
      - viewed_at (datetime): Timestamp when the view occurred (auto-set on creation).

    Relationships
    -------------
    pdf_document : ForeignKey to QualityPDFDocument
        Deletes viewing records if the linked PDF document is removed.

    Fields
    ------
    operator_number : CharField(max_length=20)
        Operator’s clock number (stored as string for flexibility).
    pdf_document : ForeignKey
        Reference to the viewed QualityPDFDocument.
    viewed_at : DateTimeField
        Auto-populated with the current time when the record is created.

    Methods
    -------
    __str__()
        Returns a readable string in the format:
        "Operator <operator_number> viewed <document title> on <viewed_at>".
    """
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
    """
    Define a category of “Red Rabbit” inspection or process for a given part.

    Fields
    ------
    name : str
        Unique name of this red rabbit type.
    description : str, optional
        Free-form description or notes about this type.
    part : ForeignKey to Part
        The Part to which this type applies; defaults to Part with ID 1.
        Deletion of the Part cascades to its RedRabbitType entries.

    Methods
    -------
    __str__()
        Returns the type’s name along with its associated part number.
    """
    name = models.CharField(max_length=256, unique=True)
    description = models.TextField(blank=True, null=True)  # Optional description
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name="red_rabbit_types", default=1)  # Default to part ID 1

    def __str__(self):
        return f"{self.name} (Part: {self.part.part_number})"



class RedRabbitsEntry(models.Model):
    """
    Record a single “Red Rabbit” event or verification for a part.

    Fields
    ------
    part : ForeignKey to Part
        The Part being inspected or processed.
    red_rabbit_type : ForeignKey to RedRabbitType
        The type/category of this entry; defaults to type ID 1.
    date : date
        Date when the entry was created (auto-set to today).
    clock_number : str
        Operator’s clock number or identifier.
    shift : int
        Shift number during which the event occurred.
    verification_okay : bool
        Whether the red rabbit verification passed.
    supervisor_comments : str, optional
        Any additional comments from the supervisor.
    supervisor_id : str, optional
        Identifier of the supervising person.
    created_at : datetime
        Timestamp when this entry was created (auto-set).

    Methods
    -------
    __str__()
        Returns a summary string including the type, part number, and operator.
    """
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



