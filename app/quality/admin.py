from django.contrib import admin
from .models import ScrapSystemOperation, ScrapCategory
from plant.models.setupfor_models import Asset


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
    """Full CRUD for Assets in the Admin."""
    list_display    = ('asset_number', 'asset_name')
    search_fields   = ('asset_number', 'asset_name')
    list_filter     = ('asset_name',)
    ordering        = ('asset_number',)
    list_editable   = ('asset_name',)
    fields          = ('asset_number', 'asset_name')