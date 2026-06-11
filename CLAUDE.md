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
│   └── production.py    ← ALLOWED_HOSTS must be set explicitly; CORS_ALLOWED_ORIGINS; CONN_MAX_AGE=60
├── responses.py         ← SINGLE SOURCE for {success, message, data} envelope
├── pagination.py        ← StandardResultsSetPagination + paginated_success_response (shared by all apps)
├── urls.py              ← root URL conf; api/auth/, api/users/, api/listings/, api/rentals/
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
├── filters.py           ← ProductFilter; availability filter via Q-exclude (incl. accepted/in_progress rentals)
├── services.py          ← get_blocked_dates(product, start=None, end=None) → set of dates; window args push overlap filter into SQL
├── admin.py             ← ProductAdmin; suspend/re-activate actions; image + pricing tier inlines
├── views.py             ← ProductViewSet; no caching; F() for views_count
├── urls.py              ← DefaultRouter at api/listings/
└── tests/               ← 25 listings tests (visibility, create validation, availability filter, perf regressions)
rentals/
├── state_machine.py     ← ALLOWED_TRANSITIONS dict + TransitionError + get_actor_role + role_matches (§4.2)
├── models.py            ← Rental (transition() method), RentalPhoto (uploaded_by), PaymentRecord (append-only)
├── serializers.py       ← RentalCreateSerializer (all §4.4 create guards), RentalDetailSerializer (settlement block)
├── views.py             ← RentalViewSet — 8 endpoints per §4.5; never sets rental.status directly
├── urls.py              ← DefaultRouter at api/rentals/
├── admin.py             ← RentalAdmin; transition actions; PaymentRecord add-only inline (recorded_by auto-set)
├── migrations/
└── tests/               ← 58 tests (transition matrix, double-booking, §5.3 guard, snapshot, photos, query counts, stale-instance re-check)
reviews/
├── models.py            ← Review (UUID pk, UniqueConstraint rental+reviewer); _recompute_ratings() on save
├── serializers.py       ← ReviewCreateSerializer (server-derives direction/reviewee); ReviewSerializer
├── views.py             ← ReviewViewSet — create/list/pending; list is AllowAny; pending requires auth
├── urls.py              ← DefaultRouter at api/reviews/
├── admin.py             ← ReviewAdmin; list+delete only; has_change_permission=False
├── migrations/
└── tests/               ← 21 tests (creation rules, aggregation math, list filtering, pending)
celery_tasks/
└── users.py             ← send_otp_task (async SMS delivery)
docs/
├── bhara_rebuild_spec.md     ← full rebuild spec (§1–§9)
├── bhara_auth_instructions.md ← auth module spec (still authoritative for auth)
└── INSTALLATION.md           ← setup instructions
pyrightconfig.json       ← points Pyright to venv (venvPath + venv keys)
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
| POST | `/api/rentals/` | Auth (renter) | Create rental request |
| GET | `/api/rentals/my-rentals/` | Auth | Rentals where I'm renter |
| GET | `/api/rentals/my-listings-rentals/` | Auth | Rentals where I'm owner |
| GET | `/api/rentals/{id}/` | Participant/Staff | Detail + payment_records + settlement |
| POST | `/api/rentals/{id}/accept/` | Owner | pending → accepted |
| POST | `/api/rentals/{id}/reject/` | Owner | pending → rejected |
| POST | `/api/rentals/{id}/cancel/` | Renter | → cancelled |
| GET/POST | `/api/rentals/{id}/photos/` | Participant/Staff | Rental documentation photos |
| POST | `/api/reviews/` | Auth | Submit review (direction + reviewee derived server-side) |
| GET | `/api/reviews/?product={id}` | None | Public: renter_to_owner reviews for a product |
| GET | `/api/reviews/?user={id}` | None | Public: reviews received by a user |
| GET | `/api/reviews/pending/` | Auth | My completed rentals awaiting my review |

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
- **Pagination**: `StandardResultsSetPagination` in `core/pagination.py` (`page_size=20`, `max_page_size=80`) — single source, do NOT redefine per app. Paginated list endpoints (listings list/my_products, rentals my-rentals/my-listings-rentals, reviews list/pending) return `data = {count, next, previous, results}`. Use `paginated_success_response(viewset, qs, serializer_class)` for GenericViewSet actions.
- **Composite indexes**: `Rental` has `(product, status, start_date, end_date)` + `(renter, status)` + `(owner, status)`; `Product` has `(status, -created_at)`; `Review` has `(product, direction)`. Add to `Meta.indexes` — keep migrations in sync.
- **Transition saves**: `Rental._apply()` and auto-reject use `save(update_fields=['status', 'status_history', 'updated_at'])` — never full-row save inside the accept lock. Auto-reject uses `bulk_update` (sets `updated_at` manually — `bulk_update` skips `auto_now`).
- **Transition status re-check**: every `Rental.transition()` runs in `atomic()` with the rental row `select_for_update`-locked and `status` re-read before validation — a stale in-memory instance raises `TransitionError` instead of double-applying. Lock order is always product → rental (accept locks product first); never lock the reverse.
- **Auth throttles**: `LoginRateThrottle` 10/min/IP on login (bounds password spraying + victim-lockout DoS); `OTPDailyRateThrottle` 20/day/IP on OTP request (bounds SMS billing attacks — 3/min alone allowed 4,320 SMS/day/IP). Tests call `cache.clear()` in `setUp` so throttle history never leaks between tests.
- **Signup TOCTOU**: `create_user` wrapped in `try/except IntegrityError` → 400, not 500 — the unique constraint is the real guard, the `exists()` check is just UX.
- **Prod Redis must use `maxmemory-policy noeviction`** — eviction silently wipes lockout counters and used-JTI keys (disables brute-force protection, enables ephemeral-token replay).
- **Filter `distinct=True`**: `min_price`/`max_price`/`duration_unit` on ProductFilter join `pricing_tiers` — `distinct=True` required or products with several matching tiers duplicate.
- **`get_blocked_dates(product, start, end)`**: always pass the window when checking a specific date range — without it the product's entire rental history is fetched and expanded.
- **Rental list vs detail prefetch**: `payment_records` prefetched only for `retrieve` — `RentalListSerializer` never reads them.
- **Tests hit the real dev `db.sqlite3`** — `conftest.py` no-ops `django_db_setup`. NEVER run two pytest invocations concurrently (cross-run corruption, observed). Suite takes ~9 min.
- **Rental status transitions**: always call `rental.transition(new_status, actor, note='')` — never assign `rental.status` directly. `ALLOWED_TRANSITIONS` in `rentals/state_machine.py` is the single source of truth.
- **Pricing snapshot**: `unit_price`, `base_cost`, `service_fee`, `owner_payout`, `security_deposit` are frozen at create time from `PricingTier.price * duration`. Changing the tier afterward has no effect.
- **PaymentRecord is append-only**: no edit/delete in admin. Corrections go in as offsetting records. `recorded_by` auto-set to `request.user` in `RentalAdmin.save_formset`.
- **§5.3 completion guard**: `in_progress → completed` blocked unless rent_collected ≥ base_cost, deposit fully settled (collected == returned + withheld), and owner_payout record present. Each missing piece raises `TransitionError` with a specific message.
- **Double-booking guard**: `pending → accepted` wraps in `transaction.atomic()` + `Product.objects.select_for_update()`. Overlapping accepted/in_progress rentals raise `TransitionError`; overlapping pending requests are auto-rejected with note 'Auto-rejected: dates were booked'.
- **`has_completed_transactions()`**: uses `Q(renter=self) | Q(owner=self)` — Rental has no `user` field.
- **`success_response` / `error_response` `data` arg**: uses `{} if data is None else data` — NOT `data or {}`. An empty list `[]` is a valid response body; falsy-coercion would silently replace it with `{}`.
- **Review direction + reviewee**: always derived server-side in `ReviewCreateSerializer.validate()` from who the reviewer is. Client sends only `{rental_id, rating, comment}`.
- **Review aggregation**: `Review._recompute_ratings()` runs on every `save()`. renter_to_owner only updates `product.average_rating`; all reviews update `reviewee.average_rating`. Both via `aggregate(Avg)` + `.update()` — atomic, no SELECT then SET.
- **Spec files moved to `docs/`**: `bhara_rebuild_spec.md`, `bhara_auth_instructions.md`, `INSTALLATION.md` are in `docs/` not root.

## Settings Structure

- `DJANGO_SETTINGS_MODULE=core.settings.development` (dev) / `core.settings.production` (prod)
- `SERVICE_FEE_RATE = Decimal('0.20')` in `base.py`
- `LOGIN_MAX_ATTEMPTS = 5`, `LOGIN_LOCKOUT_SECONDS = 900` in `base.py`
- `OTP_TTL_SECONDS = 300`, `OTP_DEBUG_VALUE = '111111'` (DEBUG only) in `base.py`

## Running Tests

```bash
pytest                        # all 179 tests (~9 min — tests hit real dev SQLite; never run two suites at once)
pytest users/                 # 70 auth tests
pytest listings/              # 25 listings tests
pytest rentals/               # 58 rentals tests (matrix, double-booking, §5.3, snapshot, photos, query counts, state re-check)
pytest reviews/               # 21 reviews tests (creation rules, aggregation, list, pending)
pytest -x -v                  # stop on first failure, verbose
```

## Spec

Full rebuild spec in `docs/bhara_rebuild_spec.md`. Sections implemented so far:
- §2 — core/responses.py extraction ✅
- §3 — listings app (Product, images, pricing tiers, availability) ✅
- §4 — rentals app (Rental model, state machine, endpoints, double-booking guard) ✅
- §5 — PaymentRecord (append-only), settlement block in detail, §5.3 completion guard ✅
- §6 — Django admin (RentalAdmin + ProductAdmin) ✅
- §7 — reviews app (Review model, aggregation, 4 endpoints, admin) ✅
- §9 — auth hardening (brute-force, SMS caps, lockout TTL, token rotation, ephemeral JTI) ✅

## Skills Active

- `after-change` (global) — Update CLAUDE.md + PROGRESSION.md, commit, push. Trigger: "update docs and commit", "land these changes"
