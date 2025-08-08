from datetime import timedelta
from django.contrib import admin
from django.utils import timezone
from .models import ScrapSubmission, ScrapSystemOperation, ScrapCategory, TPCRequest
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





# ────────────────────────────────────
#  T P C   R E Q U E S T
# ────────────────────────────────────
QM_GROUP = "quality_manager"          # name of your Quality-Manager group

@admin.register(TPCRequest)
class TPCRequestAdmin(admin.ModelAdmin):
    # ─────────────── list view ───────────────
    list_display   = (
        "id", "date_requested", "issuer_name", "reason_short", "process",
        "supplier_issue", "machine_number", "approved",
        "approved_by", "approved_at",
    )
    list_filter    = (
        "supplier_issue", "approved", "process", "issuer_name", "feature",
    )
    date_hierarchy = "date_requested"
    search_fields  = (
        "issuer_name", "reason", "process", "machine_number",
        "feature", "reason_note",
    )
    list_per_page  = 50
    readonly_fields = ("approved_by", "approved_at")

    # ─────────────── helpers ────────────────
    @admin.display(description="Reason")
    def reason_short(self, obj):
        return (obj.reason[:40] + " …") if len(obj.reason) > 40 else obj.reason

    # field groupings
    base_fields     = (
        "date_requested", "issuer_name", "reason", "process", "supplier_issue",
        "machine_number", "reason_note", "feature",
        "current_process", "changed_to",
        "expiration_date", "expiration_notes",
    )
    approval_fields = ("approved", "approved_by", "approved_at")

    # ─────────────── utilities ──────────────
    def _is_qm(self, request):
        return request.user.groups.filter(name=QM_GROUP).exists()

    # ❶  NO queryset filtering → show *all* TPCs
    # (delete the old get_queryset override completely)

    # tailor add/change forms
    def get_fields(self, request, obj=None):
        if obj is None:                       # add form → no approval fields
            return self.base_fields
        if self._is_qm(request):              # QM editing
            return self.base_fields + self.approval_fields
        return self.base_fields + (self.approval_fields if obj.approved else ())

    def get_readonly_fields(self, request, obj=None):
        ro = list(self.readonly_fields)
        if not self._is_qm(request):
            ro.append("approved")
        return ro

    # only QMs may edit existing records
    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request, obj)
        return self._is_qm(request)

    # ─────────────── bulk actions ───────────
    actions = ["approve_selected", "unapprove_selected"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self._is_qm(request):
            actions.pop("approve_selected", None)
            actions.pop("unapprove_selected", None)
        return actions

    def _ensure_manager(self, request):
        if not self._is_qm(request):
            self.message_user(request, "Only Quality Managers can (un)approve.", level="error")
            return False
        return True

    def approve_selected(self, request, queryset):
        if not self._ensure_manager(request):
            return
        count = queryset.update(
            approved=True,
            approved_by=request.user,
            approved_at=timezone.now(),
        )
        self.message_user(request, f"{count} TPC(s) approved.")
    approve_selected.short_description = "Approve selected TPCs"

    def unapprove_selected(self, request, queryset):
        if not self._ensure_manager(request):
            return
        count = queryset.update(approved=False, approved_by=None, approved_at=None)
        self.message_user(request, f"{count} TPC(s) un-approved.")
    unapprove_selected.short_description = "Un-approve selected TPCs"

    # ─────────────── save hook ──────────────
    def save_model(self, request, obj, form, change):
        if not change:                        # new record → force un-approved
            obj.approved     = False
            obj.approved_by  = None
            obj.approved_at  = None
        elif "approved" in form.changed_data: # QM toggled checkbox
            if obj.approved:
                obj.approved_by = request.user
                obj.approved_at = timezone.now()
            else:
                obj.approved_by = None
                obj.approved_at = None
        super().save_model(request, obj, form, change)