# Bhara Platform — Master Rebuild Specification
## Modules: Listings, Rentals, Payments, Reviews + Auth Hardening + Frontend Rewiring
### Version: 1.0 | Status: Implementation-Ready
### Companion to: `bhara_auth_instructions.md` (auth module spec — still authoritative for auth)

---

## 0. HOW TO USE THIS DOCUMENT

This document locks every product and engineering decision for the pre-launch rebuild.
It extends the existing `bhara_backend` (the `core/` + `users/` rebuild) with the domain
apps the live site needs, and defines exactly how the existing frontend is rewired to it
**without changing the UI design**. Read top to bottom. Do not deviate or guess.

Code conventions, response envelope, settings layout, and testing conventions are
inherited from `bhara_auth_instructions.md` §26–28 (2-space indent, envelope
`{success, message, data}`, pytest + factory_boy, settings split base/dev/prod).

---

## 1. LOCKED DECISIONS (from product discussion, June 2026)

| # | Decision | Value |
|---|----------|-------|
| D1 | Auth at launch | Phone + OTP (the rebuild). Email auth retired. No user migration — current DB is test data and will be wiped. |
| D2 | Payments at launch | Offline (cash / bKash P2P / Nagad). The system **records** every money movement via staff-entered `PaymentRecord`s. No gateway. |
| D3 | Rental handover control | **Bhara staff only** for physical-world transitions (`in_progress`, `completed`). Owners only accept/reject; renters only cancel. Matches the FAQ's intermediary promise. |
| D4 | Service fee | **20%, deducted from owner's earnings.** Single source of truth: `SERVICE_FEE_RATE = Decimal('0.20')` in settings. Renter pays the listed price; owner receives 80%. The 8% figure in `PriceCalculationStep.tsx` is a bug — remove. |
| D5 | Reviews | Minimal real reviews ship at launch. Hardcoded fake reviews removed. |
| D6 | Notifications | None at launch. No SMS notifications, no in-app center. (Auth OTP SMS is unaffected.) |
| D7 | Admin surface | Django admin runs operations at launch (verification, rental transitions, payment recording, listing moderation). The custom React admin dashboard is parked: its routes are removed from `App.tsx`, code stays in repo for v2. |
| D8 | Repos | `bhara_backend` rebuild becomes THE backend. Live `backend/` is retired after cutover. `backend/api/` is archived immediately (contains non-running code). One frontend repo: the live one, rewired. |
| D9 | Deferred to v2 | Favorites/wishlist (tab hidden), payment gateway, notifications, React admin dashboard, in-app messaging. |

---

## 2. TARGET ARCHITECTURE

```
bhara_backend/
├── core/                    # settings, urls, celery (exists)
├── users/                   # auth + profiles (exists — hardened per §9)
├── services/                # sms.py, otp.py (exists)
├── listings/                # NEW — port of advertisements app, fixed
├── rentals/                 # NEW — state machine + PaymentRecord
├── reviews/                 # NEW — minimal reviews
├── celery_tasks/            # exists
└── conftest.py
```

Root URL conf additions:
```python
path('api/listings/', include('listings.urls')),
path('api/rentals/', include('rentals.urls')),
path('api/reviews/', include('reviews.urls')),
```
All responses use the `{success, message, data}` envelope via the shared
`success_response` / `error_response` helpers — **move these from `users/views.py`
into `core/responses.py`** and import everywhere.

New settings (base.py):
```python
from decimal import Decimal
SERVICE_FEE_RATE = Decimal('0.20')   # deducted from owner payout
```

---

## 3. LISTINGS APP (port of `advertisements`, corrected)

### 3.1 Models
Port from live `backend/advertisements/models.py` with these changes only:

**Product**
- Keep: UUID pk, owner FK, title, category, product_type, description, location,
  security_deposit, purchase_year, original_price, ownership_history,
  views_count, rental_count, average_rating, timestamps.
- `status` choices reduced to: `draft`, `active`, `suspended`.
  - `rented` is REMOVED as a status — whether an item is currently out is derived
    from its rentals, never stored on the product.
  - `maintenance` removed (was unused).
- Listings publish directly to `active` (creator is already identity-verified).
  Admin can `suspend`. No pre-publication review queue at launch.
- Add `db_index=True` on `status`, `category`, `location`.

**ProductImage** — unchanged. Compress via `users.utils.compress_image`
(max 1200×900, quality 85) before save, OUTSIDE any transaction.

**PricingTier** — unchanged (duration_unit day/week/month, integer `price` in Taka,
`max_period`, unique per (product, duration_unit)).

**UnavailablePeriod** — keep the live repo's `UnavailableDate` shape (single date or
range with CheckConstraint) but rename model to `UnavailablePeriod`,
related_name `unavailable_periods`. These represent OWNER-declared blocks only.
Rental-occupied dates are computed from rentals (§4.6), never written here.

### 3.2 Visibility & permissions (fixes the live bug where drafts were public)
```
list/retrieve (anonymous or any user)  → status='active' only
my_products (authenticated)            → all own products, any status
create                                 → IsAuthenticated AND user.can_transact()
update/partial_update/destroy          → owner only; blocked if product has any
                                         rental in status accepted|in_progress
suspend/unsuspend                      → staff only (Django admin action)
```
`User.can_transact()` (add to users/models.py):
```python
def can_transact(self):
  """Verified identity + completed profile — required to list or rent."""
  return self.profile_completed and self.trust_level in ('verified', 'partner')
```

### 3.3 ViewSet rules
- `ModelViewSet` with `get_queryset` branching by action exactly as §3.2.
  No `queryset_owner`-style references (that was the NameError in `backend/api/`).
- `select_related('owner')` + `prefetch_related('images', 'pricing_tiers',
  'unavailable_periods')` on every list path.
- Filters: keep live `ProductFilter` (search/location/min_price/max_price/
  availability/ordering) but availability filtering must ALSO exclude products
  with overlapping `accepted`/`in_progress` rentals.
- Pagination: PageNumberPagination, page_size 20, max 80.
- **NO response caching.** All Redis response caching from the live repo is dropped
  (it served stale and potentially cross-user data). Postgres + indexes is fast
  enough at launch scale. Revisit only with real traffic data.
- `views_count`: increment with `F()` expression inside `retrieve`, throttled to
  ignore the owner's own views. Delete the separate `increment_views` endpoint.
- Serializer validation: 1–8 images, each ≤5MB jpeg/png; ≥1 pricing tier;
  security_deposit ≥ 0; purchase_year a valid year ≤ current.

---

## 4. RENTALS APP (the core rebuild)

### 4.1 Status set — matches the frontend's existing color system exactly
```
pending      → yellow   (renter requested)
accepted     → blue     (owner approved; awaiting Bhara handover)
in_progress  → green    (Bhara delivered item to renter)
completed    → purple   (item back via Bhara, inspected, settled)
rejected     → red      (owner declined)
cancelled    → orange   (renter or staff cancelled before in_progress)
```

### 4.2 Transition table (single source of truth)
```python
# rentals/state_machine.py
ALLOWED_TRANSITIONS = {
  'pending':     {'accepted': 'owner', 'rejected': 'owner', 'cancelled': 'renter_or_staff'},
  'accepted':    {'in_progress': 'staff', 'cancelled': 'renter_or_staff'},
  'in_progress': {'completed': 'staff'},
  'completed':   {},
  'rejected':    {},
  'cancelled':   {},
}
```
Enforced in ONE place — `Rental.transition(new_status, actor, note='')` — which:
1. Validates `new_status` is reachable from current status.
2. Validates the actor's role (owner / renter / staff) for that edge.
3. Appends `{status, timestamp, actor_id, note}` to `status_history`.
4. Runs edge-specific guards (§4.4).
5. Saves inside the caller's transaction.
Views NEVER set `rental.status` directly. (The live bug — views wrote `'accepted'`
while the model declared `'approved'`, so accepted rentals vanished from every
frontend filter — becomes impossible.)

### 4.3 Model
```python
class Rental(models.Model):
  id = UUIDField(pk)
  product = FK(listings.Product, PROTECT, related_name='rentals')
  owner = FK(User, PROTECT, related_name='rentals_as_owner')     # denormalized at create
  renter = FK(User, PROTECT, related_name='rentals_as_renter')
  start_date = DateField()
  end_date = DateField()                  # computed from duration at create
  duration = PositiveIntegerField()
  duration_unit = CharField(day|week|month)
  # Pricing snapshot — frozen at request time, never recomputed:
  unit_price = DecimalField()             # tier price at request time
  base_cost = DecimalField()              # unit_price * duration  (what renter pays)
  service_fee = DecimalField()            # base_cost * SERVICE_FEE_RATE
  owner_payout = DecimalField()           # base_cost - service_fee
  security_deposit = DecimalField()       # product.security_deposit at request time
  purpose = CharField(choices)            # event|personal|professional|other
  notes = TextField(blank)
  status = CharField(choices, default='pending', db_index=True)
  status_history = JSONField(default=list)
  created_at / updated_at
```

### 4.4 Edge guards
- **create (→pending):** renter.can_transact(); renter != owner; product.status=='active';
  duration_unit has a tier; duration ≤ tier.max_period; start_date ≥ today;
  no overlap with owner UnavailablePeriods or this renter's own pending/accepted
  rental of the same product (no duplicate requests).
- **pending→accepted:** wrap in `transaction.atomic()` with
  `Product.objects.select_for_update().get(...)`; re-check no overlapping
  `accepted`/`in_progress` rental exists for [start_date, end_date]. On success,
  auto-reject all other PENDING requests for the same product with overlapping
  dates (history note: 'Auto-rejected: dates were booked'). This kills the
  double-booking race in the live code.
- **accepted→cancelled (renter):** only if `start_date > today`.
- **in_progress→completed (staff):** requires PaymentRecords present (§5.3 guard).
  On success: `product.rental_count` += 1 (F expression).

### 4.5 Endpoints
```
POST   /api/rentals/                     create request            (renter)
GET    /api/rentals/my-rentals/          rentals where I'm renter
GET    /api/rentals/my-listings-rentals/ rentals where I'm owner
GET    /api/rentals/{id}/                detail (participant or staff only)
POST   /api/rentals/{id}/accept/         pending→accepted          (owner)
POST   /api/rentals/{id}/reject/         pending→rejected          (owner, optional reason)
POST   /api/rentals/{id}/cancel/         →cancelled                (renter)
GET/POST /api/rentals/{id}/photos/       documentation photos      (participants+staff)
```
There are deliberately NO complete / confirm-return / in-progress endpoints in the
public API — those transitions exist only as Django admin actions (§6). The
frontend buttons that called them are removed (§8.4).
get_queryset is ALWAYS scoped: `Q(renter=user) | Q(owner=user)` (staff see all).
The live repo's unscoped `/rentals/` listing is gone.

### 4.6 Availability derivation
A product is unavailable on date D iff: an owner UnavailablePeriod covers D, OR an
`accepted`/`in_progress` rental's [start_date, end_date] covers D. One queryset
helper `listings.services.get_blocked_dates(product)` used by both the
availability endpoint and the filter.

### 4.7 RentalPhoto
Keep live model (pre_rental / post_rental, ≤5MB jpeg/png) with two fixes:
uploads allowed only while status in accepted|in_progress|completed, and
uploader recorded (`uploaded_by` FK). Visible to participants + staff.

---

## 5. PAYMENTS (record-only) — `rentals/models.py`

### 5.1 Model
```python
class PaymentRecord(models.Model):
  RECORD_TYPES = [
    ('rent_collected', 'Rent collected from renter'),
    ('deposit_collected', 'Security deposit collected from renter'),
    ('deposit_returned', 'Security deposit returned to renter'),
    ('deposit_withheld', 'Deposit (partially) withheld for damage'),
    ('owner_payout', 'Payout to owner (after service fee)'),
    ('refund', 'Refund to renter'),
  ]
  METHODS = [('cash', 'Cash'), ('bkash', 'bKash'), ('nagad', 'Nagad'), ('bank', 'Bank transfer')]

  id = UUIDField(pk)
  rental = FK(Rental, PROTECT, related_name='payment_records')
  record_type = CharField(choices=RECORD_TYPES)
  amount = DecimalField(max_digits=10, decimal_places=2)  # > 0 enforced
  method = CharField(choices=METHODS)
  reference = CharField(blank)        # bKash TrxID etc.
  note = TextField(blank)
  recorded_by = FK(User, PROTECT)     # staff member; set automatically in admin
  created_at = DateTimeField(auto_now_add=True)
```
Records are append-only: no admin edit/delete permission. A mistake is corrected
by an offsetting record with a note. This gives you a clean money audit trail
from day one.

### 5.2 API exposure
Read-only, nested in rental detail for participants:
`GET /api/rentals/{id}/` includes `payment_records: [...]` and a computed
`settlement` block: `{rent_paid, deposit_held, deposit_returned, owner_paid}`.
No write endpoints — creation happens only in Django admin.

### 5.3 Completion guard
`in_progress → completed` is blocked unless:
- a `rent_collected` record ≥ base_cost exists, AND
- if security_deposit > 0: deposit_collected exists AND
  (deposit_returned + deposit_withheld) records sum to deposit_collected amount, AND
- an `owner_payout` record exists.
Staff see exactly which item is missing in the admin error message. This is the
operational checklist enforced in code.

---

## 6. DJANGO ADMIN = OPERATIONS CONSOLE AT LAUNCH

### users (exists — keep)
Approve/reject verification, make partner, NID image preview.

### listings.ProductAdmin
list: title, owner phone, status, category, created. Filters: status, category.
Actions: suspend / re-activate (with note → status_history-style log field).
Inline: images (readonly thumbnails), pricing tiers.

### rentals.RentalAdmin (the operations heart)
- list: id (short), product, renter phone, owner phone, dates, status (colored),
  settlement summary. Filters: status, dates.
- readonly: all pricing snapshot fields, status, status_history (pretty-printed).
- Inline: PaymentRecord (add-only; `recorded_by` auto-set to request.user),
  RentalPhoto (readonly previews).
- Admin actions implemented via `Rental.transition(..., actor=staff)`:
  - "Mark item handed to renter (in_progress)"
  - "Mark rental completed (settled)" — surfaces §5.3 guard errors clearly
  - "Cancel rental (staff)"
- NEVER expose raw `status` as an editable field — transitions only.

Daily ops flow: open Rentals filtered by `accepted` → record deposit/rent as
collected → mark in_progress at handover → on return, record deposit_returned +
owner_payout → mark completed.

---

## 7. REVIEWS APP (minimal, real)

### 7.1 Model
```python
class Review(models.Model):
  id = UUIDField(pk)
  rental = FK(Rental, CASCADE, related_name='reviews')
  reviewer = FK(User, CASCADE, related_name='reviews_written')
  reviewee = FK(User, CASCADE, related_name='reviews_received')
  product = FK(Product, CASCADE, related_name='reviews')   # set for both directions
  direction = CharField([('renter_to_owner', ...), ('owner_to_renter', ...)])
  rating = PositiveSmallIntegerField(1..5)
  comment = TextField(max_length=1000, blank)
  created_at
  class Meta:
    constraints = [UniqueConstraint(fields=['rental', 'reviewer'], name='one_review_per_party')]
```

### 7.2 Rules
- Create allowed only if: rental.status == 'completed' AND reviewer is the
  rental's renter or owner AND within 30 days of completion.
- Direction + reviewee derived server-side from who the reviewer is. Client
  sends only `{rental_id, rating, comment}`.
- No edits, no deletes by users (admin can delete abusive content).
- On save (renter_to_owner only): recompute `product.average_rating` as the avg
  of renter→owner reviews for that product. On any save: recompute
  `reviewee.average_rating`. Both via aggregate query, atomic.

### 7.3 Endpoints
```
POST /api/reviews/                          create (rules above)
GET  /api/reviews/?product={id}             public list, renter_to_owner only, paginated
GET  /api/reviews/?user={id}                public list of reviews received
GET  /api/reviews/pending/                  my completed rentals awaiting my review
```

---

## 8. FRONTEND REWIRING (live repo — UI design unchanged)

### 8.1 Auth plumbing swap
- Adopt the rebuild's `src/lib/axios.ts` (in-memory access token, httpOnly refresh
  cookie, 401 refresh queue) as the ONLY axios instance. Delete
  `api.service.ts`'s instance, `auth.service.ts`'s two instances, and the
  camelCase↔snake_case transform interceptor. Components consume snake_case
  fields via updated TS types (mechanical rename; no visual change).
- Adopt the rebuild's `AuthContext` (silent-refresh session restore).
- Replace pages behind the same routes/design: Login → phone+password;
  Register → 3-step signup (phone → OTP → details); ForgotPassword → OTP flow;
  CompleteProfile → step1 (personal) + step2 (documents). The rebuild's `src/pages/auth/*`
  already match the green design system — port them in.
- Remove `AdminAuthContext`, `localStorage` token helpers, `admin_token` logic.

### 8.2 config.ts rewrite
Single `VITE_API_URL` (no hardcoded prod fallback), endpoint map matching §3–§7,
`isDevelopment` from `import.meta.env.DEV`. Envelope-aware response helpers:
every service unwraps `{success, message, data}` once, in one place.

### 8.3 Listings
- `getActiveProducts` relies on the backend's active-only default (remove the
  comment-driven "show all" behavior).
- PricingStep: keep 20% fee preview (correct). RequestRental's
  `PriceCalculationStep`: DELETE the 8% renter-side fee math; show the price
  snapshot returned by the backend create/preview response. Renter total =
  base_cost (+ deposit shown separately as refundable).

### 8.4 Rentals UI
- `RentalStatus` constants: `PENDING|ACCEPTED|IN_PROGRESS|COMPLETED|REJECTED|CANCELLED`
  matching backend strings exactly. (Replace `APPROVED` with `ACCEPTED`; add
  `IN_PROGRESS` — colors already exist per the README.)
- Tab filters: Active = accepted + in_progress; Pending = pending;
  History = completed + rejected + cancelled.
- RentalDetailModal action buttons: keep renter Cancel (pending/accepted,
  pre-start) and owner Accept/Reject (pending). REMOVE renter "Complete Rental"
  and owner "Confirm Return" buttons — those transitions are Bhara-staff-only and
  the buttons never worked. The timeline now renders from real `status_history`.
  Settlement block renders from `settlement` data (§5.2).
- Review form appears on completed rentals and posts to `/api/reviews/`.

### 8.5 Reviews
Remove the hardcoded default reviews in `itemDetail/ReviewsSection.tsx` props;
fetch `/api/reviews/?product=`. Empty state ("Be the first to review") already
exists and is kept.

### 8.6 Removals/hiding (not redesign — removing dead controls)
- `/admin/*` routes removed from App.tsx (dashboard code stays in repo, parked).
- Favorites tab in ProfileSidebar hidden.
- Endpoints with no backend (`submit_for_review`, `update_rating`,
  `increment_views`) removed from config + services.

---

## 9. AUTH HARDENING (changes to existing `users/` rebuild)

1. **OTP verify brute force:** attempt counter `otp_attempts:{purpose}:{phone}`;
   ≥5 wrong attempts → delete OTP key, force re-request. Add AnonRateThrottle
   (10/min) on OTPVerifyView. Compare hashes with `hmac.compare_digest`.
2. **Per-phone SMS caps** (IP throttling alone fails behind BD carrier NAT):
   cache-counter limits of 1/min and 5/day per phone number on OTP request,
   alongside the existing 3/min/IP throttle.
3. **`cache.ttl()` crash in dev:** LocMemCache lacks `.ttl`. Guard:
   `ttl = cache.ttl(k) if hasattr(cache, 'ttl') else settings.LOGIN_LOCKOUT_SECONDS`.
4. **Real refresh rotation:** in TokenRefreshView, after validating the incoming
   refresh token, blacklist it and issue a fresh `RefreshToken.for_user(user)`;
   set the NEW token in the cookie. (Current code re-sets the same token —
   rotation settings were silently inert.)
5. **Single-use ephemeral tokens:** add `jti` (uuid4) to the payload; on
   successful signup-complete / password-reset-complete, store
   `used_jti:{jti}` in cache for 10 min and reject repeats.
6. **SignupCompleteView / PasswordResetCompleteView:**
   `authentication_classes = []` (SessionAuthentication's CSRF check can 403
   browsers that carry a Django admin session cookie).
7. **SMS via POST**, not GET (OTP in query strings leaks into proxy logs).
8. Production sanity: DEBUG=False enforced, ALLOWED_HOSTS explicit,
   `CORS_ALLOWED_ORIGINS=['https://bhara.xyz']`, cookies
   Secure + SameSite=Strict (bhara.xyz ↔ api.bhara.xyz are same-site: OK).

---

## 10. BUILD ORDER

| Phase | Scope | Done when |
|-------|-------|-----------|
| 0 | Auth hardening (§9) + `core/responses.py` extraction | Existing test suite green + new tests for items 1–5 |
| 1 | `listings` app: models, viewset, filters, tests | Create→browse→detail works via curl; drafts invisible publicly |
| 2 | `rentals` app: model, state machine, endpoints, PaymentRecord, admin | Full lifecycle drivable: API for request/accept, admin for in_progress/payments/completed; double-booking test passes |
| 3 | `reviews` app | Review postable on completed rental only; ratings aggregate |
| 4 | Frontend rewiring (§8) | Full user journey in browser against new backend |
| 5 | Cutover: fresh Postgres, deploy, smoke-test script, archive old repos | bhara.xyz on new stack |

Each phase lands with its tests (pytest backend; the state machine and §5.3 guard
get exhaustive transition-matrix tests).

---

## 11. OUT OF SCOPE FOR LAUNCH
Favorites, payment gateway (bKash/SSLCommerz), notifications (SMS/in-app),
React admin dashboard API, in-app messaging, delivery-leg tracking statuses
(item_at_bhara etc. — revisit when volume justifies; status_history notes cover
it for now), listing pre-approval queue (admin suspend is the moderation tool).

*End of specification.*
