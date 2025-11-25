"""
WSGI config for provisions_link project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Default to production for safe deployments - set DJANGO_SETTINGS_MODULE
# to 'provisions_link.settings.development' for local development
os.environ.setdefault('DJANGO_SETTINGS_MODULE',
                      'provisions_link.settings.production')

application = get_wsgi_application()
