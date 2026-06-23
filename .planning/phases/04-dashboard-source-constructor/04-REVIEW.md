---
phase: 04-dashboard-source-constructor
reviewed: 2026-06-18T00:00:00Z
depth: standard
files_reviewed: 52
files_reviewed_list:
  - backend/app/api/admin_users.py
  - backend/app/api/alert_rules.py
  - backend/app/api/dashboard_requests.py
  - backend/app/api/feed.py
  - backend/app/api/prices.py
  - backend/app/api/sources.py
  - backend/app/api/deps.py
  - backend/app/core/feed_bus.py
  - backend/app/ingest/html_table/adapter.py
  - backend/app/ingest/rss/adapter.py
  - backend/app/ingest/telegram_channel/adapter.py
  - backend/app/ingest/llm_page/adapter.py
  - backend/app/main.py
  - backend/app/schemas/dashboard.py
  - backend/app/services/alert_service.py
  - backend/app/services/price_analysis_service.py
  - backend/app/services/request_service.py
  - backend/app/tasks/notify.py
  - backend/app/seed/seed_demo.py
  - dashboard/app/(dashboard)/layout.tsx
  - dashboard/app/(dashboard)/page.tsx
  - dashboard/app/(dashboard)/requests/page.tsx
  - dashboard/app/(dashboard)/prices/page.tsx
  - dashboard/app/(dashboard)/sources/page.tsx
  - dashboard/app/(dashboard)/alerts/page.tsx
  - dashboard/app/(dashboard)/admin/users/page.tsx
  - dashboard/app/login/page.tsx
  - dashboard/components/alerts/AlertFeed.tsx
  - dashboard/components/alerts/RuleBuilder.tsx
  - dashboard/components/feed/LiveFeedTable.tsx
  - dashboard/components/feed/FeedFilters.tsx
  - dashboard/components/feed/AiMarketSignalsPanel.tsx
  - dashboard/components/prices/PriceChart.tsx
  - dashboard/components/requests/AiAnalysisBlock.tsx
  - dashboard/components/requests/RequestActions.tsx
  - dashboard/components/requests/RequestDetailPanel.tsx
  - dashboard/components/requests/RequestsFilterBar.tsx
  - dashboard/components/requests/RequestsTable.tsx
  - dashboard/components/requests/ExportCsvButton.tsx
  - dashboard/components/sources/AddSourceWizard.tsx
  - dashboard/components/sources/JsonSchemaForm.tsx
  - dashboard/components/sources/SourcesList.tsx
  - dashboard/components/layout/AppShell.tsx
  - dashboard/components/layout/Sidebar.tsx
  - dashboard/components/shared/KpiCard.tsx
  - dashboard/components/shared/StatusChip.tsx
  - dashboard/components/shared/UrgencyChip.tsx
  - dashboard/components/shared/KindChip.tsx
  - dashboard/hooks/useAuth.ts
  - dashboard/hooks/useSSE.ts
  - dashboard/lib/api.ts
  - dashboard/lib/queryClient.ts
  - dashboard/lib/tz.ts
findings:
  critical: 5
  warning: 8
  info: 5
  total: 18
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-06-18
**Depth:** standard
**Files Reviewed:** 52
**Status:** issues_found

## Summary

The implementation covers the full Phase 4 scope: live feed (SSE + keyset pagination), purchase requests detail panel, sources wizard, alert rules CRUD, price series endpoint, and all supporting dashboard components. The overall architecture is sound — SQL injection guards, status-machine enforcement, service-never-commits pattern, and the SSRF guard in adapters are all properly implemented.

However, five blockers were identified. Two are correctness/safety issues in the backend (a division-by-zero in `price_analysis_service`, and a broken `db.rollback()` that invalidates the entire session in `alert_service`). Two are missing API endpoints or mismatched field names that cause silent runtime failures (the `DELETE /alert-rules` endpoint does not exist, and the price series chart sends a non-existent `product_slug` parameter). One is a React perpetual render loop from incorrect `useState` usage in `SourcesList.tsx`.

---

## Critical Issues

### CR-01: Division-by-zero when market_avg is 0 in price_analysis_service

**File:** `backend/app/services/price_analysis_service.py:88`
**Issue:** `delta_pct = float((target_price - market_avg) / market_avg * 100)` will raise `ZeroDivisionError` if `market_avg` is exactly `0` (valid for a product that has a recorded zero-price). Python's `decimal.Decimal` raises `InvalidOperation` on `0 / 0` or `DivisionByZero`, which propagates as an unhandled exception from `compute_price_analysis` into `_build_request_detail`, crashing `GET /requests/{id}` with a 500 for any request whose product has a zero market average in `price_points`.
**Fix:**
```python
if market_avg == 0:
    logger.debug(
        "price_analysis_service.zero_market_avg",
        extra={"product_id": product_id},
    )
    return None

delta_pct = float((target_price - market_avg) / market_avg * 100)
```

---

### CR-02: db.rollback() in alert_service invalidates the caller's session

**File:** `backend/app/services/alert_service.py:241`
**Issue:** When an `IntegrityError` is caught on duplicate `dedupe_key`, the code calls `db.rollback()` on line 241. This service shares the SQLAlchemy session with its caller (the Celery task or router that passed `db` in). A `rollback()` on a shared session rolls back **everything in the caller's transaction** — not just the duplicate alert flush. Any entity created earlier in the same transaction (e.g., the triggering signal) will be silently lost. The service-never-commits axiom applies equally to rollbacks: only the session owner should call rollback. The correct fix is to use a savepoint.
**Fix:**
```python
try:
    db.flush()
except IntegrityError:
    db.rollback()  # WRONG — replace with savepoint
    ...
```
Replace with:
```python
from sqlalchemy.exc import IntegrityError  # already imported

# Use a nested savepoint so rollback only undoes the duplicate alert,
# not the caller's entire transaction.
try:
    with db.begin_nested():   # SAVEPOINT
        db.add(alert)
        db.flush()
except IntegrityError:
    logger.info(
        "alert_service.dedupe_skip",
        extra={"rule_id": rule.id, "entity_type": entity_type, "entity_id": entity_id},
    )
    continue
```
The `db.add(alert)` call must move inside `begin_nested()` so the object is not left in the session's pending state after the rollback.

---

### CR-03: DELETE /alert-rules endpoint does not exist — RuleBuilder silently errors

**File:** `dashboard/components/alerts/RuleBuilder.tsx:436`
**Issue:** The `deleteMutation` calls `apiFetch(\`/alert-rules/${id}\`, { method: "DELETE" })`. No `DELETE` route is registered in `backend/app/api/alert_rules.py`. The router only defines `GET`, `POST`, and `PATCH`. The mutation will always receive a 405 Method Not Allowed (or 404 if not handled), which `apiFetch` turns into an `ApiError`. The `onError` handler silently closes the dialog (`setDeleteId(null)`) without displaying an error to the user, so admins believe deletes succeed but the rule is never removed. This is both a broken UI feature and a misleading success state.
**Fix:** Either add the endpoint to the backend router:
```python
@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(require_admin),
) -> None:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    db.delete(rule)
    db.commit()
```
Or, if deletion is intentionally out of scope for Phase 4, remove the delete button from the UI to avoid the silent error state.

---

### CR-04: PriceChart sends unknown query parameter product_slug — data never loads

**File:** `dashboard/components/prices/PriceChart.tsx:78-83`
**Issue:** The component builds the query string with `product_slug: product` and passes it to `GET /prices/series`. The backend endpoint (`prices.py`) does not accept a `product_slug` parameter — it only accepts `product_id` (an integer). The `product_slug` values are strings like `"pp_raffia"`, `"hdpe"`, etc. The backend silently ignores the unknown `product_slug` param, applies no product filter, and returns all products for the selected date range. This means the chart always shows combined unfiltered data regardless of which product pill the user clicks.

Additionally, no mapping from `product_slug` → `product_id` is ever applied, so there is no path to send a correct `product_id` integer. The chart is effectively broken for per-product filtering.
**Fix:** Either add a `PRODUCT_SLUG_TO_ID` mapping in the frontend (matching the product IDs seeded in the DB), or add a `product_slug` lookup table/endpoint on the backend. At minimum, if a slug-to-id mapping exists, replace:
```typescript
const params = new URLSearchParams({
  product_slug: product,          // wrong — backend ignores this
  ...
```
with:
```typescript
const SLUG_TO_ID: Record<string, number> = {
  pp_raffia: 1, hdpe: 2, ldpe: 3, lldpe: 4,
  pvc: 5, pet: 6, ps: 7, abs: 8,
};
const productId = SLUG_TO_ID[product];
const params = new URLSearchParams({
  ...(productId != null ? { product_id: String(productId) } : {}),
  ...
```

---

### CR-05: TestResultBanner uses useState as useEffect — runs on every render

**File:** `dashboard/components/sources/SourcesList.tsx:75-88`
**Issue:** Line 75 calls `useState(() => { apiFetch(...).then(...) })` to trigger the test fetch. `useState` initializer runs only once on mount — **but the API call and `.then()` callbacks that call `setResult`, `setRunning`, `queryClient.invalidateQueries` are all registered correctly on mount.** However this is not the real problem. The real bug is that every time `SourcesList` re-renders (e.g., after `queryClient.invalidateQueries` refetches `["sources"]`), a **new** `TestResultBanner` is mounted (key is `source.id` but it always unmounts/remounts when `testingSourceId` changes). More critically: passing an impure side-effect function to `useState` is an anti-pattern that breaks in React Strict Mode (double-invocation in dev), and the `fetch` is started but the component has no abort controller — if the component unmounts before the fetch resolves, `setResult`/`setRunning` are called on an unmounted component causing React state update warnings, and after Strict Mode double-fire, **two concurrent tests are run against the same source**.

**Fix:** Replace `useState` initializer with `useEffect`:
```typescript
useEffect(() => {
  let cancelled = false;
  apiFetch<SourceTestResult>(`/sources/${sourceId}/test`, { method: "POST" })
    .then((r) => {
      if (cancelled) return;
      setResult(r);
      setRunning(false);
      if (r.ok) queryClient.invalidateQueries({ queryKey: ["sources"] });
    })
    .catch(() => {
      if (cancelled) return;
      setError("Test request failed. Check your connection.");
      setRunning(false);
    });
  return () => { cancelled = true; };
}, [sourceId, queryClient]);
```

---

## Warnings

### WR-01: list_requests has no filter support — filter params passed to it are silently ignored

**File:** `backend/app/api/dashboard_requests.py:133-171`
**Issue:** `GET /requests` ignores all filter query parameters (`status_filter`, `urgency`, `product_id`). The `list_requests` function signature accepts only `db` and `current_user` — no filter params. The frontend `RequestsTable` sends `?status=...&urgency=...&product_id=...` but the backend returns all rows regardless. The `export_requests` endpoint (line 201) correctly accepts and applies these filters, but the list endpoint does not. This means the FilterBar and filter chips appear to work (the URL updates) but the table never actually filters.
**Fix:** Add filter query parameters to `list_requests` and apply them:
```python
def list_requests(
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(get_current_staff_user),
    status_filter: str | None = Query(default=None, alias="status"),
    urgency: str | None = None,
    product_id: int | None = None,
) -> list[RequestListOut]:
    query = db.query(Request).order_by(Request.created_at.desc())
    if status_filter is not None:
        query = query.filter(Request.status == status_filter)
    if urgency is not None:
        query = query.filter(Request.urgency == urgency)
    if product_id is not None:
        query = query.filter(Request.product_id == product_id)
    reqs = query.all()
    ...
```

---

### WR-02: alert_rules list endpoint unbounded — no limit parameter

**File:** `backend/app/api/alert_rules.py:239-258`
**Issue:** `GET /alerts` accepts a `limit` parameter (defaulting to 100), but `GET /alert-rules` (line 114-129) returns all rules with no limit at all. In a production environment with many rules this is a denial-of-service vector (large payload). Consistency with the alerts endpoint also demands a cap.
**Fix:**
```python
@router.get("", response_model=list[AlertRuleOut])
def list_alert_rules(
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _: StaffUser = Depends(get_current_staff_user),
) -> list[AlertRuleOut]:
    rules = (
        db.query(AlertRule)
        .order_by(AlertRule.created_at.desc())
        .limit(limit)
        .all()
    )
```

---

### WR-03: XML external entity (XXE) exposure in RSS adapter

**File:** `backend/app/ingest/rss/adapter.py:97`
**Issue:** `ET.fromstring(content)` uses the default `xml.etree.ElementTree` parser which, in CPython's implementation, does not expand external entities but still processes entity declarations. More importantly, the content is fetched from user-supplied URLs (after the SSRF guard) and may be attacker-controlled. While CPython's `ElementTree` is not directly exploitable for classic XXE file reads (no external entity expansion), it is vulnerable to **billion laughs** (exponential entity expansion) XML bombs, causing CPU/memory exhaustion. The SSRF guard only protects against network-layer SSRF; it does not bound the size or complexity of the XML body.
**Fix:** Cap the response body size before parsing, and use `defusedxml` for entity-safe parsing:
```python
# In fetch_url / after response, add size cap before parsing:
if len(response.content) > 5 * 1024 * 1024:  # 5 MB cap
    raise ValueError("Feed response too large (>5 MB)")

# Replace ET.fromstring with defusedxml:
import defusedxml.ElementTree as DET
root = DET.fromstring(content)
```
If adding `defusedxml` is not feasible, at minimum cap the content size.

---

### WR-04: send_delivery does not send parse_mode="HTML" — HTML tags appear as literal text

**File:** `backend/app/tasks/notify.py:324`
**Issue:** `message_text = f"<b>{alert.title}</b>\n\n{alert.body}"` constructs an HTML-formatted message, but `bot.send_message(...)` is called without `parse_mode="HTML"`. Telegram will display the literal string `<b>Alert: ...</b>` including the angle-bracket tags instead of rendering bold text. Additionally, `alert.title` and `alert.body` are not HTML-escaped, so if they contain `<`, `>`, or `&` characters (e.g. from a grade text like `"PP > 1000 MT"`), the message will be malformed or silently truncated by Telegram.
**Fix:**
```python
import html

safe_title = html.escape(alert.title)
safe_body = html.escape(alert.body)
message_text = f"<b>{safe_title}</b>\n\n{safe_body}"

asyncio.run(
    bot.send_message(
        chat_id=chat_id,
        text=message_text,
        parse_mode="HTML",  # add this
    )
)
```

---

### WR-05: Keyset pagination cursor reset missing on filter change — stale page shown

**File:** `dashboard/components/feed/LiveFeedTable.tsx:155-175`
**Issue:** `cursorStack` (line 165) is never reset when the filter parameters (`period`, `kind`, `source`, `urgency`) change. When a user is on page 2 of "All Kinds" and switches the kind filter to "Buy Request", the component keeps the old cursor on the stack and sends it to the backend. The backend's keyset WHERE clause then intersects the cursor from the previous result set with the new filter, returning an arbitrary page deep into the new result set (or an empty page if the cursor is beyond all matching rows), rather than the first page of the new filter. Users see a confusing empty or mid-stream page when they change filters.
**Fix:** Add a `useEffect` that clears the cursor stack when filters change:
```typescript
const prevFiltersRef = useRef({ period, kind, source, urgency });
useEffect(() => {
  const prev = prevFiltersRef.current;
  if (prev.period !== period || prev.kind !== kind || prev.source !== source || prev.urgency !== urgency) {
    setCursorStack([]);
    prevFiltersRef.current = { period, kind, source, urgency };
  }
}, [period, kind, source, urgency]);
```

---

### WR-06: RequestActions.tsx — AlertDialog renders without a trigger inside AlertDialog root

**File:** `dashboard/components/requests/RequestActions.tsx:316-366`
**Issue:** The status dropdown and `AlertDialogContent` are both children of an `<AlertDialog>` wrapper (line 316), but there is no `<AlertDialogTrigger>` wrapping the select. The `AlertDialog` is opened implicitly by rendering `<AlertDialogContent>` conditionally when `selectedStatus === "cancelled"` (line 342). This pattern bypasses Radix UI's managed focus and accessibility state — the dialog's open/close state is controlled externally via conditional rendering rather than via the `open` prop, but the `<AlertDialog>` wrapper itself receives no `open` prop. This can cause the dialog to fail to trap focus, fail to close on Escape key, or render with broken ARIA attributes in certain Radix versions. The close button (`AlertDialogCancel`) is inside the content, but `onOpenChange` on the `AlertDialog` root is never wired, so pressing Escape does not revert `selectedStatus`.
**Fix:** Use the controlled `open` prop pattern consistently:
```tsx
const [showCancelDialog, setShowCancelDialog] = useState(false);

// In onChange handler:
if (val === "cancelled") {
  setSelectedStatus("cancelled");
  setShowCancelDialog(true);
} else { ... }

// AlertDialog:
<AlertDialog open={showCancelDialog} onOpenChange={(open) => {
  if (!open) { setSelectedStatus(status); setShowCancelDialog(false); }
}}>
  <AlertDialogContent>...</AlertDialogContent>
</AlertDialog>
```

---

### WR-07: useAuth isTokenExpired check skipped when payload.exp is absent

**File:** `dashboard/hooks/useAuth.ts:39-46`
**Issue:** `isTokenExpired` returns `false` (not expired) when `payload.exp` is absent (`if (!payload.exp) return false`). A JWT without an `exp` claim never expires from the client's perspective, so `isAuthenticated` would remain `true` even after the backend rejects the token with 401. The backend's `decode_token` presumably enforces expiry server-side, but the UI would never show the user as logged-out based on client-side token inspection alone. If a token without `exp` is ever issued (e.g., a debug token), the UI could show a perpetually "authenticated" state while all API calls return 401.
**Fix:** Treat a missing `exp` claim as expired, matching the principle of fail-closed:
```typescript
if (!payload.exp) return true;  // no exp = treat as expired
```

---

### WR-08: seed_demo.py inserts DEMO source with is_enabled=true but without config column

**File:** `backend/app/seed/seed_demo.py:59-66`
**Issue:** The INSERT for the `html_table` demo source sets `is_enabled=true` and `last_test_ok_at=now` but does not insert a `config` column value (the INSERT column list does not include `config`). If the `sources.config` column is NOT NULL or has no default, this INSERT will fail at runtime. If `config` does have a NULL default, the source is enabled without any config — when the `html_table` adapter's `fetch()` is called, `str(cfg.get("url") or "")` returns `""` and the adapter returns `[]` silently. The enabled-with-null-config source will appear healthy but collect nothing, which could confuse developers relying on the seed for acceptance testing.

Additionally, the condition in the seed's idempotency check (`name LIKE 'DEMO —%'`) will not match if the database character encoding treats the em-dash differently; use a simpler sentinel or check by exact name.
**Fix:** Add `config` to the INSERT:
```sql
INSERT INTO sources (kind, adapter, name, url, country, is_enabled,
                     config, last_test_ok_at, last_success_at, consecutive_failures)
VALUES ('website', 'html_table', :name, 'https://example.uz/prices',
        'UZ', true,
        '{"url": "https://example.uz/prices", "table_selector": "table"}'::jsonb,
        :now, :now, 0)
```

---

## Info

### IN-01: Redundant row-count check in CSV export generator

**File:** `backend/app/api/dashboard_requests.py:241`
**Issue:** Inside `_csv_generator()`, line 241 checks `if row_count >= _EXPORT_ROW_CAP: break` but the query is already limited by `.limit(_EXPORT_ROW_CAP)` on line 241. The SQLAlchemy `.limit()` ensures at most `_EXPORT_ROW_CAP` rows are fetched; the in-loop check is unreachable dead code.
**Fix:** Remove the redundant `if row_count >= _EXPORT_ROW_CAP: break` check, or add a comment explaining why it is belt-and-suspenders.

---

### IN-02: RequestsTable "Region" column always displays "—"

**File:** `dashboard/components/requests/RequestsTable.tsx:208-218`
**Issue:** The "Region" column accessor binds to `currency` (line 208: `columnHelper.accessor("currency", ...)`) but the cell renderer always returns `<span>—</span>` (line 214-216), discarding the actual currency value. The column was likely a placeholder for a `region` field that does not exist on `RequestListItem`. The column header says "Region", but the backing accessor is `currency` — an inconsistency that wastes a column and shadows the actual currency data.
**Fix:** Either remove the Region column from the requests table (since requests don't have a region field), or rename the accessor and header to "Currency" and render the actual value.

---

### IN-03: send_delivery — asyncio.run() inside a Celery sync task is fragile

**File:** `backend/app/tasks/notify.py:344`, also line 209 (`send_status_change_notification`)
**Issue:** Both Celery tasks use `asyncio.run(bot.send_message(...))` inside synchronous task functions. `asyncio.run()` creates a new event loop, runs the coroutine to completion, and closes the loop. This works in most cases but will fail if the task worker is running inside an already-running event loop (e.g., `gevent`-patched workers or if `uvloop` is installed and active). Additionally, creating/destroying an event loop per message is wasteful. Consider using `anyio.from_thread.run_sync_soon` or a shared loop, or making the tasks async and using Celery's async support.
**Fix (minimal):** Wrap with a try/except and document the constraint:
```python
try:
    asyncio.run(bot.send_message(...))
except RuntimeError:
    # Already inside a running loop (e.g., gevent); use nest_asyncio or worker config
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(bot.send_message(...))
```
Long-term: migrate to async Celery tasks or use `asyncio.get_event_loop().run_until_complete()` with a persistent loop.

---

### IN-04: RuleBuilder chat_id parsing silently produces NaN for non-numeric input

**File:** `dashboard/components/alerts/RuleBuilder.tsx:464`
**Issue:** `parseInt(chatId, 10)` is called on each line from the chat IDs textarea. If a user accidentally enters a non-numeric line (e.g., a Telegram @username, a blank line that slipped through the `.filter()`, or a string like "group"), `parseInt` returns `NaN`. `NaN` is serialized as `null` in JSON, so the POST body will contain `{"chat_id": null}`. The backend `_validate_channels` checks for the presence of `chat_id` key (not its value), so it passes validation. `Delivery.recipient = str(channel_config["chat_id"])` then stores the string `"None"` in the DB, which will cause `int("None")` to raise `ValueError` at send time in `send_delivery`.
**Fix:**
```typescript
const chatIds = formState.chatIds
  .split("\n")
  .map((l) => l.trim())
  .filter((l) => l.length > 0 && /^-?\d+$/.test(l)); // validate numeric
```
Add an error state if any lines are non-numeric.

---

### IN-05: useAuth token state initialized from module-level getToken — stale on SSR

**File:** `dashboard/hooks/useAuth.ts:49-53`
**Issue:** `useState<string | null>(getToken)` and `useState<AuthUser | null>(() => { const t = getToken(); ... })` are initialized from `_inMemoryToken`, which is a module-level variable. In Next.js, the module may be shared across requests in some edge/SSR configurations, causing the token from one user's request to leak into the initial state of another user's component tree. The `"use client"` directive limits this to client-side rendering in most Next.js 13+ app-router configurations, but the pattern is fragile. Since the token is always `null` on first SSR render anyway (it's only set after login), the `getToken` initialization is effectively a no-op on SSR and the risk is low — but it should be documented or guarded with `typeof window !== "undefined"`.
**Fix:** Minimal: guard initialization:
```typescript
const [token, setTokenState] = useState<string | null>(
  typeof window !== "undefined" ? getToken : null
);
```

---

_Reviewed: 2026-06-18_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
