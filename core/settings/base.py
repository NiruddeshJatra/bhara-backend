from pathlib import Path
from decouple import config, Csv  # python-decouple helps manage configuration settings from environment variables.
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent.parent

ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv(), default='127.0.0.1,localhost')  # cast=Csv() treats the value as comma-separated values

# Application definition
INSTALLED_APPS = [
  'django.contrib.admin',
  'django.contrib.auth',
  'django.contrib.contenttypes',
  'django.contrib.sessions',
  'django.contrib.messages',
  'django.contrib.staticfiles',
  'rest_framework',
  'rest_framework_simplejwt',
  'rest_framework_simplejwt.token_blacklist',
  'corsheaders',
  'users',
]

MIDDLEWARE = [
  'corsheaders.middleware.CorsMiddleware',  # Adds CORS headers to allow cross-origin requests from allowed domains
  'django.middleware.security.SecurityMiddleware',  # Enforces security settings like HTTPS redirects and security headers
  'django.contrib.sessions.middleware.SessionMiddleware',  # Creates and manages session data using cookies or database
  'django.middleware.common.CommonMiddleware',  # Handles URL rewriting, content-type parsing, and basic request processing
  'django.middleware.csrf.CsrfViewMiddleware',  # Generates and validates CSRF tokens to prevent cross-site request forgery
  'django.contrib.auth.middleware.AuthenticationMiddleware',  # Attaches user object to request based on session/cookies
  'django.contrib.messages.middleware.MessageMiddleware',  # Manages temporary messages between requests (flash messages)
  'django.middleware.clickjacking.XFrameOptionsMiddleware',  # Adds X-Frame-Options header to prevent clickjacking attacks
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
  {
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
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

WSGI_APPLICATION = 'core.wsgi.application'

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
TIME_ZONE = 'Asia/Dhaka'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Django REST Framework
REST_FRAMEWORK = {
  'DEFAULT_AUTHENTICATION_CLASSES': (
    'rest_framework_simplejwt.authentication.JWTAuthentication',
  ),
  'DEFAULT_PERMISSION_CLASSES': (
    'rest_framework.permissions.IsAuthenticated',
  ),
  'DEFAULT_RENDERER_CLASSES': [
    'rest_framework.renderers.JSONRenderer',
  ],
  'DEFAULT_PARSER_CLASSES': [
    'rest_framework.parsers.JSONParser',
    'rest_framework.parsers.MultiPartParser',
    'rest_framework.parsers.FormParser',
  ],
}

# Base JWT settings
SIMPLE_JWT = {
  'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
  'REFRESH_TOKEN_LIFETIME': timedelta(days=90),
  'ROTATE_REFRESH_TOKENS': True,
  'BLACKLIST_AFTER_ROTATION': True,
  'AUTH_HEADER_TYPES': ('Bearer',),
  'AUTH_COOKIE': 'refresh_token',
  'AUTH_COOKIE_HTTP_ONLY': True,
  'AUTH_COOKIE_SAMESITE': 'Strict',
}

# OTP Configuration
OTP_TTL_SECONDS = 300         # 5 minutes
OTP_DEBUG_VALUE = '111111'    # only used when DEBUG=True
ALPHA_SMS_API_KEY = config('ALPHA_SMS_API_KEY', default='')

# Login Lockout Configuration
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 900   # 15 minutes

# CORS Configuration
CORS_ALLOWED_ORIGINS = [
  "http://localhost:3000",
  "http://127.0.0.1:3000",
]

CORS_ALLOW_CREDENTIALS = True
