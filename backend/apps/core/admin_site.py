# apps/core/admin_site.py

from django.contrib.admin import AdminSite
from django.contrib.auth.forms import AuthenticationForm
from django import forms
from django.utils.translation import gettext_lazy as _


class EmailAuthenticationForm(AuthenticationForm):
    """
    Custom authentication form that properly handles email as username.
    """
    username = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(attrs={
            'autofocus': True,
            'autocapitalize': 'none',
            'autocomplete': 'email',
        })
    )

    error_messages = {
        'invalid_login': _(
            "Please enter a correct email address and password. Note that both "
            "fields may be case-sensitive."
        ),
        'inactive': _("This account is inactive."),
    }


class CustomAdminSite(AdminSite):
    """
    Custom admin site that uses email for authentication.
    """
    site_header = "Provisions Link Administration"
    site_title = "Provisions Link Admin"
    index_title = "Welcome to Provisions Link Administration"

    # Use our custom login form
    login_form = EmailAuthenticationForm

    def has_permission(self, request):
        """
        Check if user has permission to access admin.
        User must be active and staff.
        """
        return request.user.is_active and request.user.is_staff


# Create instance of custom admin site
custom_admin_site = CustomAdminSite(name='custom_admin')
