---
phase: 04-dashboard-source-constructor
fixed_at: 2026-06-18T00:00:00Z
review_path: .planning/phases/04-dashboard-source-constructor/04-REVIEW.md
iteration: 1
findings_in_scope: 13
fixed: 13
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-06-18
**Source review:** `.planning/phases/04-dashboard-source-constructor/04-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 13 (5 Critical + 8 Warning)
- Fixed: 13
- Skipped: 0

**Verification:** `backend pytest -q` → 541 passed, 65 skipped, 0 failed; `dashboard tsc --noEmit` → exit 0.

---

## Fixed Issues

### CR-01: Division-by-zero when market_avg is 0 in price_analysis_service

**Files modified:** `backend/app/services/price_analysis_service.py`
**Commit:** a19ac31
**Applied fix:** Added a guard `if market_avg == 0: return None` with a debug log before the division, preventing `ZeroDivisionError` / `decimal.InvalidOperation` when `price_points` records a zero-price average for a product.

---

### CR-02: db.rollback() in alert_service invalidates the caller's session

**Files modified:** `backend/app/services/alert_service.py`, `backend/tests/test_alert_service.py`
**Commit:** ef446bf
**Applied fix:** Replaced the bare `db.add(alert); db.flush()` + `except IntegrityError: db.rollback()` pattern with `with db.begin_nested(): db.add(alert); db.flush()`. The SAVEPOINT ensures only the duplicate alert insert is rolled back, never the caller's transaction. Updated `test_dedupe_on_integrity_error` to assert `begin_nested` is called and `rollback` is NOT called on the shared session.

---

### CR-03: DELETE /alert-rules endpoint does not exist

**Files modified:** `backend/app/api/alert_rules.py`, `backend/tests/test_rbac_dashboard.py`
**Commit:** 21507f5
**Applied fix:** Added `DELETE /{rule_id}` endpoint with `require_admin` guard, 404 for missing rules, 204 on success. Added `TestAlertRulesDeleteAdminOnly` test class covering: non-admin roles get 403, admin gets 404 for missing rule, admin gets 204 for existing rule.

---

### CR-04: PriceChart sends unknown query parameter product_slug

**Files modified:** `dashboard/components/prices/PriceChart.tsx`
**Commit:** 3f12590
**Applied fix:** Added `SLUG_TO_ID` mapping (pp_raffia=1 through abs=8) and replaced `product_slug: product` in the URL params with `product_id: String(productId)`. The mapping is omitted from the params if the slug is unknown to avoid sending a null/garbage value.

---

### CR-05: TestResultBanner uses useState as useEffect

**Files modified:** `dashboard/components/sources/SourcesList.tsx`
**Commit:** 00e3694
**Applied fix:** Replaced `useState(() => { apiFetch(...) })` with a proper `useEffect` with a `cancelled` flag. The flag is set to `true` in the cleanup return, preventing state updates on unmounted components and avoiding double-fire in React Strict Mode.

---

### WR-01: list_requests has no filter support

**Files modified:** `backend/app/api/dashboard_requests.py`
**Commit:** b9d039c
**Applied fix:** Added `status_filter`, `urgency`, and `product_id` query parameters to `list_requests`. Filters are applied as ORM `.filter()` calls (same pattern as `export_requests`). Uses `alias="status"` for the status param to match the frontend's `?status=` query string key.

---

### WR-02: alert_rules list endpoint unbounded

**Files modified:** `backend/app/api/alert_rules.py`
**Commit:** fa9ad0f (+ 828505f for missing Query import)
**Applied fix:** Added `limit: int = Query(default=100, le=500)` parameter to `list_alert_rules`. Added `.limit(limit)` to the query. Also added `Query` to the `fastapi` import (was missing).

---

### WR-03: XML external entity (XXE) exposure in RSS adapter

**Files modified:** `backend/app/ingest/rss/adapter.py`, `backend/pyproject.toml`
**Commit:** 3662545
**Applied fix:** Added a 5 MB body size cap before XML parsing. Added a try/import for `defusedxml.ElementTree` with a fallback to stdlib ET when not installed. Added `defusedxml>=0.7.1` to `pyproject.toml` production dependencies. The size cap alone mitigates billion-laughs attacks even without defusedxml.

---

### WR-04: send_delivery does not send parse_mode="HTML"

**Files modified:** `backend/app/tasks/notify.py`
**Commit:** 306c876
**Applied fix:** Added `import html` at module level. HTML-escaped `alert.title` and `alert.body` before embedding them in the `<b>…</b>` template. Added `parse_mode="HTML"` to the `bot.send_message(...)` call so Telegram renders the bold tags instead of displaying them as literal text.

---

### WR-05: Keyset pagination cursor reset missing on filter change

**Files modified:** `dashboard/components/feed/LiveFeedTable.tsx`
**Commit:** 64ed659
**Applied fix:** Added `useRef` to track previous filter values and a `useEffect` that calls `setCursorStack([])` whenever `period`, `kind`, `source`, or `urgency` changes. Also added `useEffect` and `useRef` to the import.

---

### WR-06: RequestActions.tsx AlertDialog renders without controlled open prop

**Files modified:** `dashboard/components/requests/RequestActions.tsx`
**Commit:** 6b55719
**Applied fix:** Added `showCancelDialog` state variable. `handleStatusChange` now sets `setShowCancelDialog(true)` when `newStatus === "cancelled"`. The `<AlertDialog>` uses `open={showCancelDialog}` and `onOpenChange` to revert `selectedStatus` on Escape/outside-click. The select `onChange` now routes through `handleStatusChange` for all values (simplified).

---

### WR-07: useAuth isTokenExpired check skipped when payload.exp is absent

**Files modified:** `dashboard/hooks/useAuth.ts`
**Commit:** cf4a382
**Applied fix:** Changed `if (!payload.exp) return false` to `if (!payload.exp) return true`. A token without an `exp` claim is now treated as expired (fail-closed), preventing a perpetually "authenticated" UI state when debug tokens without expiry are issued.

---

### WR-08: seed_demo.py inserts DEMO source without config column

**Files modified:** `backend/app/seed/seed_demo.py`
**Commit:** 659f863
**Applied fix:** Added `config` to the INSERT column list for both the `html_table` and `rss` demo sources. The `html_table` source gets `{"url": "...", "table_selector": "table"}` and the RSS source gets `{"url": "...", "currency_default": "USD"}` as their JSONB config values.

---

## Skipped Issues

None — all 13 in-scope findings were fixed.

---

## Deferred (Info-severity, out of scope per instructions)

- **IN-01** (`dashboard_requests.py:241`): Redundant row-count check in CSV export generator — dead code but harmless.
- **IN-02** (`RequestsTable.tsx:208-218`): "Region" column always displays "—" — display inconsistency, not a bug.
- **IN-03** (`notify.py:344`): `asyncio.run()` inside Celery sync tasks — fragile under gevent workers, low risk in current config.
- **IN-04** (`RuleBuilder.tsx:464`): `parseInt` silently produces NaN for non-numeric chat IDs — UX improvement needed.
- **IN-05** (`useAuth.ts:49-53`): Token state initialized from module-level `getToken` — minor SSR fragility, low risk with `"use client"` directive.

---

_Fixed: 2026-06-18_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
