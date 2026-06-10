import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.development')

app = Celery('core')
app.config_from_object('django.conf:settings', namespace='CELERY')  # Loads settings from Django settings module
app.autodiscover_tasks()  # Automatically discovers tasks from installed apps
