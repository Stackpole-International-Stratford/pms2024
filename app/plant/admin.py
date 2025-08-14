from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin


# Proxy model for visitor_hosts group
class VisitorHostsGroup(Group):
    class Meta:
        proxy = True
        verbose_name = "Visitor Hosts"
        verbose_name_plural = "Visitor Hosts"


class UserInline(admin.TabularInline):
    model = Group.user_set.through
    extra = 0
    verbose_name = "Host"
    verbose_name_plural = "Hosts"


class VisitorHostsGroupAdmin(GroupAdmin):
    inlines = [UserInline]

    def get_queryset(self, request):
        # Only show the visitor_hosts group
        return super().get_queryset(request).filter(name="visitor_hosts")

    def changelist_view(self, request, extra_context=None):
        """If there’s only one group, jump directly to its edit page."""
        qs = self.get_queryset(request)
        if qs.count() == 1:
            obj = qs.first()
            return self.change_view(request, object_id=str(obj.pk), extra_context=extra_context)
        return super().changelist_view(request, extra_context)


# Keep default admin for normal groups
admin.site.unregister(Group)
admin.site.register(Group, GroupAdmin)

# Add a second entry in admin for just visitor_hosts
admin.site.register(VisitorHostsGroup, VisitorHostsGroupAdmin)
