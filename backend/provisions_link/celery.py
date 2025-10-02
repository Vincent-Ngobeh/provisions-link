# provisions_link/celery.py
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE',
                      'provisions_link.settings.development')

app = Celery('provisions_link')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(['apps.buying_groups', 'apps.vendors', 'apps.products'])
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
