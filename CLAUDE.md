# bhara-backend — Project Brain

## What This Is

Django REST API backend for Bhara — a peer-to-peer rental marketplace. Users list items, others rent them; the platform handles auth, listings, rentals, and payments. Built spec-first from `bhara_rebuild_spec.md`.

## Stack

- **Python / Django 6.0** — ORM, migrations, settings
- **Django REST Framework** — ViewSets, serializers, permissions
- **djangorestframework-simplejwt** + **token_blacklist** — JWT auth with refresh rotation
- **django-filter** — ProductFilter for availability/price/search filtering
- **Celery + Redis** — async tasks (OTP SMS delivery)
- **django-storages[s3] / boto3** — S3 media storage (production)
- **Pillow** — image compression/validation
- **pytest-django** — test runner (`conftest.py` + `pytest.ini`)

## File Structure

```
core/
├── settings/
│   ├── base.py          ← shared settings; SERVICE_FEE_RATE = Decimal('0.20')
│   ├── development.py   ← DEBUG=True, LocMemCache, SQLite
│   └── production.py    ← ALLOWED_HOSTS must be set explicitly; CORS_ALLOWED_ORIGINS
├── responses.py         ← SINGLE SOURCE for {success, message, data} envelope
├── urls.py              ← root URL conf; api/auth/, api/users/, api/listings/
├── celery.py            ← Celery app instance
services/
├── otp.py               ← OTP create/verify with hmac.compare_digest + brute-force lockout
└── sms.py               ← AlphaSMS via POST (not GET — prevents proxy log leakage)
users/
├── models.py            ← custom User; can_transact() = profile_completed + trust_level != 'unverified'
├── views.py             ← all auth views; imports success_response/error_response from core.responses
├── urls/auth.py         ← /api/auth/ routes
├── urls/users.py        ← /api/users/ routes
└── tests/               ← 70 auth tests (OTP brute-force, SMS caps, lockout TTL, token rotation, ephemeral token reuse)
listings/
├── models.py            ← Product, ProductImage, PricingTier, UnavailablePeriod
├── constants.py         ← CATEGORY_CHOICES, STATUS_CHOICES = [draft, active, suspended]
├── serializers.py       ← image compression in validate_images() (OUTSIDE transaction)
├── filters.py           ← ProductFilter; availability filter via Q-exclude
├── views.py             ← ProductViewSet; no caching; F() for views_count
├── urls.py              ← DefaultRouter at api/listings/
└── tests/               ← 19 listings tests (visibility, create validation, availability filter)
celery_tasks/
└── users.py             ← send_otp_task (async SMS delivery)
```

## API Endpoints

| Method | URL | Auth | Description |
|--------|-----|------|-------------|
| POST | `/api/auth/signup/request-otp/` | None | Send OTP to phone |
| POST | `/api/auth/signup/verify-otp/` | None | Verify OTP → ephemeral token |
| POST | `/api/auth/signup/complete/` | Ephemeral JWT | Create account |
| POST | `/api/auth/login/` | None | Login → access + refresh cookie |
| POST | `/api/auth/logout/` | Auth | Blacklist + clear cookie |
| POST | `/api/auth/password/reset/request-otp/` | None | Password reset OTP |
| POST | `/api/auth/password/reset/verify-otp/` | None | Verify → ephemeral token |
| POST | `/api/auth/password/reset/complete/` | Ephemeral JWT | Set new password |
| POST | `/api/auth/token/refresh/` | Refresh cookie | Rotate refresh token |
| GET/POST | `/api/listings/` | None/Auth | List active products / create listing |
| GET | `/api/listings/{id}/` | None | Retrieve active product |
| PUT/PATCH | `/api/listings/{id}/` | Owner | Update listing |
| DELETE | `/api/listings/{id}/` | Owner | Delete listing |
| GET | `/api/listings/my_products/` | Auth | Owner's listings (all statuses) |

## Key Conventions

- **Response envelope**: always use `success_response()` / `error_response()` from `core/responses.py`. Never construct `Response({'success': ...})` inline in views.
- **Ephemeral tokens**: `authentication_classes=[]` required on views that consume ephemeral tokens (prevents SessionAuthentication CSRF 403). Views: `SignupCompleteView`, `PasswordResetCompleteView`.
- **Single-use JTI**: after consuming an ephemeral token, call `_mark_jti_used(jti)` immediately. Check `cache.get(f'used_jti:{jti}')` on decode.
- **OTP brute-force**: `otp_attempts:{purpose}:{phone}` in cache; locked at 5 fails. `hmac.compare_digest` for timing-safe comparison.
- **SMS caps**: `sms_cap:minute:{phone}` (TTL 60s) + `sms_cap:day:{phone}` (TTL 86400s), day limit = 5.
- **Login lockout TTL guard**: `cache.ttl(key) if hasattr(cache, 'ttl') else settings.LOGIN_LOCKOUT_SECONDS` — LocMemCache has no `.ttl()`.
- **Token rotation**: blacklist incoming refresh → `RefreshToken.for_user(user)` → set new cookie. Never reuse.
- **Image compression**: in `validate_images()` serializer method, OUTSIDE any DB transaction (spec §3.1). Uses `compress_image(1200×900, q=85)`.
- **Product status default = 'active'**: direct publish — no pre-approval queue.
- **`has_blocking_rentals()`**: guarded by `apps.is_installed('rentals')` so listings tests pass before rentals app exists.
- **`can_transact()`**: checked in `ProductViewSet.perform_create` — returns 403 if false.
- **CheckConstraint** uses `condition=` in Django 6.0 (not `check=` — that's Django 5.x).
- **`django_filters`**: in `INSTALLED_APPS`. ProductFilter uses `django_filters.FilterSet`.
- **F() for views_count**: `Product.objects.filter(pk=pk).update(views_count=F('views_count') + 1)` — skips owner's own views.
- **Pagination**: `PageNumberPagination`, `page_size=20`, `max_page_size=80`.

## Settings Structure

- `DJANGO_SETTINGS_MODULE=core.settings.development` (dev) / `core.settings.production` (prod)
- `SERVICE_FEE_RATE = Decimal('0.20')` in `base.py`
- `LOGIN_MAX_ATTEMPTS = 5`, `LOGIN_LOCKOUT_SECONDS = 900` in `base.py`
- `OTP_TTL_SECONDS = 300`, `OTP_DEBUG_VALUE = '111111'` (DEBUG only) in `base.py`

## Running Tests

```bash
pytest                        # all 89 tests
pytest users/                 # 70 auth tests
pytest listings/              # 19 listings tests
pytest -x -v                  # stop on first failure, verbose
```

## Spec

Full rebuild spec in `bhara_rebuild_spec.md`. Sections implemented so far:
- §2 — core/responses.py extraction ✅
- §3 — listings app (Product, images, pricing tiers, availability) ✅
- §9 — auth hardening (brute-force, SMS caps, lockout TTL, token rotation, ephemeral JTI) ✅

## Skills Active

- `after-change` (global) — Update CLAUDE.md + PROGRESSION.md, commit, push. Trigger: "update docs and commit", "land these changes"
