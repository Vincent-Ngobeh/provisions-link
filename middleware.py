"""
Custom middleware for debugging and logging.
"""
import logging
import time

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    """
    Middleware that logs every incoming request.
    This helps debug whether requests are reaching Django.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        logger.info("RequestLoggingMiddleware initialized")

    def __call__(self, request):
        start_time = time.time()

        # Log incoming request
        logger.info(
            f"INCOMING REQUEST: {request.method} {request.path} "
            f"Host: {request.get_host()} "
            f"User-Agent: {request.META.get('HTTP_USER_AGENT', 'unknown')[:50]}"
        )

        try:
            response = self.get_response(request)

            # Log response
            duration = time.time() - start_time
            logger.info(
                f"RESPONSE: {request.method} {request.path} "
                f"Status: {response.status_code} "
                f"Duration: {duration:.3f}s"
            )

            return response
        except Exception as e:
            logger.error(
                f"ERROR handling request: {request.method} {request.path} "
                f"Error: {e}"
            )
            raise
