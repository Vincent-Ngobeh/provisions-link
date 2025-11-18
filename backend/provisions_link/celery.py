# provisions_link/celery.py
import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE',
                      'provisions_link.settings.development')

# Create Celery application
app = Celery('provisions_link')

# Load configuration from Django settings with CELERY namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# ============================================================================
# BROKER CONNECTION SETTINGS
# ============================================================================
# Fix for Celery 6.0 deprecation warning
app.conf.broker_connection_retry = True
app.conf.broker_connection_retry_on_startup = True  # ← Fixes the warning

# ============================================================================
# TASK CONFIGURATION
# ============================================================================
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'
app.conf.accept_content = ['json']
app.conf.timezone = 'UTC'
app.conf.enable_utc = True

# Task result backend settings
app.conf.result_expires = 3600  # Results expire after 1 hour

# Task execution settings
app.conf.task_track_started = True
app.conf.task_time_limit = 30 * 60  # 30 minutes hard limit
app.conf.task_soft_time_limit = 25 * 60  # 25 minutes soft limit

# ============================================================================
# AUTODISCOVER TASKS
# ============================================================================
# Automatically discover tasks from installed apps
app.autodiscover_tasks()

# ============================================================================
# PERIODIC TASKS (CELERY BEAT SCHEDULE)
# ============================================================================
app.conf.beat_schedule = {
    # Update FSA ratings weekly (every Monday at 2 AM UTC)
    'update-fsa-ratings-weekly': {
        'task': 'bulk_update_fsa_ratings',
        'schedule': crontab(day_of_week=1, hour=2, minute=0),
        'options': {
            'expires': 3600,  # Task expires if not picked up within 1 hour
        }
    },

    # Process expired buying groups (every 15 minutes)
    'process-expired-buying-groups': {
        'task': 'process_expired_groups',
        'schedule': crontab(minute='*/15'),
        'options': {
            'expires': 600,  # Task expires if not picked up within 10 minutes
        }
    },
}
