"""
Production settings - used for deployment.
"""
import dj_database_url
import logging
from .base import *

logger = logging.getLogger(__name__)

# Security - DEBUG defaults to False, can be enabled via environment variable if needed
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

# Parse ALLOWED_HOSTS from environment variable
# Format: comma-separated list of allowed hosts (e.g., "example.com,www.example.com,api.example.com")
_allowed_hosts = os.environ.get('ALLOWED_HOSTS', '')
if _allowed_hosts and _allowed_hosts.strip():
    # Split by comma and remove any whitespace/empty strings
    ALLOWED_HOSTS = [host.strip()
                     for host in _allowed_hosts.split(',') if host.strip()]
    # Always include Railway health check host
    if 'healthcheck.railway.app' not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append('healthcheck.railway.app')
else:
    # Default Railway domain for deployment
    # Add additional domains via ALLOWED_HOSTS environment variable
    ALLOWED_HOSTS = [
        '.railway.app',  # All Railway subdomains
        'provisions-link-production.up.railway.app',
        'healthcheck.railway.app',  # Railway health checks
    ]
    logger.info(
        "ALLOWED_HOSTS environment variable not set. "
        "Using default Railway domains. "
        "Set ALLOWED_HOSTS to add custom domains."
    )

# Database - use DATABASE_URL from environment
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Ensure PostGIS engine
DATABASES['default']['ENGINE'] = 'django.contrib.gis.db.backends.postgis'

# Security settings
# Note: SECURE_SSL_REDIRECT is False because Railway handles HTTPS at the proxy level
# The proxy terminates SSL and forwards requests as HTTP internally
SECURE_SSL_REDIRECT = False

# Disable APPEND_SLASH to prevent 301 redirects on health check
# Our URL patterns don't use trailing slashes
APPEND_SLASH = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# HSTS settings - let the proxy handle this, or set via headers
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Channels layer for production
_redis_url = os.environ.get('REDIS_URL')
if _redis_url:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                "hosts": [_redis_url],
            },
        },
    }
else:
    # Fallback to in-memory channel layer if Redis not configured
    # Note: This won't work for multi-instance deployments
    logger.warning(
        "REDIS_URL not set. Using in-memory channel layer. "
        "WebSocket features may not work across multiple instances."
    )
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# Parse CORS_ALLOWED_ORIGINS from environment variable
# Format: comma-separated list of allowed origins (e.g., "https://app.example.com,https://www.example.com")
_cors_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if _cors_origins and _cors_origins.strip():
    # Split by comma and remove any whitespace/empty strings
    CORS_ALLOWED_ORIGINS = [origin.strip()
                            for origin in _cors_origins.split(',') if origin.strip()]
else:
    # SECURITY: If not set, use empty list (blocks all origins - safe default)
    # Set CORS_ALLOWED_ORIGINS environment variable in production!
    CORS_ALLOWED_ORIGINS = []
    # Log warning in production if CORS origins not configured
    logger.warning(
        "CORS_ALLOWED_ORIGINS environment variable not set! "
        "All cross-origin requests will be blocked. "
        "Set CORS_ALLOWED_ORIGINS to a comma-separated list of allowed origins."
    )

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://provisions-link-frontend(-[a-z0-9]+)?(-[a-z0-9-]+)?\.vercel\.app$",
]

CORS_ALLOW_CREDENTIALS = True

# AWS S3 Configuration for Production
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

# WhiteNoise for serving static files
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# Configure logging to show INFO level messages
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'provisions_link': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Static files configuration
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    # Use S3 for static files if AWS is configured
    AWS_STATIC_BUCKET_NAME = os.getenv(
        'AWS_STATIC_BUCKET_NAME', 'provisions-link-static')
    STATICFILES_STORAGE = 'provisions_link.storage_backends.StaticStorage'
    STATIC_URL = f'https://{AWS_STATIC_BUCKET_NAME}.s3.eu-west-2.amazonaws.com/'
else:
    # Use WhiteNoise for static files (no S3)
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
    STATIC_URL = '/static/'
    logger.info("AWS credentials not set. Using WhiteNoise for static files.")

# Media files configuration
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    # Use S3 for media files if AWS is configured
    AWS_STORAGE_BUCKET_NAME = os.getenv(
        'AWS_STORAGE_BUCKET_NAME', 'provisions-link-media')
    DEFAULT_FILE_STORAGE = 'provisions_link.storage_backends.MediaStorage'
    MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.eu-west-2.amazonaws.com/'
else:
    # Use local storage for media files (no S3)
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    logger.info("AWS credentials not set. Using local storage for media files.")

# Email configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.sendgrid.net')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.environ.get(
    'DEFAULT_FROM_EMAIL', 'noreply@provisionslink.com')

# Celery Configuration
CELERY_BROKER_URL = os.environ.get('REDIS_URL')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL')

# Sentry for error tracking
if os.environ.get('SENTRY_DSN'):
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=os.environ.get('SENTRY_DSN'),
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=True
    )
