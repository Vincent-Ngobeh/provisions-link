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
from django.core.asgi import get_asgi_application  # noqa: E402
django_asgi_app = get_asgi_application()

from apps.buying_groups import routing  # noqa: E402
from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
# isort: on

logger = logging.getLogger(__name__)


async def simple_app(scope, receive, send):
    """
    Minimal ASGI app that handles ALL requests directly.
    This bypasses Django entirely to test if requests reach the server.
    """
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                logger.info("ASGI: Lifespan startup")
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                logger.info("ASGI: Lifespan shutdown")
                await send({"type": "lifespan.shutdown.complete"})
                return
    elif scope["type"] == "http":
        path = scope.get("path", "/")
        method = scope.get("method", "GET")
        headers = dict(scope.get("headers", []))
        host = headers.get(b"host", b"unknown").decode()

        logger.info(f"ASGI: {method} {path} Host: {host}")

        body = f"ASGI Direct Response\nPath: {path}\nHost: {host}\nMethod: {method}".encode(
        )

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/plain"],
                [b"content-length", str(len(body)).encode()],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
    else:
        logger.warning(f"ASGI: Unknown scope type: {scope['type']}")


# TEMPORARY: Use simple_app to test if requests reach the server
# Once this works, we'll switch back to the full Django app
application = simple_app
