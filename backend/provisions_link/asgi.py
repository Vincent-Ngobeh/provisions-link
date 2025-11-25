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
        logger.info("HealthCheckMiddleware initialized")

    async def __call__(self, scope, receive, send):
        scope_type = scope.get("type", "unknown")
        path = scope.get("path", "N/A")

        # Handle lifespan - try to forward to app, but handle if not supported
        if scope_type == "lifespan":
            logger.info("ASGI: Handling lifespan protocol")
            try:
                # Try to forward lifespan to the underlying app
                await self.app(scope, receive, send)
            except ValueError as e:
                # ProtocolTypeRouter doesn't support lifespan, handle it ourselves
                if "lifespan" in str(e):
                    logger.info(
                        "ASGI: App doesn't support lifespan, handling directly")
                    while True:
                        message = await receive()
                        if message["type"] == "lifespan.startup":
                            await send({"type": "lifespan.startup.complete"})
                        elif message["type"] == "lifespan.shutdown":
                            await send({"type": "lifespan.shutdown.complete"})
                            return
                else:
                    raise
            return

        # Log all HTTP requests
        if scope_type == "http":
            logger.info(f"ASGI: HTTP request received - path={path}")

            # Handle health check directly
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

        # Forward all other requests to the app
        try:
            logger.info(f"ASGI: Forwarding {scope_type} {path} to app")
            await self.app(scope, receive, send)
            logger.info(f"ASGI: Completed {scope_type} {path}")
        except Exception as e:
            logger.error(
                f"ASGI: Error processing {scope_type} {path}: {e}", exc_info=True)
            # Return a 500 error response for HTTP requests
            if scope_type == "http":
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [[b"content-type", b"text/plain"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": f"Internal Server Error: {str(e)}".encode(),
                })
            else:
                raise


# Create the protocol router
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
