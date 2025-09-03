# quality/admin.py
from datetime import timedelta
from django.contrib import admin
from django.utils import timezone
from .models import ScrapSubmission, ScrapSystemOperation, ScrapCategory, TPCRequest
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
QM_GROUP = "quality_manager"          # Django Group that may approve TPCs


@admin.register(TPCRequest)
class TPCRequestAdmin(admin.ModelAdmin):

    # ── list view ──
    list_display = (
        "id", "date_requested", "issuer_name", "parts_display",
        "reason_short", "process", "supplier_issue",
        "machines_display", "approved", "approved_by", "approved_at",
    )
    list_filter = (
        "supplier_issue", "approved", "process",
        "issuer_name",  # removed: 'part' (not a field anymore)
        # keep 'feature' if it exists as a CharField; otherwise remove
        "feature",
    )
    search_fields = (
        "issuer_name", "reason", "process",
        "feature", "reason_note",
        # allow text search inside JSON lists
        "parts__icontains", "machines__icontains",
    )
    date_hierarchy = "date_requested"
    list_per_page = 50
    readonly_fields = ("approved_by", "approved_at")

    # ── edit view layout ──
    base_fields = (
        "date_requested", "issuer_name",
        # use the new field names here
        "parts", "reason", "process", "supplier_issue",
        "machines", "reason_note", "feature", "current_process", "changed_to",
        "expiration_date",
    )
    approval_fields = ("approved", "approved_by", "approved_at")

    @admin.display(description="Reason")
    def reason_short(self, obj):
        return (obj.reason[:40] + " …") if len(obj.reason) > 40 else obj.reason

    @admin.display(description="Parts")
    def parts_display(self, obj):
        try:
            return ", ".join(obj.parts) if obj.parts else "—"
        except Exception:
            return str(obj.parts) if obj.parts else "—"

    @admin.display(description="Machines")
    def machines_display(self, obj):
        try:
            return ", ".join(obj.machines) if obj.machines else "—"
        except Exception:
            return str(obj.machines) if obj.machines else "—"

    # ── permissions ──
    def _is_qm(self, request):
        return request.user.groups.filter(name=QM_GROUP).exists()

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request, obj)
        return self._is_qm(request)

    def get_fields(self, request, obj=None):
        if obj is None:
            return self.base_fields
        return self.base_fields + (self.approval_fields if self._is_qm(request) or obj.approved else ())

    def get_readonly_fields(self, request, obj=None):
        ro = list(self.readonly_fields)
        if not self._is_qm(request):
            ro.append("approved")
        return ro

    # ── bulk actions ──
    actions = ["approve_selected", "unapprove_selected"]

    def get_actions(self, request):
        acts = super().get_actions(request)
        if not self._is_qm(request):
            acts.pop("approve_selected", None)
            acts.pop("unapprove_selected", None)
        return acts

    def _ensure_manager(self, request):
        if not self._is_qm(request):
            self.message_user(request, "Only Quality-Managers can (un)approve.", level="error")
            return False
        return True

    def approve_selected(self, request, queryset):
        if not self._ensure_manager(request):
            return
        count = queryset.update(approved=True, approved_by=request.user, approved_at=timezone.now())
        self.message_user(request, f"{count} TPC(s) approved.")
    approve_selected.short_description = "Approve selected TPCs"

    def unapprove_selected(self, request, queryset):
        if not self._ensure_manager(request):
            return
        count = queryset.update(approved=False, approved_by=None, approved_at=None)
        self.message_user(request, f"{count} TPC(s) un-approved.")
    unapprove_selected.short_description = "Un-approve selected TPCs"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.approved = False
            obj.approved_by = None
            obj.approved_at = None
        elif "approved" in form.changed_data:
            if obj.approved:
                obj.approved_by = request.user
                obj.approved_at = timezone.now()
            else:
                obj.approved_by = None
                obj.approved_at = None
        super().save_model(request, obj, form, change)
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
