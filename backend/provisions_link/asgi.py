"""
ASGI config for provisions_link project.
"""

from apps.buying_groups import routing
from channels.security.websocket import AllowedHostsOriginValidator
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
import os

# CRITICAL: Set Django settings module BEFORE any Django imports
# Default to production for safe deployments - set DJANGO_SETTINGS_MODULE
# to 'provisions_link.settings.development' for local development
os.environ.setdefault('DJANGO_SETTINGS_MODULE',
                      'provisions_link.settings.production')

# Initialize Django ASGI application BEFORE importing app modules
django_asgi_app = get_asgi_application()

# Import these AFTER Django is fully initialized

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                routing.websocket_urlpatterns
            )
        )
    ),
})
