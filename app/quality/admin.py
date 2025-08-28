# quality/admin.py
from datetime import timedelta
from django.contrib import admin
from django.utils import timezone
from .models import ScrapSubmission, ScrapSystemOperation, ScrapCategory, Program
from .forms import ScrapSystemOperationAdminForm
from plant.models.setupfor_models import Asset

@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display  = ("name",)
    search_fields = ("name",)

@admin.register(ScrapSubmission)
class ScrapSubmissionAdmin(admin.ModelAdmin):
    list_display   = (
        'part_number',
        'machine',
        'operation_name',
        'category_name',
        'quantity',
        'came_from_op',
        'created_at',
    )
    date_hierarchy = 'created_at'
    list_filter    = (
        'part_number',
        'machine',
        'operation_name',
        'scrap_category',
    )
    search_fields  = (
        'part_number',
        'machine',
        'operation_name',
        'category_name',
        'came_from_op',
    )

    def get_queryset(self, request):
        cutoff = timezone.now() - timedelta(days=90)
        return super().get_queryset(request).filter(created_at__gte=cutoff)

@admin.register(ScrapSystemOperation)
class ScrapSystemOperationAdmin(admin.ModelAdmin):
    form = ScrapSystemOperationAdminForm

    list_display      = ('part_number', 'operation', 'program_display', 'cost', 'created_at')
    list_filter       = ('assets', 'scrap_categories', 'programs')  # keep filter by Program
    filter_horizontal = ('assets', 'scrap_categories')              # remove 'programs' here
    search_fields     = ('part_number', 'operation')

    # Show the single selected program (if any) in the list
    def program_display(self, obj):
        p = obj.programs.first()
        return p.name if p else "-"
    program_display.short_description = "Program"

    # Map the single dropdown to the underlying M2M
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        program = form.cleaned_data.get('program')
        if program:
            obj.programs.set([program])  # enforce exactly one
        else:
            obj.programs.clear()
