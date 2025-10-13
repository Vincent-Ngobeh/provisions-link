# apps/core/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, Address, PrivacySettings
from .admin_site import custom_admin_site


class CustomUserAdmin(BaseUserAdmin):
    """Custom UserAdmin that works with email as USERNAME_FIELD."""

    list_display = ('email', 'first_name', 'last_name',
                    'is_staff', 'is_superuser')
    list_filter = ('is_staff', 'is_superuser', 'is_active')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {
         'fields': ('first_name', 'last_name', 'phone_number')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )

    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions',)


class AddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'address_name', 'postcode', 'is_default')
    list_filter = ('address_name', 'is_default')
    search_fields = ('user__email', 'postcode', 'city')


class PrivacySettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'marketing_emails',
                    'order_updates', 'data_sharing')
    list_filter = ('marketing_emails', 'order_updates')
    search_fields = ('user__email',)


# Register with custom admin site
custom_admin_site.register(User, CustomUserAdmin)
custom_admin_site.register(Address, AddressAdmin)
custom_admin_site.register(PrivacySettings, PrivacySettingsAdmin)

# Also register with default admin site for compatibility
admin.site.register(User, CustomUserAdmin)
admin.site.register(Address, AddressAdmin)
admin.site.register(PrivacySettings, PrivacySettingsAdmin)
