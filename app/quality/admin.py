from django.contrib import admin
from .models import NewScrapSystemScrapCategory

@admin.register(NewScrapSystemScrapCategory)
class NewScrapSystemScrapCategoryAdmin(admin.ModelAdmin):
    list_display      = ("part_number", "operation", "category", "cost")
    list_filter       = ("part_number", "operation", "category")
    search_fields     = ("part_number", "operation", "category")
    list_editable     = ("cost",)
    ordering          = ("part_number", "operation", "category")

    # add machines many-to-many selector:
    filter_horizontal = ("machines",)
    # alternatively, if you want autocomplete:
    # autocomplete_fields = ("machines",)
