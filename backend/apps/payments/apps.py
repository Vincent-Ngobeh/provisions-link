"""
Django app configuration for payments.
"""
from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Configuration for the payments app."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.payments'
    verbose_name = 'Payments'

    def ready(self):
        """
        Initialize app when Django starts.
        Import signal handlers or perform other initialization here.
        """
        pass
