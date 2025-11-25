"""
ASGI config for provisions_link project.
"""

import os
import logging

# CRITICAL: Set Django settings module BEFORE any Django imports
# Default to production for safe deployments - set DJANGO_SETTINGS_MODULE
# to 'provisions_link.settings.development' for local development
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
    ASGI middleware to handle health checks at the ASGI level,
    bypassing Django's URL routing for faster, more reliable health checks.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Log ALL incoming scopes for debugging
        scope_type = scope.get("type", "unknown")
        path = scope.get("path", "N/A")
        logger.info(f"ASGI SCOPE: type={scope_type} path={path}")

        # Handle lifespan protocol (used by uvicorn for startup/shutdown)
        if scope_type == "lifespan":
            # Just acknowledge lifespan protocol without doing anything
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return

        # Handle health check
        if path == "/health":
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

        # TEMPORARY: Handle root path directly to test if requests reach ASGI
        if path == "/" or path == "/favicon.ico":
            logger.info(f"ASGI: Handling {path} directly for debugging")
            body = f"ASGI Direct Response - Path: {path}".encode()
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [[b"content-type", b"text/plain"]],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })
            return

        try:
            logger.info(
                f"ASGI: Forwarding to ProtocolTypeRouter: {scope_type} {path}")
            await self.app(scope, receive, send)
            logger.info(f"ASGI: Completed: {scope_type} {path}")
        except Exception as e:
            logger.error(
                f"ASGI: Error processing {scope_type} {path}: {e}", exc_info=True)
            raise


application = HealthCheckMiddleware(
    ProtocolTypeRouter({
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(
                    routing.websocket_urlpatterns
                )
            )
        ),
    })
)
