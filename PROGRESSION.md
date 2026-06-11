# bhara-backend — Codebase Progression

Sequential history of every significant change. Read top-to-bottom for full picture; skim headers for specific context.

---

## Phase 0 — Project Bootstrap
**2026-06-04 — initial scaffold with custom user model**

- Django 6.0 project initialized; custom `User` model (`users.User`) set as `AUTH_USER_MODEL`.
- Settings split into `base / development / production`. JWT via `djangorestframework-simplejwt` + `token_blacklist`.
- Basic OTP signup/login flow (request OTP → verify → complete). Celery wired for async SMS delivery.
- `services/otp.py` + `services/sms.py` stubbed. `conftest.py` + `pytest.ini` for pytest-django.

---

## Phase 1 — Auth Hardening (§9) + Response Extraction (§2)
**2026-06-11 — OTP brute-force, SMS caps, lockout TTL fix, token rotation, single-use ephemeral tokens**

- **`core/responses.py`** (NEW): extracted `success_response` / `error_response` from `users/views.py` into a single module. All views import from here — never inline the envelope.
- **`services/otp.py`**: added `hmac.compare_digest` for timing-safe OTP comparison; attempt counter (`otp_attempts:{purpose}:{phone}`) locks OTP after 5 failed attempts.
- **`services/sms.py`**: switched `requests.get` → `requests.post` with OTP in POST body (prevents proxy log leakage).
- **`users/views.py`**:
  - Per-phone SMS caps: `sms_cap:minute:{phone}` (TTL 60s) + `sms_cap:day:{phone}` (TTL 86400s), day limit = 5.
  - Login lockout: replaced broken `time.time()` approach with `cache.ttl()` guard; LocMemCache fallback to `LOGIN_LOCKOUT_SECONDS`.
  - Token refresh: blacklist incoming refresh → `RefreshToken.for_user(user)` → issue fresh cookie. Real rotation.
  - Ephemeral token JTI: `jti=uuid4()` in payload; `used_jti:{jti}` cached 10 min. `SignupCompleteView` and `PasswordResetCompleteView` mark JTI used after action.
  - Both completion views get `authentication_classes=[]` (prevents SessionAuthentication CSRF 403 on ephemeral token endpoints).
  - `OTPVerifyRateThrottle` with scope `otp_verify` (10/min) added — separate from `OTPRateThrottle` (scope `otp_request`) so the two don't share a cache key.
- **`core/settings/production.py`**: `ALLOWED_HOSTS` must be explicit (removed fragile `.split(',')` fallback); added `CORS_ALLOWED_ORIGINS`, secure cookie flags.
- **`users/tests/test_views.py`**: 5 new test classes — `OTPBruteForceTest`, `SMSCapTest`, `LoginLockoutTTLTest`, `TokenRotationTest`, `EphemeralTokenSingleUseTest` (35 new tests; 70 total).

---

## Phase 2 — Listings App (§3)
**2026-06-11 — Product model, images, pricing tiers, availability filter, full viewset**

- **`listings/`** (NEW app):
  - `models.py`: `Product` (UUID pk, status default `active`), `ProductImage` (related_name `images`), `PricingTier` (UniqueConstraint per product+duration_unit), `UnavailablePeriod` (CheckConstraint via `condition=` — Django 6.0 API).
  - `constants.py`: `STATUS_CHOICES = [draft, active, suspended]` (no rented/maintenance).
  - `validators.py`: `validate_image_file` (≤5MB, jpg/png), `validate_purchase_year`.
  - `serializers.py`: image compression (`compress_image(1200×900, q=85)`) in `validate_images()` — OUTSIDE any DB transaction per spec §3.1. Nested pricing tiers + unavailable periods on create/update.
  - `filters.py`: `ProductFilter` with search, location, price range, duration_unit, ordering, and `filter_availability` (Q-exclude for single-date and range overlap; additionally excludes accepted/in_progress rentals via guarded `apps.is_installed('rentals')` import).
  - `views.py`: `ProductViewSet` — AllowAny for list/retrieve, IsAuthenticated otherwise; `can_transact()` gate on create; `has_blocking_rentals()` gate on update/destroy; `my_products` action; F()-based views_count increment (skips owner).
  - `urls.py`: `DefaultRouter` at `api/listings/`.
- **`core/settings/base.py`**: added `django_filters` + `listings` to `INSTALLED_APPS`; `SERVICE_FEE_RATE = Decimal('0.20')`.
- **`requirements.txt`**: added `django-filter`.
- **`core/urls.py`**: wired `api/listings/` include.
- **`listings/tests/`**: 19 tests — `ListingVisibilityTest` (draft/suspended visibility), `ListingCreateTest` (can_transact gating, image validation), `AvailabilityFilterTest`.
- Total: 89 tests passing.

---

## Code Review Fixes
**2026-06-11 — address 6 bugs/suggestions from post-merge review**

- **`users/views.py`**: fixed TOCTOU race in ephemeral JTI check — replaced `cache.get() + cache.set()` with atomic `cache.add()` in `_decode_ephemeral_token`; removed now-redundant `_mark_jti_used`.
- **`listings/serializers.py`**: `images` field set `required=False` (create still enforced in `validate()`); `_parse_nested_list` normalizes each string element in a list (multipart repeated keys); `_validate_nested` passes `context=self.context` to child serializers; renamed `_pricing_tiers`/`_unavailable_periods` → `pricing_tiers_data`/`unavailable_periods_data`; extracted `_replace_related` helper used in `update()`.
- **`listings/filters.py`**: price ordering now uses `Min('pricing_tiers__price')` annotation + tie-break on `id` — avoids duplicate rows and unstable pagination from multi-tier products.
- **`users/tests/test_views.py`**: 2 new tests — `test_attempt_counter_reset_after_success`, `test_attempt_counter_reset_on_new_otp`.
- **`listings/tests/test_views.py`**: 3 new tests — owner retrieve 404 on own draft, views_count increments for non-owner, views_count unchanged for owner.
- Total: 94 tests passing.

---

## Phase 3 — Rentals App (§4–§6)
**2026-06-11 — Rental state machine, endpoints, PaymentRecord, completion guard, admin**

- **`rentals/state_machine.py`** (NEW): `ALLOWED_TRANSITIONS` dict is single source of truth for all status edges. `TransitionError`, `get_actor_role`, `role_matches` helpers. Views never assign `rental.status` directly.
- **`rentals/models.py`** (NEW): `Rental` with frozen pricing snapshot fields (`unit_price`, `base_cost`, `service_fee`, `owner_payout`, `security_deposit` — all set at create, never recomputed). `transition(new_status, actor, note)` method enforces the table + per-edge guards: pending→accepted uses `select_for_update` inside `atomic()` to prevent double-booking and auto-rejects overlapping pending requests; accepted→cancelled(renter) blocks if `start_date ≤ today`; in_progress→completed blocked by §5.3 payment completeness check with specific error per missing piece. `RentalPhoto` adds `uploaded_by` FK. `PaymentRecord` append-only with 6 record types.
- **`rentals/serializers.py`** (NEW): `RentalCreateSerializer` validates all §4.4 create guards (can_transact, renter≠owner, active product, tier exists, duration≤max, start≥today, no UnavailablePeriod overlap, no duplicate request). `RentalDetailSerializer` nests `payment_records` + computed `settlement` block `{rent_paid, deposit_held, deposit_returned, owner_paid}`.
- **`rentals/views.py`** (NEW): `RentalViewSet` — 8 endpoints per §4.5. `get_queryset` always scoped to `Q(renter=user) | Q(owner=user)` (staff see all). No complete/in_progress public endpoints — admin-only transitions.
- **`rentals/admin.py`** (NEW): `RentalAdmin` — colored status column, settlement summary, all pricing fields readonly, `PaymentRecord` inline (add-only; `save_formset` auto-sets `recorded_by=request.user`), 3 transition actions via `rental.transition()`. `RentalPhoto` readonly inline.
- **`listings/admin.py`** (NEW): `ProductAdmin` with suspend/re-activate actions; image thumbnails + pricing tier inlines.
- **`listings/services.py`** (NEW): `get_blocked_dates(product)` returns set of date objects from owner UnavailablePeriods + accepted/in_progress rental date ranges.
- **`users/models.py`**: fixed `has_completed_transactions()` — was querying `user=self` (no such field); now uses `Q(renter=self) | Q(owner=self)`.
- **`pyrightconfig.json`** (NEW): `venvPath` + `venv` keys point Pyright/Pylance to the project venv so import errors from `rest_framework` etc. are resolved.
- Total: 141 tests passing (47 new — exhaustive transition matrix, double-booking + concurrent guard, §5.3 guard per missing piece, pricing snapshot immutability).
