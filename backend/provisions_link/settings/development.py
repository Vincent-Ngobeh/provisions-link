"""
Development settings - used for local development.
"""
from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
DEBUG_PROPAGATE_EXCEPTIONS = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.localhost']

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': os.environ.get('DB_NAME', 'provisions_link'),
        'USER': os.environ.get('DB_USER', 'provisions_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'provisions_pass'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Django Channels
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [(
                os.environ.get('REDIS_HOST', '127.0.0.1'),
                int(os.environ.get('REDIS_PORT', 6379))
            )],
        },
    },
}

# CORS settings for local development
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",  # Vite default
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

# Allow CORS credentials
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# Email backend for development (prints to console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# AWS S3 Configuration for Media Files (use S3 even in development)
# This ensures images work consistently across all environments
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_STORAGE_BUCKET_NAME:
    # Use S3 for media storage
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

    # Override the S3 custom domain to use regional endpoint
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com'

    # Media URL pointing to S3
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'

    # Ensure public read access
    # AWS_DEFAULT_ACL = 'public-read'
    AWS_QUERYSTRING_AUTH = False

    # Optional: Set location for media files in bucket
    AWS_LOCATION = 'media'
else:
    # Fallback to local storage if S3 not configured
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

# Django Debug Toolbar (optional but useful)
if DEBUG:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
    INTERNAL_IPS = ['127.0.0.1', 'localhost']

# Celery Configuration (for async tasks)
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
