"""
ASGI config for provisions_link project.
"""

import os
import logging

# CRITICAL: Set Django settings module BEFORE any Django imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE',
                      'provisions_link.settings.production')

# isort: off
# Initialize Django ASGI application BEFORE importing app modules
from django.core.asgi import get_asgi_application  # noqa: E402
django_asgi_app = get_asgi_application()

# Import these AFTER Django is fully initialized
from apps.buying_groups import routing  # noqa: E402
from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
# isort: on

logger = logging.getLogger(__name__)


class HealthCheckMiddleware:
    """
    ASGI middleware to handle health checks and lifespan protocol.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Handle lifespan protocol (ProtocolTypeRouter doesn't support it)
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return

        # Handle health check at ASGI level for reliability
        if scope["type"] == "http" and scope.get("path") == "/health":
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [[b"content-type", b"text/plain"]],
            })
            await send({
                "type": "http.response.body",
                "body": b"OK",
            })
            return

        # Forward all other requests to Django/Channels
        await self.app(scope, receive, send)


# Create the protocol router for HTTP and WebSocket
inner_app = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                routing.websocket_urlpatterns
            )
        )
    ),
})

# Wrap with health check middleware
application = HealthCheckMiddleware(inner_app)
