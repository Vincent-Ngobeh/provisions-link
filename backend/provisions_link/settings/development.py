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

# Email backend for development (prints to console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

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
