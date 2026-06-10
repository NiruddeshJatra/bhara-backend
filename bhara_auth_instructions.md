# Bhara Platform — Developer Instruction Document
## Module: Authentication & Profile Completion (Backend + Frontend)
### Version: 1.0 | Status: Implementation-Ready

---

## 0. HOW TO USE THIS DOCUMENT

This document is self-contained. A developer (human or AI) reading this cold has everything needed to implement the auth and profile completion module without asking questions. Every decision is locked. Do not deviate, optimize, or guess. If something seems missing, it is intentional.

Read sections in order before writing any code. Sections 1–3 are context. Sections 4+ are implementation specs.

---

## 1. PROJECT OVERVIEW

**Bhara** is a peer-to-peer rental platform for Bangladesh. Owners list items they rarely use. Renters borrow those items by paying a fee. Bhara acts as the physical intermediary — items are delivered to and from Bhara, inspected, and then forwarded. Bhara never lets owner and renter deal directly.

### Core Trust Model
Trust is everything. The platform enforces it through a tiered user verification system. No transaction (renting or listing) is possible without full identity verification. This is intentional and non-negotiable.

### Language & Locale
- Target users: Bangladeshi (Bengali-speaking, mobile-first)
- Phone numbers follow BD format: `01XXXXXXXXX` (11 digits), country code `880`
- All districts and thanas are Bangladeshi administrative divisions
- OTP is the primary auth UX (users trained by bKash, Nagad, Pathao)

---

## 2. ALL PLANNING DECISIONS (Context for this module)

### 2.1 Authentication Method
- **Phone number + Password** is the login credential. No email login.
- Email is optional, collected later in profile completion for receipt/notification purposes.
- OTP via SMS is used for: signup phone verification, forgot password flow.
- SMS provider: **Alpha SMS** (`api.sms.net.bd`)
- In `DEBUG=True`: OTP is always hardcoded `111111`. No actual SMS sent.

### 2.2 Signup Flow (3 screens, dedicated pages)
1. Enter phone number → request OTP
2. Enter OTP → receive ephemeral JWT (10 min TTL)
3. Enter full_name, password, marketing_consent → user created, full JWT issued

User is NOT created after OTP verification. Only created at step 3 completion. This prevents ghost accounts.

### 2.3 Session Management
- **Access token**: 1 day TTL, stored in-memory (JS variable / React state), sent as `Authorization: Bearer <token>`
- **Refresh token**: 90 days TTL, stored in `httpOnly` cookie (`Secure`, `SameSite=Strict`), auto-sent by browser
- Silent refresh: on 401, Axios interceptor calls `/auth/token/refresh/` using cookie, gets new access token, retries original request
- Logout: blacklists refresh token server-side, clears cookie

### 2.4 User Trust Levels
Three levels stored in a single `trust_level` CharField:
- `unverified` — signed up, no documents submitted
- `verified` — identity documents submitted and admin-approved
- `partner` — manually elevated by admin based on relationship or transaction history

Badge display:
- `verified` → checkmark badge (e.g., ✓ Verified)
- `partner` → gold/star badge (e.g., ★ Bhara Partner)

### 2.5 Permission Gates
```
trust_level=unverified → browse listings, wishlist only
profile_completed=True + trust_level=verified → can request rentals, create listings
trust_level=partner → same as verified + special badge
```

### 2.6 Profile Completion (2 steps, dedicated pages)
**Step 1** — Personal Info (sets `profile_completed=True` on save):
- profile_picture (optional but nudged)
- date_of_birth (18+ enforced, backend + frontend)
- district (dropdown, 64 BD districts, static data)
- thana (cascading dropdown filtered by district, static data)
- full_address (textarea)

**Step 2** — Identity Verification (admin reviews, sets `trust_level`):
- nid_number (CharField)
- nid_image (govt ID photo — NID, passport, or driving license front)
- institutional_id_image (optional — university/office ID)
- Submission sets `is_approved=None` (pending). Admin sets `True` or `False`.

### 2.7 Document Fields
- No document type dropdowns. Admin visually identifies from the image.
- `is_approved`: nullable BooleanField. `None`=pending/not submitted, `True`=approved, `False`=rejected.
- If rejected: user contacts Bhara via email/phone. Rejection reason NOT stored in DB.

### 2.8 Name
- Single `full_name` CharField. No first_name/last_name split.
- Name change allowed only if user has zero completed transactions. Enforced in backend.

### 2.9 OTP Storage
- Stored in Redis/Django cache. NOT in a database table.
- Cache key: `otp:{purpose}:{phone_number}` → hashed OTP value, TTL 5 min
- Purposes: `signup`, `password_reset`
- On use: cache key deleted immediately

### 2.10 Failed Login Lockout
- 5 consecutive failures → 15-minute lockout
- Tracked in Redis (not DB): key `login_attempts:{phone_number}`
- Returns HTTP 429 with seconds remaining

### 2.11 Image Compression
- All uploaded images compressed via Pillow before saving to storage
- Profile picture: max 800×800px, JPEG, quality 85
- NID image: max 1200×900px, JPEG, quality 90
- Institutional ID image: max 1200×900px, JPEG, quality 90

### 2.12 API Response Envelope
All responses follow:
```json
{
  "success": true,
  "message": "Human-readable message",
  "data": { }
}
```
Errors follow DRF default field-level format inside the envelope:
```json
{
  "success": false,
  "message": "Validation failed",
  "data": {
    "phone_number": ["A user with this phone number already exists."]
  }
}
```

### 2.13 No API Versioning
URLs are `/api/auth/...`, `/api/users/...`. No `/v1/` prefix.

---

## 3. TECH STACK

### Backend
| Concern | Choice |
|---|---|
| Framework | Django 5.x |
| API | Django REST Framework (DRF) |
| Auth tokens | `djangorestframework-simplejwt` |
| Cache / OTP storage | Redis via `django-redis` |
| Async tasks | Celery + Redis broker |
| Image processing | Pillow |
| File storage (dev) | Local filesystem |
| File storage (prod) | AWS S3 via `django-storages` |
| SMS | Alpha SMS (`api.sms.net.bd`) — custom service class |
| Testing | `pytest`, `pytest-django`, `factory_boy` |
| Password hashing | Django default (PBKDF2) |

### Frontend
| Concern | Choice |
|---|---|
| Framework | React 18 + Vite |
| Language | TypeScript |
| Routing | React Router v6 |
| Server state | TanStack React Query v5 |
| HTTP client | Axios with interceptors |
| Forms | React Hook Form + Zod |
| UI components | Radix UI primitives + Tailwind CSS |
| Toasts | `react-hot-toast` (or Sonner, already in package.json) |
| OTP input | `input-otp` (already in package.json) |
| Animations | Framer Motion (already in package.json) |

---

## 4. BACKEND — FOLDER STRUCTURE

```
bhara_backend/
├── core/
│   ├── settings/
│   │   ├── __init__.py         # empty
│   │   ├── base.py             # shared settings
│   │   ├── development.py      # DEBUG=True, local storage, hardcoded OTP
│   │   └── production.py       # S3, real SMS, DEBUG=False
│   ├── __init__.py
│   ├── asgi.py
│   ├── wsgi.py
│   └── urls.py                 # root URL conf, includes app URLs
├── users/
│   ├── migrations/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── factories.py
│   │   ├── test_models.py
│   │   ├── test_views.py
│   │   └── test_serializers.py
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── managers.py
│   ├── models.py
│   ├── serializers.py
│   ├── urls.py
│   ├── validators.py
│   └── views.py
├── services/
│   ├── __init__.py
│   ├── sms.py                  # Alpha SMS integration
│   └── otp.py                  # OTP generation, storage, verification
├── listings/                   # future app, not in scope now
├── rentals/                    # future app, not in scope now
├── reviews/                    # future app, not in scope now
├── notifications/              # future app, not in scope now
├── celery_tasks/
│   ├── __init__.py
│   └── users.py                # send_otp_task
├── conftest.py                 # pytest fixtures
├── manage.py
├── requirements.txt
├── requirements-dev.txt
├── docker-compose.yml
└── .env.example
```

---

## 5. BACKEND — SETTINGS

### 5.1 `core/settings/base.py`
```python
# Installed apps must include:
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

AUTH_USER_MODEL = 'users.User'

REST_FRAMEWORK = {
  'DEFAULT_AUTHENTICATION_CLASSES': (
    'rest_framework_simplejwt.authentication.JWTAuthentication',
  ),
  'DEFAULT_PERMISSION_CLASSES': (
    'rest_framework.permissions.IsAuthenticated',
  ),
}

from datetime import timedelta
SIMPLE_JWT = {
  'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
  'REFRESH_TOKEN_LIFETIME': timedelta(days=90),
  'ROTATE_REFRESH_TOKENS': True,
  'BLACKLIST_AFTER_ROTATION': True,
  'AUTH_HEADER_TYPES': ('Bearer',),
  'AUTH_COOKIE': 'refresh_token',
  'AUTH_COOKIE_HTTP_ONLY': True,
  'AUTH_COOKIE_SECURE': True,       # overridden to False in development.py
  'AUTH_COOKIE_SAMESITE': 'Strict',
}

CACHES = {
  'default': {
    'BACKEND': 'django_redis.cache.RedisCache',
    'LOCATION': env('REDIS_URL', default='redis://127.0.0.1:6379/1'),
    'OPTIONS': {
      'CLIENT_CLASS': 'django_redis.client.DefaultClient',
    }
  }
}

CELERY_BROKER_URL = env('REDIS_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = env('REDIS_URL', default='redis://127.0.0.1:6379/0')

OTP_TTL_SECONDS = 300         # 5 minutes
OTP_DEBUG_VALUE = '111111'    # only used when DEBUG=True
ALPHA_SMS_API_KEY = env('ALPHA_SMS_API_KEY', default='')
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 900   # 15 minutes
```

### 5.2 `core/settings/development.py`
```python
from .base import *

DEBUG = True
SECRET_KEY = 'dev-secret-key-not-for-production'
ALLOWED_HOSTS = ['*']

# Override cookie security for local dev
SIMPLE_JWT = {
  **SIMPLE_JWT,
  'AUTH_COOKIE_SECURE': False,
}

# Local file storage
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Disable real SMS in dev — OTP_DEBUG_VALUE used instead
ALPHA_SMS_ENABLED = False
```

### 5.3 `core/settings/production.py`
```python
from .base import *

DEBUG = False
SECRET_KEY = env('SECRET_KEY')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

# S3 storage
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME')
AWS_S3_FILE_OVERWRITE = False

ALPHA_SMS_ENABLED = True
```

---

## 6. BACKEND — USER MODEL

File: `users/models.py`

### 6.1 Trust Level Choices (defined at top of file)
```python
TRUST_LEVEL_UNVERIFIED = 'unverified'
TRUST_LEVEL_VERIFIED = 'verified'
TRUST_LEVEL_PARTNER = 'partner'

TRUST_LEVEL_CHOICES = [
  (TRUST_LEVEL_UNVERIFIED, 'Unverified'),
  (TRUST_LEVEL_VERIFIED, 'Verified'),
  (TRUST_LEVEL_PARTNER, 'Bhara Partner'),
]
```

### 6.2 User Model
```python
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from uuid import uuid4
from .managers import UserManager

class User(AbstractBaseUser, PermissionsMixin):
  # --- Primary Key ---
  id = models.UUIDField(
    primary_key=True,
    default=uuid4,
    editable=False
  )

  # --- Auth Fields ---
  phone_number = models.CharField(
    max_length=15,
    unique=True,
    db_index=True,
    help_text='Bangladeshi phone number (01XXXXXXXXX). Used as login identifier.'
  )
  full_name = models.CharField(
    max_length=150,
    help_text='Display name shown on listings and profile.'
  )

  # --- Status Flags ---
  is_active = models.BooleanField(default=True)
  is_staff = models.BooleanField(default=False)
  profile_completed = models.BooleanField(
    default=False,
    help_text='True after Step 1 of profile completion is submitted.'
  )
  marketing_consent = models.BooleanField(
    default=False,
    help_text='User opted in to marketing communications.'
  )

  # --- Trust System ---
  trust_level = models.CharField(
    max_length=20,
    choices=TRUST_LEVEL_CHOICES,
    default=TRUST_LEVEL_UNVERIFIED,
    help_text='unverified | verified | partner'
  )
  is_approved = models.BooleanField(
    null=True,
    default=None,
    help_text=(
      'None = no documents submitted or pending review. '
      'True = admin approved. False = admin rejected.'
    )
  )

  # --- Profile Step 1 Fields ---
  profile_picture = models.ImageField(
    upload_to='profile_pictures/',
    null=True,
    blank=True
  )
  date_of_birth = models.DateField(
    null=True,
    blank=True,
    help_text='Must be 18+ years old.'
  )
  district = models.CharField(
    max_length=100,
    blank=True,
    help_text='Selected from BD district list.'
  )
  thana = models.CharField(
    max_length=100,
    blank=True,
    help_text='Selected from thanas under chosen district.'
  )
  full_address = models.TextField(
    blank=True,
    help_text='Free-text full address after district/thana selection.'
  )
  email = models.EmailField(
    null=True,
    blank=True,
    help_text='Optional. Collected during profile completion. Not used for login.'
  )

  # --- Profile Step 2 Fields (Identity Verification) ---
  nid_number = models.CharField(
    max_length=20,
    null=True,
    blank=True,
    help_text='NID number typed by user. No format enforcement — admin visually verifies.'
  )
  nid_image = models.ImageField(
    upload_to='identity/nid/',
    null=True,
    blank=True,
    help_text='Photo of govt ID (NID front, passport, or driving license).'
  )
  institutional_id_image = models.ImageField(
    upload_to='identity/institutional/',
    null=True,
    blank=True,
    help_text='Optional. University or office ID photo.'
  )

  # --- Stats ---
  average_rating = models.DecimalField(
    max_digits=3,
    decimal_places=2,
    default=0.00,
    editable=False
  )

  # --- Timestamps ---
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  objects = UserManager()

  USERNAME_FIELD = 'phone_number'
  REQUIRED_FIELDS = ['full_name']

  class Meta:
    ordering = ['-created_at']
    verbose_name = 'User'
    verbose_name_plural = 'Users'

  def __str__(self):
    return f'{self.full_name} ({self.phone_number})'

  def can_transact(self):
    """Returns True if user can rent or list items."""
    return self.profile_completed and self.trust_level in [
      TRUST_LEVEL_VERIFIED,
      TRUST_LEVEL_PARTNER,
    ]

  def has_completed_transactions(self):
    """Used to gate name changes. Import inline to avoid circular imports."""
    from rentals.models import Rental
    return Rental.objects.filter(
      models.Q(renter=self) | models.Q(owner=self),
      status='completed'
    ).exists()
```

---

## 7. BACKEND — USER MANAGER

File: `users/managers.py`

```python
from django.contrib.auth.models import BaseUserManager

class UserManager(BaseUserManager):

  def create_user(self, phone_number, full_name, password=None, **extra_fields):
    if not phone_number:
      raise ValueError('Phone number is required.')
    if not full_name:
      raise ValueError('Full name is required.')
    user = self.model(
      phone_number=phone_number,
      full_name=full_name,
      **extra_fields
    )
    user.set_password(password)
    user.save(using=self._db)
    return user

  def create_superuser(self, phone_number, full_name, password=None, **extra_fields):
    extra_fields.setdefault('is_staff', True)
    extra_fields.setdefault('is_superuser', True)
    extra_fields.setdefault('trust_level', 'partner')
    return self.create_user(phone_number, full_name, password, **extra_fields)
```

---

## 8. BACKEND — VALIDATORS

File: `users/validators.py`

```python
import re
from datetime import date
from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError


def validate_bd_phone(phone_number):
  """
  Valid formats: 01XXXXXXXXX (11 digits) or +8801XXXXXXXXX or 8801XXXXXXXXX.
  Normalizes to 01XXXXXXXXX before storage.
  """
  phone = phone_number.strip()
  # Strip country code if present
  if phone.startswith('+880'):
    phone = '0' + phone[4:]
  elif phone.startswith('880'):
    phone = '0' + phone[3:]
  pattern = r'^01[3-9]\d{8}$'
  if not re.match(pattern, phone):
    raise ValidationError(
      'Enter a valid Bangladeshi phone number (e.g. 01712345678).'
    )
  return phone


def validate_age_18(date_of_birth):
  """User must be at least 18 years old."""
  today = date.today()
  age = relativedelta(today, date_of_birth).years
  if age < 18:
    raise ValidationError('You must be at least 18 years old.')
  return date_of_birth


def validate_password_strength(password):
  """Minimum 8 chars, at least one letter and one number."""
  if len(password) < 8:
    raise ValidationError('Password must be at least 8 characters.')
  if not re.search(r'[A-Za-z]', password):
    raise ValidationError('Password must contain at least one letter.')
  if not re.search(r'\d', password):
    raise ValidationError('Password must contain at least one number.')
  return password
```

---

## 9. BACKEND — SERVICES

### 9.1 OTP Service
File: `services/otp.py`

```python
import hashlib
import random
import string
from django.core.cache import cache
from django.conf import settings


def _generate_otp():
  """Returns 6-digit OTP string. Hardcoded in DEBUG mode."""
  if settings.DEBUG:
    return settings.OTP_DEBUG_VALUE
  return ''.join(random.choices(string.digits, k=6))


def _hash_otp(otp):
  """SHA-256 hash of OTP. Cache stores hash, not plaintext."""
  return hashlib.sha256(otp.encode()).hexdigest()


def _cache_key(purpose, phone_number):
  return f'otp:{purpose}:{phone_number}'


def create_otp(purpose, phone_number):
  """
  Generates OTP, stores hashed value in cache with TTL.
  Returns the plaintext OTP (to be sent via SMS).
  Purpose: 'signup' | 'password_reset'
  """
  otp = _generate_otp()
  key = _cache_key(purpose, phone_number)
  cache.set(key, _hash_otp(otp), timeout=settings.OTP_TTL_SECONDS)
  return otp


def verify_otp(purpose, phone_number, otp_input):
  """
  Verifies OTP. Returns True and deletes key on success.
  Returns False if not found or doesn't match.
  """
  key = _cache_key(purpose, phone_number)
  stored_hash = cache.get(key)
  if stored_hash is None:
    return False
  if stored_hash != _hash_otp(otp_input):
    return False
  cache.delete(key)
  return True
```

### 9.2 SMS Service
File: `services/sms.py`

```python
import requests
from django.conf import settings
import logging

logger = logging.getLogger('sms')


class AlphaSMSService:
  BASE_URL = 'https://api.sms.net.bd'

  def send(self, phone_number, message):
    """
    Sends SMS via Alpha SMS API.
    In DEBUG mode or when ALPHA_SMS_ENABLED=False, logs instead of sending.
    phone_number: BD format (01XXXXXXXXX)
    """
    if not getattr(settings, 'ALPHA_SMS_ENABLED', False):
      logger.info(f'[SMS MOCK] To: {phone_number} | Message: {message}')
      return {'success': True, 'mock': True}

    # Convert to international format
    recipient = '880' + phone_number[1:]  # 01712345678 -> 8801712345678

    try:
      response = requests.get(
        f'{self.BASE_URL}/sendsms',
        params={
          'api_key': settings.ALPHA_SMS_API_KEY,
          'msg': message,
          'to': recipient,
        },
        timeout=10
      )
      data = response.json()
      if data.get('error') == 0:
        logger.info(f'SMS sent to {phone_number}, request_id={data["data"]["request_id"]}')
        return {'success': True, 'request_id': data['data']['request_id']}
      else:
        logger.error(f'SMS failed: error={data.get("error")}, msg={data.get("msg")}')
        return {'success': False, 'error': data.get('msg')}
    except Exception as e:
      logger.exception(f'SMS exception: {e}')
      return {'success': False, 'error': str(e)}


sms_service = AlphaSMSService()
```

---

## 10. BACKEND — CELERY TASK

File: `celery_tasks/users.py`

```python
from celery import shared_task
from services.sms import sms_service
import logging

logger = logging.getLogger('celery.users')


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_otp_task(self, phone_number, otp, purpose):
  """
  Sends OTP SMS asynchronously.
  purpose: 'signup' | 'password_reset'
  Retries up to 3 times with 30-second delay on failure.
  """
  if purpose == 'signup':
    message = f'Your Bhara signup OTP is: {otp}. Valid for 5 minutes. Do not share this code.'
  elif purpose == 'password_reset':
    message = f'Your Bhara password reset OTP is: {otp}. Valid for 5 minutes. Do not share this code.'
  else:
    message = f'Your Bhara OTP is: {otp}. Valid for 5 minutes.'

  result = sms_service.send(phone_number, message)
  if not result['success']:
    logger.error(f'OTP SMS failed for {phone_number}, purpose={purpose}')
    raise self.retry(exc=Exception(result.get('error', 'SMS send failed')))
```

---

## 11. BACKEND — IMAGE COMPRESSION UTILITY

File: `users/utils.py`

```python
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys


def compress_image(uploaded_file, max_width, max_height, quality=85):
  """
  Compresses and resizes an uploaded image.
  Converts to JPEG. Returns a new InMemoryUploadedFile.

  Args:
    uploaded_file: Django uploaded file object
    max_width: int, max width in pixels
    max_height: int, max height in pixels
    quality: int, JPEG quality (1-95)

  Returns:
    InMemoryUploadedFile ready to assign to an ImageField
  """
  img = Image.open(uploaded_file)

  # Convert to RGB (handles PNG with transparency, CMYK, etc.)
  if img.mode != 'RGB':
    img = img.convert('RGB')

  # Resize maintaining aspect ratio, only if larger than max
  img.thumbnail((max_width, max_height), Image.LANCZOS)

  output = BytesIO()
  img.save(output, format='JPEG', quality=quality, optimize=True)
  output.seek(0)

  return InMemoryUploadedFile(
    output,
    'ImageField',
    f'{uploaded_file.name.rsplit(".", 1)[0]}.jpg',
    'image/jpeg',
    sys.getsizeof(output),
    None
  )
```

---

## 12. BACKEND — SERIALIZERS

File: `users/serializers.py`

### 12.1 OTP Request Serializer
```python
from rest_framework import serializers
from users.validators import validate_bd_phone
from users.models import User

class OTPRequestSerializer(serializers.Serializer):
  phone_number = serializers.CharField(max_length=15)
  purpose = serializers.ChoiceField(choices=['signup', 'password_reset'])

  def validate_phone_number(self, value):
    return validate_bd_phone(value)

  def validate(self, data):
    phone = data['phone_number']
    purpose = data['purpose']
    if purpose == 'signup':
      if User.objects.filter(phone_number=phone).exists():
        raise serializers.ValidationError({
          'phone_number': ['An account with this phone number already exists.']
        })
    elif purpose == 'password_reset':
      if not User.objects.filter(phone_number=phone).exists():
        raise serializers.ValidationError({
          'phone_number': ['No account found with this phone number.']
        })
    return data
```

### 12.2 OTP Verify Serializer
```python
class OTPVerifySerializer(serializers.Serializer):
  phone_number = serializers.CharField(max_length=15)
  otp = serializers.CharField(min_length=6, max_length=6)
  purpose = serializers.ChoiceField(choices=['signup', 'password_reset'])

  def validate_phone_number(self, value):
    return validate_bd_phone(value)
```

### 12.3 Signup Complete Serializer
```python
from users.validators import validate_password_strength

class SignupCompleteSerializer(serializers.Serializer):
  full_name = serializers.CharField(min_length=2, max_length=150)
  password = serializers.CharField(write_only=True)
  marketing_consent = serializers.BooleanField(default=False)

  def validate_password(self, value):
    return validate_password_strength(value)

  def validate_full_name(self, value):
    if not value.strip():
      raise serializers.ValidationError('Full name cannot be blank.')
    return value.strip()
```

### 12.4 Login Serializer
```python
class LoginSerializer(serializers.Serializer):
  phone_number = serializers.CharField(max_length=15)
  password = serializers.CharField(write_only=True)

  def validate_phone_number(self, value):
    return validate_bd_phone(value)
```

### 12.5 Password Reset Complete Serializer
```python
class PasswordResetCompleteSerializer(serializers.Serializer):
  password = serializers.CharField(write_only=True)

  def validate_password(self, value):
    return validate_password_strength(value)
```

### 12.6 Profile Step 1 Serializer
```python
from users.validators import validate_age_18
from users.utils import compress_image

class ProfileStep1Serializer(serializers.ModelSerializer):
  class Meta:
    model = User
    fields = [
      'profile_picture',
      'date_of_birth',
      'district',
      'thana',
      'full_address',
      'email',
    ]

  def validate_date_of_birth(self, value):
    return validate_age_18(value)

  def validate_district(self, value):
    if not value.strip():
      raise serializers.ValidationError('District is required.')
    return value.strip()

  def validate_thana(self, value):
    if not value.strip():
      raise serializers.ValidationError('Thana is required.')
    return value.strip()

  def validate_full_address(self, value):
    if not value.strip():
      raise serializers.ValidationError('Full address is required.')
    return value.strip()

  def validate(self, data):
    required = ['date_of_birth', 'district', 'thana', 'full_address']
    errors = {}
    for field in required:
      if not data.get(field):
        errors[field] = [f'{field.replace("_", " ").title()} is required.']
    if errors:
      raise serializers.ValidationError(errors)
    return data

  def update(self, instance, validated_data):
    # Compress profile picture if provided
    if 'profile_picture' in validated_data and validated_data['profile_picture']:
      validated_data['profile_picture'] = compress_image(
        validated_data['profile_picture'],
        max_width=800,
        max_height=800,
        quality=85
      )
    for attr, value in validated_data.items():
      setattr(instance, attr, value)
    instance.profile_completed = True
    instance.save()
    return instance
```

### 12.7 Profile Step 2 Serializer
```python
class ProfileStep2Serializer(serializers.ModelSerializer):
  class Meta:
    model = User
    fields = [
      'nid_number',
      'nid_image',
      'institutional_id_image',
    ]

  def validate_nid_number(self, value):
    if not value.strip():
      raise serializers.ValidationError('NID number is required.')
    return value.strip()

  def validate_nid_image(self, value):
    if value is None:
      raise serializers.ValidationError('NID image is required.')
    if value.size > 10 * 1024 * 1024:
      raise serializers.ValidationError('Image must be under 10MB.')
    return value

  def update(self, instance, validated_data):
    # Compress NID image
    if 'nid_image' in validated_data and validated_data['nid_image']:
      validated_data['nid_image'] = compress_image(
        validated_data['nid_image'],
        max_width=1200,
        max_height=900,
        quality=90
      )
    # Compress institutional ID image if provided
    if 'institutional_id_image' in validated_data and validated_data['institutional_id_image']:
      validated_data['institutional_id_image'] = compress_image(
        validated_data['institutional_id_image'],
        max_width=1200,
        max_height=900,
        quality=90
      )
    for attr, value in validated_data.items():
      setattr(instance, attr, value)
    # Set pending state
    instance.is_approved = None
    instance.save()
    return instance
```

### 12.8 User Profile Read Serializer
```python
class UserProfileSerializer(serializers.ModelSerializer):
  trust_badge = serializers.SerializerMethodField()
  member_since = serializers.SerializerMethodField()

  class Meta:
    model = User
    fields = [
      'id',
      'phone_number',
      'full_name',
      'email',
      'profile_picture',
      'date_of_birth',
      'district',
      'thana',
      'full_address',
      'trust_level',
      'trust_badge',
      'is_approved',
      'profile_completed',
      'average_rating',
      'marketing_consent',
      'member_since',
      'created_at',
    ]
    read_only_fields = fields

  def get_trust_badge(self, obj):
    if obj.trust_level == 'partner':
      return 'partner'
    if obj.trust_level == 'verified':
      return 'verified'
    return None

  def get_member_since(self, obj):
    return obj.created_at.strftime('%B %Y')
```

### 12.9 Update Full Name Serializer
```python
class UpdateFullNameSerializer(serializers.ModelSerializer):
  class Meta:
    model = User
    fields = ['full_name']

  def validate_full_name(self, value):
    if not value.strip():
      raise serializers.ValidationError('Full name cannot be blank.')
    return value.strip()

  def validate(self, data):
    user = self.instance
    if user.has_completed_transactions():
      raise serializers.ValidationError(
        'Name cannot be changed after completing a transaction.'
      )
    return data
```

---

## 13. BACKEND — VIEWS

File: `users/views.py`

All views use `APIView`. Response helper at top of file:

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
import jwt

from users.models import User
from users import serializers as user_serializers
from services.otp import create_otp, verify_otp
from celery_tasks.users import send_otp_task


def success_response(data=None, message='', status_code=status.HTTP_200_OK):
  return Response({
    'success': True,
    'message': message,
    'data': data or {},
  }, status=status_code)


def error_response(data=None, message='', status_code=status.HTTP_400_BAD_REQUEST):
  return Response({
    'success': False,
    'message': message,
    'data': data or {},
  }, status=status_code)


def _set_refresh_cookie(response, refresh_token_str):
  """Attaches refresh token as httpOnly cookie."""
  response.set_cookie(
    key=settings.SIMPLE_JWT['AUTH_COOKIE'],
    value=refresh_token_str,
    max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
    httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
    secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
    samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE'],
  )


def _clear_refresh_cookie(response):
  response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE'])


def _issue_tokens(user):
  """Returns (access_token_str, refresh_token_obj)."""
  refresh = RefreshToken.for_user(user)
  return str(refresh.access_token), refresh


def _create_ephemeral_token(phone_number, purpose):
  """
  Creates a short-lived JWT (10 min) encoding phone_number and purpose.
  Used between OTP verification and final signup/password-reset completion.
  """
  from datetime import datetime, timedelta
  payload = {
    'phone_number': phone_number,
    'purpose': f'{purpose}_verified',
    'exp': datetime.utcnow() + timedelta(minutes=10),
  }
  return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


def _decode_ephemeral_token(token, expected_purpose):
  """Decodes and validates ephemeral token. Raises jwt exceptions on failure."""
  payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
  if payload.get('purpose') != expected_purpose:
    raise ValueError('Token purpose mismatch.')
  return payload['phone_number']
```

### 13.1 OTP Request View
```
POST /api/auth/otp/request/
Permission: AllowAny
Body: { phone_number, purpose }
```
```python
class OTPRequestView(APIView):
  permission_classes = [AllowAny]

  def post(self, request):
    serializer = user_serializers.OTPRequestSerializer(data=request.data)
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    phone = serializer.validated_data['phone_number']
    purpose = serializer.validated_data['purpose']

    otp = create_otp(purpose, phone)
    send_otp_task.delay(phone, otp, purpose)

    return success_response(message='OTP sent successfully.')
```

### 13.2 OTP Verify View
```
POST /api/auth/otp/verify/
Permission: AllowAny
Body: { phone_number, otp, purpose }
Returns: { ephemeral_token }
```
```python
class OTPVerifyView(APIView):
  permission_classes = [AllowAny]

  def post(self, request):
    serializer = user_serializers.OTPVerifySerializer(data=request.data)
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    phone = serializer.validated_data['phone_number']
    otp = serializer.validated_data['otp']
    purpose = serializer.validated_data['purpose']

    if not verify_otp(purpose, phone, otp):
      return error_response(
        {'otp': ['Invalid or expired OTP. Please try again.']},
        'OTP verification failed.',
        status.HTTP_400_BAD_REQUEST
      )

    ephemeral_token = _create_ephemeral_token(phone, purpose)
    return success_response(
      {'ephemeral_token': ephemeral_token},
      'OTP verified successfully.'
    )
```

### 13.3 Signup Complete View
```
POST /api/auth/signup/complete/
Permission: AllowAny
Headers: Authorization: Bearer <ephemeral_token>
Body: { full_name, password, marketing_consent }
Returns: { access_token, user }
Sets: refresh_token cookie
```
```python
class SignupCompleteView(APIView):
  permission_classes = [AllowAny]

  def post(self, request):
    # Extract and validate ephemeral token from Authorization header
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
      return error_response(message='Ephemeral token required.', status_code=status.HTTP_401_UNAUTHORIZED)
    token = auth_header.split(' ')[1]

    try:
      phone_number = _decode_ephemeral_token(token, 'signup_verified')
    except Exception:
      return error_response(message='Invalid or expired token.', status_code=status.HTTP_401_UNAUTHORIZED)

    serializer = user_serializers.SignupCompleteSerializer(data=request.data)
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    # Guard: phone should not already exist (race condition)
    if User.objects.filter(phone_number=phone_number).exists():
      return error_response(
        {'phone_number': ['An account with this phone number already exists.']},
        'Registration failed.'
      )

    user = User.objects.create_user(
      phone_number=phone_number,
      full_name=serializer.validated_data['full_name'],
      password=serializer.validated_data['password'],
      marketing_consent=serializer.validated_data.get('marketing_consent', False),
    )

    access_token, refresh = _issue_tokens(user)
    response = success_response(
      {
        'access_token': access_token,
        'user': {
          'id': str(user.id),
          'full_name': user.full_name,
          'phone_number': user.phone_number,
          'profile_completed': user.profile_completed,
          'trust_level': user.trust_level,
        }
      },
      'Account created successfully.',
      status.HTTP_201_CREATED
    )
    _set_refresh_cookie(response, str(refresh))
    return response
```

### 13.4 Login View
```
POST /api/auth/login/
Permission: AllowAny
Body: { phone_number, password }
Returns: { access_token, user }
Sets: refresh_token cookie
```
```python
class LoginView(APIView):
  permission_classes = [AllowAny]

  def post(self, request):
    serializer = user_serializers.LoginSerializer(data=request.data)
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    phone = serializer.validated_data['phone_number']
    password = serializer.validated_data['password']

    # Check lockout
    lockout_key = f'login_attempts:{phone}'
    attempts = cache.get(lockout_key, 0)
    if attempts >= settings.LOGIN_MAX_ATTEMPTS:
      ttl = cache.ttl(lockout_key)
      return error_response(
        {'detail': f'Account locked. Try again in {ttl} seconds.'},
        'Too many failed attempts.',
        status.HTTP_429_TOO_MANY_REQUESTS
      )

    user = authenticate(request, username=phone, password=password)

    if user is None:
      # Increment failed attempts
      cache.set(lockout_key, attempts + 1, timeout=settings.LOGIN_LOCKOUT_SECONDS)
      return error_response(
        {'detail': 'Invalid phone number or password.'},
        'Login failed.',
        status.HTTP_401_UNAUTHORIZED
      )

    if not user.is_active:
      return error_response(
        {'detail': 'This account has been deactivated.'},
        'Login failed.',
        status.HTTP_401_UNAUTHORIZED
      )

    # Clear failed attempts on success
    cache.delete(lockout_key)

    access_token, refresh = _issue_tokens(user)
    response = success_response(
      {
        'access_token': access_token,
        'user': {
          'id': str(user.id),
          'full_name': user.full_name,
          'phone_number': user.phone_number,
          'profile_completed': user.profile_completed,
          'trust_level': user.trust_level,
          'is_approved': user.is_approved,
        }
      },
      'Login successful.'
    )
    _set_refresh_cookie(response, str(refresh))
    return response
```

### 13.5 Logout View
```
POST /api/auth/logout/
Permission: IsAuthenticated
Clears cookie, blacklists refresh token
```
```python
class LogoutView(APIView):
  permission_classes = [IsAuthenticated]

  def post(self, request):
    refresh_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE'])
    if refresh_token:
      try:
        token = RefreshToken(refresh_token)
        token.blacklist()
      except Exception:
        pass  # Token already invalid — still clear cookie

    response = success_response(message='Logged out successfully.')
    _clear_refresh_cookie(response)
    return response
```

### 13.6 Token Refresh View
```
POST /api/auth/token/refresh/
Permission: AllowAny
Cookie: refresh_token (auto-sent by browser)
Returns: { access_token }
```
```python
class TokenRefreshView(APIView):
  permission_classes = [AllowAny]

  def post(self, request):
    refresh_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE'])
    if not refresh_token:
      return error_response(message='No refresh token.', status_code=status.HTTP_401_UNAUTHORIZED)
    try:
      refresh = RefreshToken(refresh_token)
      access_token = str(refresh.access_token)
      response = success_response({'access_token': access_token}, 'Token refreshed.')
      # If ROTATE_REFRESH_TOKENS=True, update cookie with new refresh token
      _set_refresh_cookie(response, str(refresh))
      return response
    except Exception:
      response = error_response(message='Invalid or expired refresh token.', status_code=status.HTTP_401_UNAUTHORIZED)
      _clear_refresh_cookie(response)
      return response
```

### 13.7 Password Reset Request View
```
POST /api/auth/password-reset/request/
Body: { phone_number, purpose: "password_reset" }
(Reuses OTPRequestView — same endpoint, different purpose)
```
No separate view needed. Frontend sends `purpose: "password_reset"` to `/api/auth/otp/request/`.

### 13.8 Password Reset Complete View
```
POST /api/auth/password-reset/complete/
Headers: Authorization: Bearer <ephemeral_token>
Body: { password }
```
```python
class PasswordResetCompleteView(APIView):
  permission_classes = [AllowAny]

  def post(self, request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
      return error_response(message='Ephemeral token required.', status_code=status.HTTP_401_UNAUTHORIZED)
    token = auth_header.split(' ')[1]

    try:
      phone_number = _decode_ephemeral_token(token, 'password_reset_verified')
    except Exception:
      return error_response(message='Invalid or expired token.', status_code=status.HTTP_401_UNAUTHORIZED)

    serializer = user_serializers.PasswordResetCompleteSerializer(data=request.data)
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    try:
      user = User.objects.get(phone_number=phone_number)
    except User.DoesNotExist:
      return error_response(message='User not found.', status_code=status.HTTP_404_NOT_FOUND)

    user.set_password(serializer.validated_data['password'])
    user.save(update_fields=['password'])

    # Blacklist all existing refresh tokens for this user
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    for token_obj in OutstandingToken.objects.filter(user=user):
      try:
        token_obj.blacklist()
      except Exception:
        pass

    return success_response(message='Password reset successfully.')
```

### 13.9 Profile Step 1 View
```
PATCH /api/users/profile/step1/
Permission: IsAuthenticated
Body: multipart/form-data { profile_picture?, date_of_birth, district, thana, full_address, email? }
```
```python
class ProfileStep1View(APIView):
  permission_classes = [IsAuthenticated]

  def patch(self, request):
    serializer = user_serializers.ProfileStep1Serializer(
      instance=request.user,
      data=request.data,
      partial=True
    )
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    user = serializer.save()
    return success_response(
      user_serializers.UserProfileSerializer(user).data,
      'Profile updated successfully.'
    )
```

### 13.10 Profile Step 2 View
```
POST /api/users/profile/step2/
Permission: IsAuthenticated
Requires: profile_completed=True
Body: multipart/form-data { nid_number, nid_image, institutional_id_image? }
```
```python
class ProfileStep2View(APIView):
  permission_classes = [IsAuthenticated]

  def post(self, request):
    if not request.user.profile_completed:
      return error_response(
        message='Complete Step 1 of your profile first.',
        status_code=status.HTTP_403_FORBIDDEN
      )

    serializer = user_serializers.ProfileStep2Serializer(
      instance=request.user,
      data=request.data
    )
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    serializer.save()
    return success_response(
      message='Identity documents submitted. Your account is under review.'
    )
```

### 13.11 User Profile View (GET + PATCH name)
```
GET /api/users/profile/     → returns full user profile
PATCH /api/users/profile/   → update full_name only (if no completed transactions)
```
```python
class UserProfileView(APIView):
  permission_classes = [IsAuthenticated]

  def get(self, request):
    serializer = user_serializers.UserProfileSerializer(request.user)
    return success_response(serializer.data)

  def patch(self, request):
    serializer = user_serializers.UpdateFullNameSerializer(
      instance=request.user,
      data=request.data
    )
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')
    serializer.save()
    return success_response(
      user_serializers.UserProfileSerializer(request.user).data,
      'Name updated successfully.'
    )
```

---

## 14. BACKEND — URLS

### `core/urls.py`
```python
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
  path('admin/', admin.site.urls),
  path('api/auth/', include('users.urls.auth')),
  path('api/users/', include('users.urls.users')),
]

if settings.DEBUG:
  urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### `users/urls/auth.py`
```python
from django.urls import path
from users.views import (
  OTPRequestView,
  OTPVerifyView,
  SignupCompleteView,
  LoginView,
  LogoutView,
  TokenRefreshView,
  PasswordResetCompleteView,
)

urlpatterns = [
  path('otp/request/', OTPRequestView.as_view(), name='otp-request'),
  path('otp/verify/', OTPVerifyView.as_view(), name='otp-verify'),
  path('signup/complete/', SignupCompleteView.as_view(), name='signup-complete'),
  path('login/', LoginView.as_view(), name='login'),
  path('logout/', LogoutView.as_view(), name='logout'),
  path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
  path('password-reset/complete/', PasswordResetCompleteView.as_view(), name='password-reset-complete'),
]
```

### `users/urls/users.py`
```python
from django.urls import path
from users.views import (
  UserProfileView,
  ProfileStep1View,
  ProfileStep2View,
)

urlpatterns = [
  path('profile/', UserProfileView.as_view(), name='user-profile'),
  path('profile/step1/', ProfileStep1View.as_view(), name='profile-step1'),
  path('profile/step2/', ProfileStep2View.as_view(), name='profile-step2'),
]
```

---

## 15. BACKEND — TESTING

### Test Conventions
- Test runner: `pytest` with `pytest-django`
- Config: `pytest.ini` or `pyproject.toml` — `DJANGO_SETTINGS_MODULE = core.settings.development`
- All test files in `users/tests/`
- Each test class handles one view or one unit
- Fixtures defined in `conftest.py` at project root
- Use `factory_boy` for model creation; never manually call `User.objects.create` in tests

### `users/tests/factories.py`
```python
import factory
from users.models import User

class UserFactory(factory.django.DjangoModelFactory):
  class Meta:
    model = User

  phone_number = factory.Sequence(lambda n: f'017{n:08d}')
  full_name = factory.Faker('name')
  password = factory.PostGenerationMethodCall('set_password', 'testpass123')
  is_active = True
  profile_completed = False
  trust_level = 'unverified'
  is_approved = None

class VerifiedUserFactory(UserFactory):
  profile_completed = True
  trust_level = 'verified'
  is_approved = True
  district = 'Dhaka'
  thana = 'Mirpur'
  full_address = 'House 5, Road 3, Mirpur-10'
  date_of_birth = factory.LazyFunction(lambda: __import__('datetime').date(1995, 1, 1))
```

### Tests to Write (all must pass before any new feature is added)

**`test_models.py`**
- `test_user_str` — `__str__` returns correct format
- `test_create_user_requires_phone`
- `test_create_user_requires_full_name`
- `test_create_superuser_sets_is_staff`
- `test_can_transact_returns_false_for_unverified`
- `test_can_transact_returns_true_for_verified_and_profile_completed`
- `test_trust_level_default_is_unverified`

**`test_views.py` — OTP**
- `test_otp_request_signup_success`
- `test_otp_request_signup_fails_if_phone_exists`
- `test_otp_request_password_reset_fails_if_phone_not_found`
- `test_otp_verify_success_returns_ephemeral_token`
- `test_otp_verify_fails_with_wrong_otp`
- `test_otp_verify_fails_after_cache_expiry` (use `cache.delete` to simulate)

**`test_views.py` — Signup**
- `test_signup_complete_creates_user`
- `test_signup_complete_sets_refresh_cookie`
- `test_signup_complete_returns_access_token`
- `test_signup_complete_fails_with_invalid_ephemeral_token`
- `test_signup_complete_fails_with_weak_password`

**`test_views.py` — Login**
- `test_login_success`
- `test_login_sets_refresh_cookie`
- `test_login_fails_with_wrong_password`
- `test_login_lockout_after_5_attempts`
- `test_login_lockout_clears_on_success`

**`test_views.py` — Logout**
- `test_logout_clears_cookie`
- `test_logout_blacklists_token`

**`test_views.py` — Token Refresh**
- `test_token_refresh_success_with_cookie`
- `test_token_refresh_fails_without_cookie`

**`test_views.py` — Profile**
- `test_profile_step1_saves_and_sets_profile_completed`
- `test_profile_step1_rejects_under_18_dob`
- `test_profile_step1_requires_district_thana_address`
- `test_profile_step2_requires_step1_first`
- `test_profile_step2_saves_documents_and_sets_pending`
- `test_update_name_allowed_with_no_transactions`
- `test_update_name_blocked_with_completed_transaction`

---

## 16. BACKEND — `docker-compose.yml`

```yaml
version: '3.9'
services:
  redis:
    image: redis:7-alpine
    ports:
      - '6379:6379'
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

Local dev: run `docker-compose up -d` to start Redis. Django and Celery run directly (not containerized in dev).

### Start Celery Worker (dev)
```bash
celery -A core worker --loglevel=info
```

---

## 17. FRONTEND — FOLDER STRUCTURE

```
src/
├── assets/
├── components/
│   ├── auth/
│   │   ├── OtpInput.tsx              # 6-box OTP input using input-otp package
│   │   └── PasswordStrengthBar.tsx
│   ├── common/
│   │   ├── NavBar.tsx
│   │   ├── Footer.tsx
│   │   ├── PageTransition.tsx
│   │   └── ProfileCompletionBanner.tsx  # shown after login if profile incomplete
│   └── ui/                           # Radix-based shadcn components (keep existing)
├── contexts/
│   └── AuthContext.tsx               # current user, access token, login/logout methods
├── hooks/
│   └── useAuth.ts                    # convenience hook consuming AuthContext
├── lib/
│   ├── axios.ts                      # Axios instance + interceptors
│   └── react-query.ts                # QueryClient config
├── pages/
│   ├── auth/
│   │   ├── SignupPhone.tsx            # Step 1: enter phone
│   │   ├── SignupOtp.tsx              # Step 2: enter OTP
│   │   ├── SignupDetails.tsx          # Step 3: full_name, password, consent
│   │   ├── Login.tsx
│   │   ├── ForgotPasswordPhone.tsx
│   │   ├── ForgotPasswordOtp.tsx
│   │   └── ForgotPasswordReset.tsx
│   ├── profile/
│   │   ├── CompleteProfileStep1.tsx
│   │   └── CompleteProfileStep2.tsx
│   └── ... (other pages, not in scope here)
├── services/
│   └── auth.service.ts               # all API calls for auth + profile
├── stores/
│   └── authStore.ts                  # Zustand-free: just AuthContext state
├── types/
│   └── auth.ts                       # TypeScript types
├── utils/
│   ├── bd-districts.ts               # static list of BD districts + thanas
│   └── validators.ts                 # Zod schemas
├── App.tsx
├── main.tsx
└── index.css
```

---

## 18. FRONTEND — TYPES

File: `src/types/auth.ts`

```typescript
export interface User {
  id: string;
  phone_number: string;
  full_name: string;
  email: string | null;
  profile_picture: string | null;
  date_of_birth: string | null;
  district: string;
  thana: string;
  full_address: string;
  trust_level: 'unverified' | 'verified' | 'partner';
  trust_badge: 'verified' | 'partner' | null;
  is_approved: boolean | null;
  profile_completed: boolean;
  average_rating: string;
  marketing_consent: boolean;
  member_since: string;
  created_at: string;
}

export interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface ApiResponse<T = Record<string, unknown>> {
  success: boolean;
  message: string;
  data: T;
}

export interface ProfileStep1Form {
  date_of_birth: string;       // 'YYYY-MM-DD'
  district: string;
  thana: string;
  full_address: string;
  profile_picture?: File | null;
  email?: string;
}

export interface ProfileStep2Form {
  nid_number: string;
  nid_image: File;
  institutional_id_image?: File | null;
}
```

---

## 19. FRONTEND — AXIOS INSTANCE + INTERCEPTORS

File: `src/lib/axios.ts`

```typescript
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  withCredentials: true,   // CRITICAL: sends httpOnly refresh cookie automatically
});

// Request interceptor — attach access token
api.interceptors.request.use((config) => {
  const token = window.__accessToken__;   // see AuthContext for how this is set
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor — silent token refresh on 401
let isRefreshing = false;
let refreshQueue: Array<(token: string) => void> = [];

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // Queue requests while refresh is in progress
        return new Promise((resolve) => {
          refreshQueue.push((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            resolve(api(originalRequest));
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const response = await api.post('/auth/token/refresh/');
        const newToken = response.data.data.access_token;
        window.__accessToken__ = newToken;
        refreshQueue.forEach((cb) => cb(newToken));
        refreshQueue = [];
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      } catch {
        // Refresh failed — user must log in again
        window.__accessToken__ = null;
        window.location.href = '/auth/login';
        return Promise.reject(error);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;
```

Note: `window.__accessToken__` is a simple in-memory store. Declare it in `src/main.tsx`:
```typescript
declare global {
  interface Window {
    __accessToken__: string | null;
  }
}
window.__accessToken__ = null;
```

---

## 20. FRONTEND — AUTH CONTEXT

File: `src/contexts/AuthContext.tsx`

```typescript
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, AuthState } from '@/types/auth';
import api from '@/lib/axios';

interface AuthContextValue extends AuthState {
  login: (accessToken: string, user: User) => void;
  logout: () => Promise<void>;
  setUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On app load: try silent token refresh to restore session
  useEffect(() => {
    const tryRestoreSession = async () => {
      try {
        const response = await api.post('/auth/token/refresh/');
        const { access_token } = response.data.data;
        window.__accessToken__ = access_token;
        setAccessToken(access_token);

        // Fetch user profile with new token
        const profileResponse = await api.get('/users/profile/');
        setUserState(profileResponse.data.data);
      } catch {
        // No valid session — user must log in
        window.__accessToken__ = null;
      } finally {
        setIsLoading(false);
      }
    };
    tryRestoreSession();
  }, []);

  const login = (token: string, userData: User) => {
    window.__accessToken__ = token;
    setAccessToken(token);
    setUserState(userData);
  };

  const logout = async () => {
    try {
      await api.post('/auth/logout/');
    } finally {
      window.__accessToken__ = null;
      setAccessToken(null);
      setUserState(null);
    }
  };

  const setUser = (userData: User) => setUserState(userData);

  return (
    <AuthContext.Provider value={{
      user,
      accessToken,
      isAuthenticated: !!user,
      isLoading,
      login,
      logout,
      setUser,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
```

---

## 21. FRONTEND — AUTH SERVICE

File: `src/services/auth.service.ts`

All API calls go through this file. Pages and components never call `api` directly for auth.

```typescript
import api from '@/lib/axios';
import { User, ProfileStep1Form, ProfileStep2Form } from '@/types/auth';

const authService = {
  async requestOtp(phone_number: string, purpose: 'signup' | 'password_reset') {
    const res = await api.post('/auth/otp/request/', { phone_number, purpose });
    return res.data;
  },

  async verifyOtp(phone_number: string, otp: string, purpose: 'signup' | 'password_reset') {
    const res = await api.post('/auth/otp/verify/', { phone_number, otp, purpose });
    return res.data.data.ephemeral_token as string;
  },

  async signupComplete(ephemeralToken: string, payload: {
    full_name: string;
    password: string;
    marketing_consent: boolean;
  }) {
    const res = await api.post('/auth/signup/complete/', payload, {
      headers: { Authorization: `Bearer ${ephemeralToken}` }
    });
    return res.data.data as { access_token: string; user: User };
  },

  async login(phone_number: string, password: string) {
    const res = await api.post('/auth/login/', { phone_number, password });
    return res.data.data as { access_token: string; user: User };
  },

  async logout() {
    await api.post('/auth/logout/');
  },

  async getProfile() {
    const res = await api.get('/users/profile/');
    return res.data.data as User;
  },

  async updateProfile(data: FormData) {
    const res = await api.patch('/users/profile/step1/', data, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return res.data.data as User;
  },

  async submitIdentity(data: FormData) {
    const res = await api.post('/users/profile/step2/', data, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return res.data;
  },

  async updateFullName(full_name: string) {
    const res = await api.patch('/users/profile/', { full_name });
    return res.data.data as User;
  },

  async passwordResetComplete(ephemeralToken: string, password: string) {
    const res = await api.post('/auth/password-reset/complete/', { password }, {
      headers: { Authorization: `Bearer ${ephemeralToken}` }
    });
    return res.data;
  },
};

export default authService;
```

---

## 22. FRONTEND — ZOD VALIDATION SCHEMAS

File: `src/utils/validators.ts`

```typescript
import { z } from 'zod';

const bdPhoneRegex = /^01[3-9]\d{8}$/;

export const phoneSchema = z.object({
  phone_number: z
    .string()
    .regex(bdPhoneRegex, 'Enter a valid Bangladeshi phone number (e.g. 01712345678)')
});

export const otpSchema = z.object({
  otp: z.string().length(6, 'OTP must be exactly 6 digits').regex(/^\d+$/, 'OTP must be numeric')
});

export const signupDetailsSchema = z.object({
  full_name: z.string().min(2, 'Full name must be at least 2 characters').max(150),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Za-z]/, 'Password must contain at least one letter')
    .regex(/\d/, 'Password must contain at least one number'),
  confirm_password: z.string(),
  marketing_consent: z.boolean().default(false),
}).refine(
  (data) => data.password === data.confirm_password,
  { message: 'Passwords do not match', path: ['confirm_password'] }
);

export const loginSchema = z.object({
  phone_number: z.string().regex(bdPhoneRegex, 'Enter a valid Bangladeshi phone number'),
  password: z.string().min(1, 'Password is required'),
});

const eighteenYearsAgo = () => {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 18);
  return d;
};

export const profileStep1Schema = z.object({
  date_of_birth: z
    .string()
    .min(1, 'Date of birth is required')
    .refine((val) => {
      const dob = new Date(val);
      return dob <= eighteenYearsAgo();
    }, 'You must be at least 18 years old'),
  district: z.string().min(1, 'District is required'),
  thana: z.string().min(1, 'Thana is required'),
  full_address: z.string().min(5, 'Please enter a valid address'),
  email: z.string().email('Enter a valid email').optional().or(z.literal('')),
  profile_picture: z.instanceof(File).optional().nullable(),
});

export const profileStep2Schema = z.object({
  nid_number: z.string().min(1, 'NID number is required'),
  nid_image: z.instanceof(File, { message: 'NID image is required' }),
  institutional_id_image: z.instanceof(File).optional().nullable(),
});
```

---

## 23. FRONTEND — ROUTES

File: `src/App.tsx`

```typescript
// All auth routes are public (no auth required)
// Profile completion routes require isAuthenticated only (not trust_level)
// Transactional routes require can_transact (profile_completed + trust_level=verified|partner)

// Route guards:
// <PublicRoute>        — redirect to /advertisements if already logged in
// <AuthRoute>         — redirect to /auth/login if not logged in
// <TransactionRoute>  — redirect to /profile/complete if can't transact

// Route list for auth + profile module:
/auth/signup              → SignupPhone (PublicRoute)
/auth/signup/otp          → SignupOtp (PublicRoute) — receives phone via location.state
/auth/signup/details      → SignupDetails (PublicRoute) — receives ephemeral_token via location.state
/auth/login               → Login (PublicRoute)
/auth/forgot-password     → ForgotPasswordPhone (PublicRoute)
/auth/forgot-password/otp → ForgotPasswordOtp (PublicRoute) — receives phone via location.state
/auth/forgot-password/reset → ForgotPasswordReset (PublicRoute) — receives ephemeral_token via location.state
/profile/complete/step1   → CompleteProfileStep1 (AuthRoute)
/profile/complete/step2   → CompleteProfileStep2 (AuthRoute)
/profile                  → Profile (AuthRoute)
```

State is passed between signup steps using React Router's `location.state`, not URL params or localStorage. If a user navigates directly to `/auth/signup/otp` without state, redirect them back to `/auth/signup`.

---

## 24. FRONTEND — PAGE SPECS

### Visual Reference
These pages must visually replicate the design from the provided reference files. The color scheme, gradients, card styles, button styles, and form layout follow the existing components exactly:
- Background: `bg-gradient-to-b from-green-300 to-lime-100/20`
- Card: `bg-gradient-to-b from-white to-lime-50 rounded-xl shadow-lg`
- Primary button: `bg-green-600 hover:bg-green-700 text-white`
- Error text: `text-red-500 text-xs flex items-center gap-1`
- Label: `text-xs sm:text-sm font-medium text-gray-700`
- Input icons: left-aligned, `h-4 w-4 text-gray-400`
- Animations: `animate-fade-up`, `animate-fade-up delay-100/200/300`
- All pages include `<NavBar />` at top and `<Footer />` at bottom

---

### Page: `SignupPhone.tsx` (`/auth/signup`)
**Layout:** Centered card, max-w-md, same card style as Login reference.

**Contents:**
- Heading: "Create Account"
- Subheading: "Enter your phone number to get started"
- Single input: Phone number, placeholder `01XXXXXXXXX`, `type="tel"`, left icon: `Phone`
- Helper text below input: "We'll send a 6-digit OTP to this number"
- Submit button: "Send OTP" — full width, green
- Link below card: "Already have an account? Sign in" → `/auth/login`

**Behavior:**
1. On submit: validate phone with `phoneSchema` (Zod + React Hook Form)
2. Call `authService.requestOtp(phone, 'signup')`
3. On success: `navigate('/auth/signup/otp', { state: { phone_number: phone } })`
4. On error: show inline error from API response under the input

---

### Page: `SignupOtp.tsx` (`/auth/signup/otp`)
**Guard:** If `location.state?.phone_number` is missing → redirect to `/auth/signup`

**Contents:**
- Heading: "Verify Your Number"
- Subheading: "Enter the 6-digit code sent to `{phone_number}`"
- OTP input: Use `input-otp` package, 6 boxes, auto-focus, auto-advance on digit entry
- Countdown timer: "Resend OTP in 4:32" — grey, updates every second. When 0: becomes "Resend OTP" button (green text link)
- Submit button: "Verify" — full width, green
- Back link: "← Change number" → `/auth/signup`

**Behavior:**
1. On mount: start 5-minute countdown
2. On "Resend": call `authService.requestOtp(phone, 'signup')`, restart timer
3. On submit: call `authService.verifyOtp(phone, otp, 'signup')`
4. On success: `navigate('/auth/signup/details', { state: { ephemeral_token } })`
5. On error: show "Invalid or expired OTP" below OTP input, clear OTP boxes

---

### Page: `SignupDetails.tsx` (`/auth/signup/details`)
**Guard:** If `location.state?.ephemeral_token` missing → redirect to `/auth/signup`

**Contents:**
- Heading: "Almost There!"
- Subheading: "Set up your account details"
- Input: Full Name, placeholder "Your full name", left icon: `User`
- Input: Password, `type="password"`, left icon: `Lock`, show/hide toggle eye icon (right)
- Password strength bar (visual, 5-level: based on length + uppercase + lowercase + digit + special char)
- Input: Confirm Password, same styling
- Checkbox: Marketing consent — "I'd like to receive updates and offers from Bhara" (unchecked by default)
- Submit button: "Create Account" — full width, green

**Behavior:**
1. Validate with `signupDetailsSchema`
2. Call `authService.signupComplete(ephemeral_token, { full_name, password, marketing_consent })`
3. On success: call `authContext.login(access_token, user)`, `navigate('/advertisements')`
4. Show persistent banner: "Complete your profile to start renting" (see `ProfileCompletionBanner`)
5. On error: show field-level errors

---

### Page: `Login.tsx` (`/auth/login`)
**Visual reference:** Existing `Login.tsx` reference file — replicate exactly including decorative blur circles, icon placement, and "Remember me" + "Forgot Password?" row layout.

**Key changes from old design:**
- Field label "Phone Number" (not Email). Input `type="tel"`, icon: `Phone`
- Remove email verification logic — it no longer exists
- "Forgot Password?" is a `Link` → `/auth/forgot-password` (not inline handler)
- On submit: `authService.login(phone_number, password)`

---

### Page: `ForgotPasswordPhone.tsx`, `ForgotPasswordOtp.tsx`, `ForgotPasswordReset.tsx`
Same structure as Signup trio but with `purpose='password_reset'`.

`ForgotPasswordReset.tsx`:
- One input: New password + show/hide
- Submit calls `authService.passwordResetComplete(ephemeral_token, password)`
- On success: `navigate('/auth/login')` with success toast

---

### Page: `CompleteProfileStep1.tsx` (`/profile/complete/step1`)
**Guard:** `AuthRoute` only (logged in). If `profile_completed=true`: redirect to `/profile/complete/step2`

**Layout:** Same card style. Max-w-xl. Step progress indicator at top (Step 1 of 2 — filled circle → line → empty circle).

**Contents (single scrollable form):**
- Profile picture upload — circular preview area, tap to upload, "Upload Photo" label. Uses `react-dropzone`. Shows preview on select.
- Date of Birth — date input (`type="date"`) or date picker, with helper "Must be 18 or older"
- District — `<select>` dropdown, options from `bd-districts.ts` static list
- Thana — `<select>` dropdown, options filtered by selected district (re-renders on district change)
- Full Address — `<textarea>`, placeholder "House/Road/Area details"
- Email (optional) — `type="email"`, helper "For receipts and notifications (optional)"
- Submit button: "Save & Continue" — full width, green

**Behavior:**
1. Validate with `profileStep1Schema`
2. Build FormData (multipart — for image)
3. Call `authService.updateProfile(formData)`
4. On success: update `authContext.setUser(updatedUser)`, `navigate('/profile/complete/step2')`

---

### Page: `CompleteProfileStep2.tsx` (`/profile/complete/step2`)
**Guard:** `AuthRoute`. If `is_approved === true`: redirect to `/profile`. If `profile_completed === false`: redirect to `/profile/complete/step1`.

**Layout:** Same card. Step indicator: Step 2 of 2 — both circles filled.

**Contents:**
- NID Number input — text, placeholder "Your NID/Passport/License number"
- NID Image upload — drag-and-drop box (same style as `NationalIdStep.tsx` reference). Label: "Upload your Govt. ID (NID front, Passport, or Driving License)"
- Institutional ID upload (optional) — same drag-and-drop. Label: "Upload University or Office ID (optional)"
- Info box (amber/yellow): "Your documents are reviewed by Bhara within 24–48 hours."
- Submit button: "Submit for Verification" — full width, green
- "Skip for now" link below button → `/advertisements` (user can come back later)

**Behavior:**
1. Validate with `profileStep2Schema`
2. Build FormData
3. Call `authService.submitIdentity(formData)`
4. On success: toast "Documents submitted! We'll notify you once reviewed.", `navigate('/advertisements')`

---

### Component: `ProfileCompletionBanner.tsx`
Shown persistently after login if user's `profile_completed === false` OR `trust_level === 'unverified'`.

```
Displayed as a sticky top banner (below NavBar) or a bottom floating pill.
Text: "Complete your profile to start renting →"
Color: amber/yellow background
Click: navigate to /profile/complete/step1 or /profile/complete/step2 based on state
Dismiss: user can close but banner reappears on next login
```

---

## 25. FRONTEND — STATIC DATA: BD DISTRICTS & THANAS

File: `src/utils/bd-districts.ts`

Structure:
```typescript
export interface District {
  name: string;
  thanas: string[];
}

export const BD_DISTRICTS: District[] = [
  { name: 'Dhaka', thanas: ['Mirpur', 'Gulshan', 'Dhanmondi', 'Mohammadpur', 'Tejgaon', /* ... all thanas */] },
  { name: 'Chittagong', thanas: ['Pahartali', 'Halishahar', /* ... */] },
  // all 64 districts
];

export const getThanas = (districtName: string): string[] => {
  return BD_DISTRICTS.find(d => d.name === districtName)?.thanas ?? [];
};
```

Populate all 64 districts and their thanas from official BD administrative data. This is static — no API call needed.

---

## 26. CODE CONVENTIONS

### Both Frontend and Backend
- **Indentation:** 2 spaces. No tabs. Enforced.
- **Quotes:** Single quotes in Python. Double quotes in TypeScript/JSX.
- **Trailing comma:** Yes in Python dicts/lists when multi-line. Yes in TypeScript objects/arrays.
- **Line length:** Max 100 characters.
- **No commented-out code** in committed files.

### Backend (Python)
- Snake_case for all variables, functions, file names.
- PascalCase for classes.
- Docstrings on all public methods.
- Never use bare `except:` — always specify exception type.
- Never import inside function body except to break circular imports (comment why).

### Frontend (TypeScript)
- PascalCase for components and types.
- camelCase for variables, functions, hooks.
- All components are functional. No class components.
- Props interfaces named `{ComponentName}Props`.
- Every API call is in `auth.service.ts` — no `api.get/post` inside components.
- No `any` type unless absolutely unavoidable (comment why).
- Use `const` by default. `let` only if reassignment is needed.

---

## 27. ENVIRONMENT VARIABLES

### Backend `.env.example`
```
SECRET_KEY=
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
REDIS_URL=redis://127.0.0.1:6379/1
ALPHA_SMS_API_KEY=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=
AWS_S3_REGION_NAME=ap-southeast-1
DATABASE_URL=postgres://user:pass@localhost:5432/bhara
```

### Frontend `.env.example`
```
VITE_API_URL=http://localhost:8000/api
```

---

## 28. REQUIREMENTS

### `requirements.txt`
```
Django>=5.0
djangorestframework
djangorestframework-simplejwt
django-redis
django-cors-headers
django-storages[s3]
celery
redis
Pillow
PyJWT
python-dateutil
requests
python-decouple
boto3
```

### `requirements-dev.txt`
```
pytest
pytest-django
factory-boy
pytest-cov
```

---

## 29. WHAT IS OUT OF SCOPE FOR THIS MODULE

The following will be specified in separate instruction documents:
- Listing creation, viewing, and management
- Rental request flow
- Reviews and ratings
- Notifications
- Admin dashboard
- Search and filtering
- Payment integration

---

## 30. ARCHITECTURE CORRECTIONS & SETTINGS REFACTOR

### 30.1 Dependency & Environment Variable Fix
**The Error:** The original document listed `python-decouple` in requirements but used `django-environ` syntax (`env.list()`, `env()`).
**The Correction:** Replace all instances of `env()` with `decouple.config()`.

### 30.2 Strict Settings Separation
`base.py` must **never** contain variables that are meant to be overwritten. It should only contain universal truths for the application.

**Remove from `base.py`:**
- `CACHES`
- `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND`
- Environment-specific keys in `SIMPLE_JWT` (`AUTH_COOKIE_SECURE`)
- Database configurations

**Add to `core/settings/base.py`:**
```python
from decouple import config, Csv
from datetime import timedelta

ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv(), default='127.0.0.1,localhost')

# Base JWT settings (No environment-specific security flags here)
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
```

---

## 31. DEVELOPMENT ENVIRONMENT (NO DOCKER/REDIS REQUIRED)

To ensure developers can run the project immediately without a heavy infrastructure footprint, `development.py` must default to local, synchronous alternatives. 

**Update `core/settings/development.py`:**
```python
from .base import *
from decouple import config

DEBUG = True
SECRET_KEY = config('SECRET_KEY', default='dev-secret-key-not-for-production')

# 1. Database: Use SQLite3 for local dev
DATABASES = {
  'default': {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': BASE_DIR / 'db.sqlite3',
  }
}

# 2. Cache: Use Local Memory Cache (Removes Redis dependency for local OTP storage)
CACHES = {
  'default': {
    'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    'LOCATION': 'unique-snowflake',
  }
}

# 3. Celery: Execute tasks synchronously in the same thread (Removes Celery worker dependency)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_STORE_EAGER_RESULT = True

# 4. JWT: Allow non-HTTPS cookies locally
SIMPLE_JWT = {
  **SIMPLE_JWT,
  'AUTH_COOKIE_SECURE': False,
}
```

**Update `core/settings/production.py`:**
```python
from .base import *
from decouple import config

# Must explicitly define Redis, Postgres, and secure cookies here
DATABASES = {
  'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': config('DB_NAME'),
    # ... other db credentials ...
  }
}

CACHES = {
  'default': {
    'BACKEND': 'django_redis.cache.RedisCache',
    'LOCATION': config('REDIS_URL'),
    # ...
  }
}

SIMPLE_JWT = {
  **SIMPLE_JWT,
  'AUTH_COOKIE_SECURE': True,
}
```

---

## 32. DATABASE TRANSACTIONS & PERFORMANCE

### 32.1 Atomic Transactions
Multiple consecutive database operations must be wrapped in atomic blocks to prevent partial data states if an exception occurs mid-execution. 

Apply `from django.db import transaction` and use `@transaction.atomic` on the `post` or `patch` methods of the following views:
- `SignupCompleteView`
- `ProfileStep1View`
- `ProfileStep2View`

### 32.2 Performance Bitter Truth: Synchronous Image Compression
**Warning:** The current architecture uses Pillow to compress images inside the `update` method of the Serializer. Doing this *inside* an atomic transaction blocks the database lock while the CPU processes the image. 

**Strict Implementation Rule:** Perform image compression *before* opening the database transaction, or run it at the view level before passing data to `serializer.save()`.

---

## 33. SECURITY ENHANCEMENTS

### 33.1 OTP Rate Limiting (Anti-Spam)
The original document locks out login attempts but leaves the OTP generation endpoint completely exposed to SMS bombing attacks.

**Implementation Rule:** Add DRF Throttling to `OTPRequestView`.
```python
from rest_framework.throttling import AnonRateThrottle

class OTPRateThrottle(AnonRateThrottle):
    rate = '3/minute' # Max 3 OTP requests per minute per IP

# Apply to view
class OTPRequestView(APIView):
    throttle_classes = [OTPRateThrottle]
    # ...
```

---

## 34. CRITICAL INTEGRATION TESTS (FLOW PROTECTION)

To ensure future changes do not break the strict sequence of the auth module, add a dedicated End-to-End flow test class.

**Add to `users/tests/test_flows.py`:**
- `test_full_user_lifecycle_flow`:
    1. POST `/api/auth/otp/request/` (Signup)
    2. POST `/api/auth/otp/verify/` -> Capture `ephemeral_token`
    3. POST `/api/auth/signup/complete/` -> Capture `access_token`
    4. PATCH `/api/users/profile/step1/` -> Ensure `profile_completed` becomes `True`
    5. POST `/api/users/profile/step2/` -> Ensure `is_approved` becomes `None` (pending)
    6. Verify final DB state for the user object matches the expected outputs.

---

## 35. DEVELOPER SETUP & COMMANDS

Use these exact commands to bootstrap the environment.

### Backend Setup
```bash
# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 3. Set environment variable to use dev settings
export DJANGO_SETTINGS_MODULE=core.settings.development # Windows: set DJANGO_SETTINGS_MODULE=core.settings.development

# 4. Run migrations
python manage.py migrate

# 5. Run the server
python manage.py runserver
```

### Backend Testing
```bash
# Run all tests with coverage
pytest --cov=. -v
```

### Frontend Setup
```bash
# 1. Install dependencies
npm install

# 2. Start Vite dev server
npm run dev
```
```

*End of document. This document fully specifies the auth and profile completion module. No implementation decision is left to the developer's judgment.*
