from .base import *
from decouple import config

DEBUG = False  # never overridable in production
SECRET_KEY = config('SECRET_KEY')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())  # no default — must be set explicitly

# Database
DATABASES = {
  'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': config('DB_NAME'),
    'USER': config('DB_USER'),
    'PASSWORD': config('DB_PASSWORD'),
    'HOST': config('DB_HOST', default='localhost'),
    'PORT': config('DB_PORT', default='5432'),
    # Persistent connections: skip the per-request connect handshake.
    # Health checks ping before reuse so stale connections never 500.
    'CONN_MAX_AGE': 60,
    'CONN_HEALTH_CHECKS': True,
  }
}

# Cache
CACHES = {
  'default': {
    'BACKEND': 'django_redis.cache.RedisCache',
    'LOCATION': config('REDIS_URL'),
    'OPTIONS': {
      'CLIENT_CLASS': 'django_redis.client.DefaultClient',
    }
  }
}

# Celery
CELERY_BROKER_URL = config('REDIS_URL')
CELERY_RESULT_BACKEND = config('REDIS_URL')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# JWT
SIMPLE_JWT = {
  **SIMPLE_JWT,
  'AUTH_COOKIE_SECURE': True,
}

# S3/R2-compatible object storage.
# Django 6 removed DEFAULT_FILE_STORAGE — STORAGES is the only setting that works.
STORAGES = {
  'default': {'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage'},
  'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
AWS_S3_ENDPOINT_URL = config('AWS_S3_ENDPOINT_URL', default='')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='auto')
AWS_S3_SIGNATURE_VERSION = 's3v4'
AWS_S3_CUSTOM_DOMAIN = config('AWS_S3_CUSTOM_DOMAIN', default='')
AWS_S3_FILE_OVERWRITE = False

# Media URLs — custom domain (e.g. R2 public bucket / CDN) wins when set
MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/media/'
MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/' if AWS_S3_CUSTOM_DOMAIN else MEDIA_URL

# Enable real SMS in production
ALPHA_SMS_ENABLED = True

# CORS — bhara.xyz ↔ api.bhara.xyz are same-site
CORS_ALLOWED_ORIGINS = ['https://bhara.xyz']

# Security settings for production
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = 'Strict'
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000  # 1 year — browsers refuse plain HTTP after first visit
SECURE_HSTS_INCLUDE_SUBDOMAINS = False  # api host only; bhara.xyz manages its own policy
SECURE_HSTS_PRELOAD = False
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
