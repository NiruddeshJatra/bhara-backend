# Performance Audit — bhara-backend

**Date:** 2026-06-11
**Scope:** Full Django codebase — models, views, serializers, filters, services, settings, Celery, deployment config.
**Method:** Static analysis of every query path, serializer, and endpoint. No load testing performed (no production traffic data available).

**Context that shapes this audit:** This is a pre-launch marketplace. The spec (§3.3) explicitly says "NO response caching anywhere — Postgres + indexes carry launch scale." Existing code is already disciplined: `select_related`/`prefetch_related` are used on the main querysets, `F()` expressions avoid read-modify-write races, image compression happens outside transactions, and SMS is async via Celery. The findings below are the gaps, ranked by ROI.

---

## Summary Table

| # | Finding | Severity | Effort | Risk | Priority |
|---|---------|----------|--------|------|----------|
| 1 | No DB connection pooling in production (`CONN_MAX_AGE` unset) | High | Trivial | Low | **P0** |
| 2 | Unbounded list endpoints (rentals ×2, reviews ×2) — no pagination | High | Low | Low | **P0** |
| 3 | `get_blocked_dates()` loads *all* historical rentals, expands every date into a Python set | High | Low | Low | **P0** |
| 4 | Missing composite indexes on hot query paths | Medium-High | Low | Low | **P0** |
| 5 | Price filters produce duplicate rows (missing `.distinct()`) — payload bloat + correctness | Medium | Trivial | Low | **P0** |
| 6 | Rental list endpoints prefetch `payment_records` + `photos` that the list serializer never reads | Medium | Trivial | Low | **P1** |
| 7 | Full-row `save()` in `Rental._apply()` and auto-reject loop | Low-Medium | Low | Low | **P1** |
| 8 | `retrieve()` does an extra `refresh_from_db` query for `views_count` | Low | Trivial | Low | **P1** |
| 9 | Auto-reject loop in `_guard_accept` saves one row at a time | Low | Low | Medium | **P2** |
| 10 | Synchronous image compression in request thread (up to 8 images) | Medium | High | Medium | **P2** — document, don't fix now |
| 11 | `views_count` write on every anonymous product view | Low (at launch) | — | — | **P2** — document only |
| 12 | `icontains` search can't use B-tree indexes | Low (at launch) | Medium | Medium | **P2** — document only |
| 13 | Password-reset blacklists outstanding tokens one query per token | Negligible | — | — | Not worth fixing |
| 14 | No HTTP compression for JSON payloads | Low | — | — | Handle at reverse proxy, not Django |

---

## Detailed Findings

### 1. No database connection pooling in production — P0

**Where:** `core/settings/production.py` — `DATABASES` has no `CONN_MAX_AGE`.

**Root cause:** Django's default is `CONN_MAX_AGE = 0`: every request opens a new Postgres connection (TCP + TLS + auth handshake, ~5–50 ms) and closes it at the end.

**Impact:** Adds fixed latency to *every single request* and burns Postgres connection slots under concurrency. This is the single cheapest win in the codebase.

**Fix:** `CONN_MAX_AGE = 60` + `CONN_HEALTH_CHECKS = True` (Django ≥ 4.1 pings before reuse, so stale connections don't 500).

**Expected gain:** ~5–50 ms shaved off every request's response time; lower Postgres load; zero memory cost.

**Risk:** Low. Health checks eliminate the classic stale-connection failure mode. Worker count × persistent connections must stay under Postgres `max_connections` — fine at launch scale.

---

### 2. Unbounded list endpoints — P0

**Where:**
- `rentals/views.py` — `my_rentals`, `my_listings_rentals` (lines 71–79): serialize the *entire* queryset.
- `reviews/views.py` — `list` (line 50) and `pending` (line 67): same.

**Root cause:** These endpoints return `Serializer(qs, many=True).data` with no pagination, unlike `ProductViewSet` which paginates correctly.

**Impact:** Response time, memory, and payload size all grow linearly and without bound as a user accumulates rentals/reviews. A power user (or the public `?user=<id>` reviews endpoint for a popular owner) eventually returns megabytes of JSON in one response. The public reviews endpoint is the worst case: unauthenticated, unbounded, and hits three `select_related` joins per row.

**Fix:** Apply the existing `StandardResultsSetPagination` (page_size 20, max 80) to all four endpoints. Move it to a shared location (`core/`) so rentals/reviews don't import from listings.

**Expected gain:** Bounded response time and payload (~20 rows max per request instead of unbounded). Protects the DB and the JSON serializer from pathological users.

**Risk:** Low-Medium — **this changes the response shape** for these four endpoints (results wrapped in `{count, next, previous, results}`). The frontend must handle pagination. This is the only finding where the fix is technically a contract change; flagged for your approval decision.

---

### 3. `get_blocked_dates()` over-fetches and over-computes — P0

**Where:** `listings/services.py:33-40`, consumed by `rentals/serializers.py:137-145`.

**Root cause:** Two compounding issues:
1. It loads **every** accepted/in_progress rental for the product — including ones whose date ranges are nowhere near the requested window. After a product has been rented 50 times, all 50 rows are fetched and every single day of every rental is expanded into a Python `set`.
2. The caller then walks the requested range day-by-day in Python checking set membership.

A 6-month rental expands to ~180 `date` objects. A product with years of history allocates thousands of objects per availability check — on the rental-create hot path.

**Fix:** Accept an optional `(start, end)` window in `get_blocked_dates()` and push the overlap filter into SQL (`start_date__lte=end, end_date__gte=start` for rentals; equivalent date/range conditions for `UnavailablePeriod`). Only dates inside the requested window get expanded. The function signature stays backward-compatible (window defaults to `None` = current behavior) so the filter use-case is untouched.

**Expected gain:** Query returns only relevant rows (typically 0–2 instead of all history); memory allocation drops from O(total rental-days ever) to O(requested window); rental creation latency stops degrading as product history grows.

**Risk:** Low. Pure narrowing of fetched data; existing 54 rental tests + 19 listings tests verify behavior.

---

### 4. Missing composite indexes — P0

**Where:** `rentals/models.py`, `listings/models.py`, `reviews/models.py`.

Django auto-indexes every FK and the explicitly marked `db_index=True` fields (`Rental.status`, `Product.status/category/location`). But the hot queries filter on **combinations**, and single-column indexes force Postgres to intersect or scan:

| Query | Where it runs | Current index coverage |
|---|---|---|
| `rentals WHERE product_id=? AND status IN (...) AND start_date<=? AND end_date>=?` | Double-booking guard (`_guard_accept`), availability filter, `get_blocked_dates`, `has_blocking_rentals` | `product_id` only |
| `rentals WHERE product_id=? AND renter_id=? AND status IN ('pending','accepted')` | Duplicate-request guard on every rental create | `product_id` or `renter_id` alone |
| `products WHERE status='active' ORDER BY created_at DESC` | Main listing page, every visit | separate `status` index, no covering order |
| `reviews WHERE product_id=? AND direction='renter_to_owner'` | Public review list + rating recompute on every review save | `product_id` only |

**Fix:** Add `Meta.indexes`:
- `Rental`: `(product, status, start_date, end_date)` — covers overlap guard, blocked-dates, and blocking-rentals checks with a single index.
- `Rental`: `(renter, status)` and `(owner, status)` — duplicate-request guard, my-rentals filtering, pending reviews.
- `Product`: `(status, -created_at)` — main listing page scan+sort in one index.
- `Review`: `(product, direction)` — public list + aggregation.

One migration per app, additive only.

**Expected gain:** Index-only or index-range scans instead of broader scans on the most-executed queries. Matters most for the double-booking guard since it runs *inside* a `select_for_update` lock — faster guard = shorter lock hold = better accept throughput.

**Risk:** Low. Additive migrations; small write-amplification cost per index (negligible at these write volumes).

---

### 5. Price/duration filters return duplicate products — P0 (correctness + performance)

**Where:** `listings/filters.py:13-17` — `min_price`, `max_price`, `duration_unit` are declared filters that join through `pricing_tiers` but **don't apply `.distinct()`** (unlike `filter_search` and `filter_availability`, which do).

**Root cause:** A product with 3 pricing tiers matching `min_price=100` appears 3 times in the joined result set.

**Impact:** Duplicate rows inflate payload size, waste serialization work, break pagination counts, and look like a bug to users. Compounding: pagination `COUNT(*)` counts the duplicates too.

**Fix:** Apply `.distinct()` once in the list path when these filters are active (or convert the filters to method filters with distinct). Note `distinct=True` is supported directly on `NumberFilter`/`CharFilter`.

**Expected gain:** Correct results, smaller payloads, accurate page counts.

**Risk:** Low. `DISTINCT` on the UUID PK is cheap; the ordering columns are already in the select list.

---

### 6. Rental list endpoints prefetch unused relations — P1

**Where:** `rentals/views.py:29-39` — `get_queryset()` always prefetches `payment_records` and `photos`, but `RentalListSerializer` (used by `my_rentals` and `my_listings_rentals`) reads neither.

**Impact:** Two extra queries per list request, each fetching *all* payment records and photos for *every* rental in the list — rows that are immediately thrown away. For an owner with 100 rentals this loads potentially hundreds of payment rows for nothing.

**Fix:** Only add the `payment_records`/`photos` prefetch for `retrieve` (the only action whose serializer uses them). List actions keep `select_related` only.

**Expected gain:** 2 fewer queries and substantially less row transfer + memory per list call.

**Risk:** Low. Detail path unchanged.

---

### 7. Full-row writes on status transitions — P1

**Where:** `rentals/models.py:138-147` (`_apply`) and `:179-193` (auto-reject loop) call `self.save()` with no `update_fields`.

**Impact:** Every transition rewrites all ~20 columns including the pricing snapshot and `notes` text. Inside the accept path this happens while holding the product row lock. Also a subtle safety issue: a stale in-memory field would silently overwrite the DB value.

**Fix:** `self.save(update_fields=['status', 'status_history', 'updated_at'])` in both places.

**Expected gain:** Smaller WAL writes, shorter lock hold on accept, and a correctness hardening for free.

**Risk:** Low. `updated_at` (`auto_now`) must be included in `update_fields` to keep being set — included.

---

### 8. Extra query in product retrieve — P1

**Where:** `listings/views.py:62-63` — after the `F()`-based increment, `refresh_from_db(fields=['views_count'])` issues a second query just to display the new count.

**Fix:** Increment the in-memory value (`product.views_count += 1`) for display; the DB value is already correct from the `update()`. Saves one query per anonymous product view — the highest-traffic endpoint.

**Risk:** Low. Displayed count could be off by concurrent views either way; `refresh_from_db` had the same race.

---

### 9. Auto-reject saves one row at a time — P2

**Where:** `rentals/models.py:179-193`.

**Impact:** N queries for N overlapping pending rentals, inside the locked accept transaction. N is almost always 0–3, so impact is small — but it does extend lock hold time.

**Fix option:** Collect and `bulk_update(['status', 'status_history', 'updated_at'])`. Note: `bulk_update` skips `auto_now`, so `updated_at` must be set manually — this is why it's P2 (medium risk of subtle behavior drift) rather than P1.

---

### 10. Synchronous image compression — P2, document only

**Where:** `listings/serializers.py:143-150` (up to 8 images per listing create), `users/views.py` profile views.

**Impact:** Pillow decode + LANCZOS resize + JPEG encode for 8 phone photos can take 2–5 s of CPU in the request worker. This blocks the worker and caps create-listing throughput.

**Why not fixing now:** The spec deliberately places compression in `validate_images()` outside the transaction. Moving it to Celery means accepting originals first, compressing async, and handling failure states — a meaningful design change with API-visible effects (listing appears before images are final). Wrong trade pre-launch. **Recommendation:** revisit when create-listing volume justifies it; until then, ensure enough gunicorn workers/threads that one slow create doesn't starve traffic.

### 11. `views_count` hot-row writes — P2, document only

Every anonymous product view issues an `UPDATE`. At launch volume this is nothing. At scale, a popular product becomes a hot row. Future fix: buffer counts in Redis, flush periodically. Not now — premature.

### 12. `icontains` search — P2, document only

`title__icontains` / `location__icontains` can't use B-tree indexes; they're sequential scans. Fine for thousands of products. When the catalog grows: Postgres `pg_trgm` GIN indexes (additive migration). Not applicable to SQLite dev. Not now — premature.

### 13–14. Not worth changing

- **Token blacklist loop** (`users/views.py:352-356`): runs on password reset only — rare, small N.
- **HTTP compression:** add gzip/brotli at nginx/reverse-proxy level, not `GZipMiddleware` (BREACH considerations with tokens in response bodies; proxy-level compression with sensible config is the standard answer).

---

## What was checked and found healthy

- `ProductViewSet.get_queryset` — correct `select_related('owner')` + prefetch of all serializer-consumed relations. No N+1.
- `ReviewViewSet.list` — `select_related('reviewer', 'reviewee', 'product')` matches serializer reads. No N+1.
- `Review._recompute_ratings` — single `aggregate(Avg)` + `update()`, atomic, no read-modify-write race.
- `views_count` / `rental_count` — `F()` expressions, race-free.
- Double-booking guard — `select_for_update` inside `transaction.atomic`, correct.
- OTP/SMS — async via Celery with retries; caps enforced via cache; no blocking I/O in request path.
- Image compression placement — outside DB transactions per spec.
- Settlement math — operates on prefetched rows, no extra queries.
- Pagination on products — present, with `max_page_size` cap.
- No response caching — intentional per spec §3.3; **not** flagged as a gap.

## Post-audit discovery (found during implementation)

**Test suite runs against the real dev database.** `conftest.py` overrides the `django_db_setup` fixture with `pass`, which disables pytest-django's isolated test-database creation — all 170+ tests execute directly against `db.sqlite3`. Consequences: (a) the suite takes ~10 minutes because every write hits a synchronous file-backed SQLite DB; (b) two concurrent test runs corrupt each other (observed: 12 spurious auth-test failures when runs overlapped); (c) test data pollutes the dev DB. Fix is to delete the no-op fixture override and let pytest-django manage an isolated (in-memory for SQLite) test DB — likely cuts suite time dramatically. **Not changed in this pass** — test infrastructure change, flagged for separate approval.

## Measurement caveat

All impact estimates are from static analysis (query counting, complexity reasoning), not load tests. The verification plan in `PERFORMANCE_PLAN.md` uses `django.test.utils.CaptureQueriesContext`-style assertions in tests to lock in query counts where it matters.
