"""
ASGI config for provisions_link project.
"""

from apps.buying_groups import routing
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE',
                      'provisions_link.settings.development')

# Initialize Django ASGI application early - THIS MUST COME FIRST
django_asgi_app = get_asgi_application()

# Now import routing AFTER Django is initialized

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
