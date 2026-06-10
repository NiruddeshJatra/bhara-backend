from .base import *
from decouple import config

DEBUG = True
SECRET_KEY = config('SECRET_KEY', default='dev-secret-key-not-for-production')

DATABASES = {
  'default': {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': BASE_DIR / 'db.sqlite3',
  }
}

CACHES = {
  'default': {
    'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    'LOCATION': 'unique-snowflake',
  }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_STORE_EAGER_RESULT = True

SIMPLE_JWT = {
  **SIMPLE_JWT,
  'AUTH_COOKIE_SECURE': False,
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

ALPHA_SMS_ENABLED = False

CORS_ALLOW_ALL_ORIGINS = True
