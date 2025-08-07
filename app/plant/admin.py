# plant/admin.py
from django.contrib import admin
from .models.maintenance_models import DowntimeMachine
from .models.email_models import EmailRecipient, EmailCampaign

@admin.register(DowntimeMachine)
class DowntimeMachineAdmin(admin.ModelAdmin):
    list_display    = ('line', 'operation', 'machine_number', 'is_tracked', 'created_at_UTC')
    list_filter     = ('line', 'operation', 'is_tracked')
    search_fields   = ('line', 'operation', 'machine_number')
    readonly_fields = ('created_at_UTC', 'updated_at_UTC')


@admin.register(EmailRecipient)
class EmailRecipientAdmin(admin.ModelAdmin):
    list_display   = ("email", "name")
    search_fields  = ("email", "name")

    def _is_editor(self, user):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        # True if they’re editor on ≥1 campaign
        return EmailCampaign.objects.filter(editors=user).exists()

    def has_module_permission(self, request):
        return self._is_editor(request.user)

    def has_view_permission(self, request, obj=None):
        return self._is_editor(request.user)

    def has_add_permission(self, request):
        return self._is_editor(request.user)

    def has_change_permission(self, request, obj=None):
        return self._is_editor(request.user)

    def has_delete_permission(self, request, obj=None):
        return self._is_editor(request.user)


@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display      = ("name", "description", "created_at")
    search_fields     = ("name", "description")
    filter_horizontal = ("recipients", "editors")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(editors=request.user)

    def has_module_permission(self, request):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return EmailCampaign.objects.filter(editors=request.user).exists()

    def has_view_permission(self, request, obj=None):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        if obj is None:
            return True
        return request.user in obj.editors.all()

    def has_change_permission(self, request, obj=None):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        if obj is None:
            return True
        return request.user in obj.editors.all()

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj is not None and not request.user.is_superuser:
            ro += ['name', 'description', 'editors']
        return ro
