from datetime import timedelta
from django.contrib import admin
from django.utils import timezone
from .models import ScrapSubmission, ScrapSystemOperation, ScrapCategory
from plant.models.setupfor_models import Asset

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
    # add part_number and operation_name here:
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
    list_display       = ('part_number', 'operation', 'cost', 'created_at')
    list_filter        = ('assets', 'scrap_categories')
    filter_horizontal  = ('assets', 'scrap_categories')


@admin.register(ScrapCategory)
class ScrapCategoryAdmin(admin.ModelAdmin):
    list_display  = ('name',)
    search_fields = ('name',)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display    = ('asset_number', 'asset_name')
    search_fields   = ('asset_number', 'asset_name')
    list_filter     = ('asset_name',)
    ordering        = ('asset_number',)
    list_editable   = ('asset_name',)
    fields          = ('asset_number', 'asset_name')