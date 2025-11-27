"""
Base Django settings for Provisions Link project.

Contains all common settings used across all environments.
Environment-specific settings should override these in their respective files.
"""
import os
from pathlib import Path
from datetime import timedelta
from celery.schedules import crontab
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project root directory (three levels up from this file)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# GDAL/GEOS Configuration (only needed for Windows)
if os.name == 'nt':  # Windows only
    # Set these as Django settings, not environment variables
    GDAL_LIBRARY_PATH = r'C:\Users\Vince\AppData\Local\Programs\OSGeo4W\bin\gdal311.dll'
    GEOS_LIBRARY_PATH = r'C:\Users\Vince\AppData\Local\Programs\OSGeo4W\bin\geos_c.dll'

    # Also set environment variables for good measure
    os.environ['GDAL_DATA'] = r'C:\Users\Vince\AppData\Local\Programs\OSGeo4W\share\gdal'
    os.environ['PROJ_LIB'] = r'C:\Users\Vince\AppData\Local\Programs\OSGeo4W\share\proj'

    # Add to PATH
    osgeo_bin = r'C:\Users\Vince\AppData\Local\Programs\OSGeo4W\bin'
    if osgeo_bin not in os.environ.get('PATH', ''):
        os.environ['PATH'] = osgeo_bin + ';' + os.environ['PATH']

# Security
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set!")

# Core Django applications
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
]

# Third-party applications
THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'channels',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'storages',
]

# Project applications
LOCAL_APPS = [
    'apps.core',
    'apps.vendors',
    'apps.products',
    'apps.buying_groups',
    'apps.orders',
    'apps.integrations',
    'apps.payments',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Middleware configuration
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# URL configuration
ROOT_URLCONF = 'provisions_link.urls'

# Template configuration
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# WSGI/ASGI configuration
WSGI_APPLICATION = 'provisions_link.wsgi.application'
ASGI_APPLICATION = 'provisions_link.asgi.application'

# Channels Layer Configuration
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [(os.environ.get('REDIS_HOST', '127.0.0.1'),
                      int(os.environ.get('REDIS_PORT', 6379)))],
            "capacity": 1500,  # Maximum number of messages to store
            "expiry": 10,  # Seconds
        },
    },
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files configuration
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
] if (BASE_DIR / 'static').exists() else []

# Media files configuration
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# AWS S3 Configuration (base settings, will be overridden in production)
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', '')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', '')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME', 'eu-west-2')
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com' if AWS_STORAGE_BUCKET_NAME else None
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
}
AWS_DEFAULT_ACL = None  # ACLs disabled - using bucket policy instead
AWS_S3_VERIFY = True

# Primary key field configuration
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'core.User'

# Authentication backends
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# Stripe Configuration
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')
STRIPE_WEBHOOK_SECRET_DESTINATION = os.getenv(
    'STRIPE_WEBHOOK_SECRET_DESTINATION', '')
STRIPE_PLATFORM_ACCOUNT_ID = os.getenv('STRIPE_PLATFORM_ACCOUNT_ID', '')

# Frontend URL (for Stripe redirects and other integrations)
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# Django REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
    # Add this line for drf-spectacular
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# JWT Authentication configuration
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=60),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=7),
}

# drf-spectacular settings for API documentation
SPECTACULAR_SETTINGS = {
    'TITLE': 'Provisions Link API',
    'DESCRIPTION': 'B2B Marketplace for UK Food & Beverage Industry',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': True,
    },
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/v1/',
}

# Service Configuration
SERVICE_CACHE_TIMEOUT = 3600  # 1 hour default cache timeout for services

# External API Keys
MAPBOX_API_TOKEN = os.getenv('MAPBOX_API_TOKEN', '')

# FSA API Configuration
FSA_API_BASE_URL = 'https://api.ratings.food.gov.uk'
FSA_API_VERSION = '2'

# Celery Configuration for Periodic Tasks
CELERY_BEAT_SCHEDULE = {
    # Buying Groups Tasks
    'process-expired-groups-hourly': {
        'task': 'process_expired_buying_groups',
        'schedule': crontab(minute=0),  # Every hour
    },
    'check-group-thresholds-every-30-min': {
        'task': 'check_group_thresholds',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
    'notify-expiring-groups-every-6-hours': {
        'task': 'notify_expiring_groups',
        'schedule': crontab(minute=0, hour='*/6'),  # Every 6 hours
    },
    'cleanup-old-group-updates-weekly': {
        'task': 'cleanup_old_group_updates',
        'schedule': crontab(hour=3, minute=0, day_of_week=0),  # Sunday 3 AM
    },
    'refresh-demo-groups-daily': {
        'task': 'refresh_demo_buying_groups',
        'schedule': crontab(hour=0, minute=30),  # Daily at 12:30 AM
    },

    # Vendor Tasks
    'update-fsa-ratings-weekly': {
        'task': 'bulk_update_fsa_ratings',
        'schedule': crontab(hour=2, minute=0, day_of_week=1),  # Monday 2 AM
    },
    'check-vendor-compliance-daily': {
        'task': 'check_vendor_compliance',
        'schedule': crontab(hour=1, minute=0),  # Daily at 1 AM
    },
    'update-vendor-commission-monthly': {
        'task': 'update_vendor_commission_rates',
        # First day of month
        'schedule': crontab(hour=0, minute=0, day_of_month=1),
    },

    # Product Tasks
    'check-low-stock-daily': {
        'task': 'check_low_stock_products',
        'schedule': crontab(hour=9, minute=0),  # Daily at 9 AM
    },
    'update-search-vectors-weekly': {
        'task': 'update_search_vectors',
        'schedule': crontab(hour=4, minute=0, day_of_week=0),  # Sunday 4 AM
    },
    'calculate-product-analytics-weekly': {
        'task': 'calculate_product_analytics',
        'schedule': crontab(hour=5, minute=0, day_of_week=0),  # Sunday 5 AM
    },
    'update-featured-products-weekly': {
        'task': 'update_featured_products',
        'schedule': crontab(hour=6, minute=0, day_of_week=1),  # Monday 6 AM
    },
    'cleanup-abandoned-products-monthly': {
        'task': 'cleanup_abandoned_products',
        # 15th of month
        'schedule': crontab(hour=2, minute=0, day_of_month=15),
    },
}

# Logging configuration - Base (Console only by default)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'provisions_link': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'provisions_link.requests': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Request logging settings (for custom middleware)
REQUEST_LOGGING_ENABLED = os.getenv(
    'REQUEST_LOGGING_ENABLED', 'False').lower() == 'true'
REQUEST_LOGGING_LEVEL = 'INFO'
REQUEST_LOGGING_INCLUDE_RESPONSE_BODY = False

# Rate limiting settings (for custom middleware)
RATE_LIMITING_ENABLED = os.getenv(
    'RATE_LIMITING_ENABLED', 'False').lower() == 'true'
