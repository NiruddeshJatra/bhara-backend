# Performance Plan — bhara-backend

Companion to `PERFORMANCE_AUDIT.md`. Ordered by ROI: high impact / low risk first. Each phase is independently shippable and verified by the existing 169-test suite plus targeted new tests.

**STATUS: All phases implemented and verified 2026-06-11** — 177 tests green (169 pre-existing + 8 new), `makemigrations --check` clean. Phase 2 response-shape change approved by user.

---

## Phase 1 — High impact, low risk, zero contract change

### 1.1 Connection pooling (Audit #1)
- **Change:** `core/settings/production.py` — add `'CONN_MAX_AGE': 60, 'CONN_HEALTH_CHECKS': True` to `DATABASES['default']`.
- **Verify:** settings import cleanly; full test suite green (dev settings unaffected).
- **Expected:** ~5–50 ms off every production request; fewer Postgres handshakes.

### 1.2 Window-aware `get_blocked_dates()` (Audit #3)
- **Change:** `listings/services.py` — add optional `start`/`end` params; when provided, filter `UnavailablePeriod` and `Rental` queries to rows overlapping the window before date-expansion. `rentals/serializers.py` passes the requested rental window.
- **Verify:** new test — product with a rental far outside the requested window: assert it is not fetched (query inspection) and availability result unchanged. Existing rental-create and availability tests stay green.
- **Expected:** rental-create validation cost stops growing with product history; memory O(window) not O(history).

### 1.3 Composite indexes (Audit #4)
- **Change:** `Meta.indexes` additions + one migration per app:
  - `Rental`: `['product', 'status', 'start_date', 'end_date']`, `['renter', 'status']`, `['owner', 'status']`
  - `Product`: `['status', '-created_at']`
  - `Review`: `['product', 'direction']`
- **Verify:** `makemigrations --check` clean afterward; suite green.
- **Expected:** range scans on double-booking guard, listing page, duplicate-request guard, review lists.

### 1.4 Distinct on price/duration filters (Audit #5)
- **Change:** `listings/filters.py` — `distinct=True` on `min_price`, `max_price`, `duration_unit` filters.
- **Verify:** new test — product with 2 tiers both matching `min_price`: assert it appears once.
- **Expected:** correct results, accurate pagination counts, smaller payloads.

### 1.5 Trim rental list prefetches (Audit #6)
- **Change:** `rentals/views.py get_queryset()` — keep `select_related`; add `prefetch_related('payment_records', 'photos')` only when `self.action == 'retrieve'`.
- **Verify:** new test asserting query count on `my-rentals` drops by 2; detail tests stay green.
- **Expected:** 2 fewer queries + far less row transfer per list call.

### 1.6 `update_fields` on transitions (Audit #7)
- **Change:** `rentals/models.py` — `_apply()` and auto-reject loop use `save(update_fields=['status', 'status_history', 'updated_at'])`.
- **Verify:** full transition-matrix tests (54) stay green.
- **Expected:** smaller writes, shorter lock hold on accept.

### 1.7 Drop `refresh_from_db` in retrieve (Audit #8)
- **Change:** `listings/views.py retrieve()` — replace with in-memory `product.views_count += 1`.
- **Verify:** existing views_count tests stay green.
- **Expected:** 1 query saved on highest-traffic endpoint.

## Phase 2 — High impact, needs a decision (response shape changes)

### 2.1 Paginate rentals + reviews list endpoints (Audit #2)
- **Change:** shared pagination class (moved/re-exported via `core/`), applied to `my-rentals`, `my-listings-rentals`, `GET /api/reviews/`, `GET /api/reviews/pending/`.
- **⚠ Contract change:** these four endpoints currently return a bare array in `data`; they would return `{count, next, previous, results}` like listings already does. Frontend must adapt.
- **Decision needed:** approve shape change, or defer? (Alternative: cap with `[:N]` slice — bounds the damage without shape change, but silently truncates. Pagination is the right fix.)
- **Verify:** updated tests for the four endpoints; rest of suite green.
- **Expected:** bounded latency/payload/memory on all list endpoints; closes the unauthenticated unbounded-response hole on public reviews.

## Phase 3 — Marginal, only if Phases 1–2 land clean

### 3.1 Bulk auto-reject (Audit #9)
- `bulk_update` for overlapping pending rentals; manual `updated_at` (bulk_update skips `auto_now`). Small win, slight behavior-drift risk — last for a reason.

## Explicitly deferred (documented in audit, no action)

- Async image compression (#10) — design change, wrong trade pre-launch.
- Redis-buffered `views_count` (#11) — premature.
- `pg_trgm` search indexes (#12) — premature; catalog too small.
- Response caching — prohibited by spec §3.3.
- gzip — reverse-proxy concern, not Django.

## Verification protocol (every phase)

1. `pytest` — full 169-test suite green before and after.
2. New assertions use `django.test.utils.CaptureQueriesContext` to pin query counts where the change claims to reduce them.
3. `python manage.py makemigrations --check` after model changes.
4. No endpoint response shape changes outside the approved Phase 2 scope.
5. One commit per phase, conventional commit messages.

## Estimated total effort

Phase 1: ~1–2 hours including tests. Phase 2: ~1 hour + frontend coordination. Phase 3: ~30 min.
