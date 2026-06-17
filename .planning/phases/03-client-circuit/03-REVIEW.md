---
status: resolved
phase: 03-client-circuit
reviewed_base: e024332
reviewed_at: 2026-06-17
fixed_at: 2026-06-17
findings_total: 9
findings_fixed: 9
findings_by_severity:
  critical: 3
  high: 2
  medium: 3
  low: 1
---

# Phase 03: Client Circuit — Code Review

**Reviewed:** 2026-06-17
**Fixed:** 2026-06-17 — all 9 findings resolved
**Depth:** deep (cross-file analysis)
**Files Reviewed:** 28
**Status:** resolved — backend 386 passed / 65 skipped; webapp build green

## Summary

Phase 3 implements the Telegram Web App client circuit: initData HMAC auth, request wizard, file uploads, status notifications, and webhook validation. The security-critical Python auth code (HMAC constant-time compare, TTL, IDOR scoping) is well-structured. However, three BLOCKER-level defects were found: the CORS `allow_headers` list omits `X-Telegram-Init-Data` (breaks the entire webapp in CORS-preflight contexts), a Content-Type header leak corrupts multipart file uploads, and the webhook secret is exposed in plain-text log output at INFO level.

---

## Critical Issues

### CR-01: CORS `allow_headers` Missing `X-Telegram-Init-Data` — Every Authenticated Webapp Call Fails Cross-Origin ✓ RESOLVED (commit cc20644)

**File:** `backend/app/main.py:114`

**Issue:** The FastAPI CORSMiddleware is configured with:
```python
allow_headers=["Authorization", "Content-Type"],
```
Every `/webapp/*` endpoint requires the `X-Telegram-Init-Data` header for authentication. When the Telegram Web App runs from its origin and makes requests to the API origin, the browser sends a CORS preflight (`OPTIONS`) request. The server's preflight response will not include `X-Telegram-Init-Data` in `Access-Control-Allow-Headers`, so the browser rejects the request before it reaches the server. The result is that **every authenticated webapp call fails silently** (CORS error, no 401 — the request is never sent).

**Fix:**
```python
application.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Telegram-Init-Data"],
)
```

---

### CR-02: `uploadFile` in `api/client.ts` Sets `Content-Type: application/json` on Multipart Upload — File Uploads Broken ✓ RESOLVED (commit 0379b82)

**File:** `webapp/src/api/client.ts:36-54` (default headers) and `webapp/src/api/client.ts:91-101` (uploadFile)

**Issue:** `apiFetch` sets `"Content-Type": "application/json"` as a default, then spreads `options.headers` after it. The `uploadFile` method passes only `{ "X-Telegram-Init-Data": getInitData() }` in its `headers` object — it does **not** override or delete `Content-Type`. The comment says "We intentionally omit `Content-Type`", but the `Content-Type: application/json` default from `apiFetch` is **not overridden** and is sent with every file upload request.

A fetch with `body: FormData` and `Content-Type: application/json` causes the browser to not set the `multipart/form-data; boundary=...` header that FastAPI requires to parse the multipart body. FastAPI's `UploadFile` dependency will fail to find the `file` field and the upload will return HTTP 422.

**Fix:** Pass an explicit `undefined` (or use `Headers` object deletion) to remove the default `Content-Type` for multipart requests. The cleanest fix is to detect `FormData` in `apiFetch` and not set `Content-Type` in that case:

```typescript
async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      // Do NOT set Content-Type for multipart — browser must set boundary
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      "X-Telegram-Init-Data": getInitData(),
      ...options.headers,
    },
  });
  // ...
}
```

And remove the redundant `"X-Telegram-Init-Data": getInitData()` from `uploadFile`'s headers (it is already injected by `apiFetch`).

---

### CR-03: Webhook Secret Logged at INFO Level — Secret Exposed in Structured Logs ✓ RESOLVED (commit 40410f4)

**File:** `telegram/bot.py:113-117`

**Issue:**
```python
webhook_url = (
    f"{settings.PUBLIC_WEBAPP_URL}/api/v1/telegram/webhook/{settings.WEBHOOK_SECRET}"
)
logger.info("setup_webhook.start", extra={"webhook_url": webhook_url})
```
`WEBHOOK_SECRET` is embedded in the full `webhook_url` and emitted at INFO level on every application startup. Any log aggregator (Grafana Loki, Datadog, CloudWatch, etc.) receiving structured logs will store the secret in plain text, indexed and searchable. This defeats the dual-check security model (T-03-11) in environments where logs are accessible to operators who are not authorized to trigger webhooks.

**Fix:** Log only the URL prefix without the secret token:
```python
safe_url = f"{settings.PUBLIC_WEBAPP_URL}/api/v1/telegram/webhook/***"
logger.info("setup_webhook.start", extra={"webhook_url": safe_url})
```
The actual `webhook_url` (with secret) is only passed to `bot.set_webhook()`.

---

## High Severity

### HR-01: `auth_date` TTL Check Accepts Future Timestamps — Weak Replay Protection ✓ RESOLVED (commits c7d872f RED, cef4893 GREEN)

**File:** `backend/app/services/client_service.py:111-113`

**Issue:**
```python
age_seconds = int(time.time()) - auth_date
if age_seconds > INIT_DATA_TTL_SECONDS:
    raise InvalidInitData(...)
```
`age_seconds` is not checked for negative values. A token with `auth_date` set far in the future (e.g. `auth_date = now + 1_000_000`) produces `age_seconds = -1_000_000`, which is not `> INIT_DATA_TTL_SECONDS` (86400), so it passes. An attacker who can construct or obtain a token with a far-future `auth_date` can present it perpetually without expiry. Telegram itself would reject such a token, but the server-side check is supposed to be an independent enforcement layer.

**Fix:**
```python
age_seconds = int(time.time()) - auth_date
# Reject tokens from the future (more than 5 minutes of clock skew allowed)
if age_seconds < -300:
    raise InvalidInitData(f"initData from the future: age={age_seconds}s")
if age_seconds > INIT_DATA_TTL_SECONDS:
    raise InvalidInitData(f"initData expired: age={age_seconds}s > TTL={INIT_DATA_TTL_SECONDS}s")
```

---

### HR-02: `INIT_DATA_TTL_SECONDS` Module-Level Constant Bound at Import Time — Patching `settings` in Tests Has No Effect ✓ RESOLVED (commits c7d872f RED, cef4893 GREEN)

**File:** `backend/app/services/client_service.py:34`

**Issue:**
```python
INIT_DATA_TTL_SECONDS: int = settings.TELEGRAM_INIT_DATA_TTL_SECONDS
```
This constant is evaluated **once** when the module is first imported. If a test patches `settings.TELEGRAM_INIT_DATA_TTL_SECONDS` (e.g., to test TTL expiry), the change has no effect because `INIT_DATA_TTL_SECONDS` already holds the original value. The TTL used at runtime inside `verify_init_data` is always the value that was present at module-import time, not the live `settings` value. In production this is not a correctness bug (settings don't change at runtime), but it creates a silent testing gap: the TTL boundary is untestable without patching the module-level constant directly, which tests may not know to do.

**Fix:** Read `settings.TELEGRAM_INIT_DATA_TTL_SECONDS` directly in the function body:
```python
# Remove module-level constant
# INIT_DATA_TTL_SECONDS: int = settings.TELEGRAM_INIT_DATA_TTL_SECONDS

def verify_init_data(raw: str) -> dict[str, object]:
    # ...
    ttl = settings.TELEGRAM_INIT_DATA_TTL_SECONDS  # read live; patchable in tests
    if age_seconds > ttl:
        raise InvalidInitData(f"initData expired: age={age_seconds}s > TTL={ttl}s")
```

---

## Medium Severity

### MR-01: `send_status_change_notification` Calls `session.commit()` When Nothing Has Been Written — Unnecessary Noise ✓ RESOLVED (commit 6cc9335)

**File:** `backend/app/tasks/notify.py:214`

**Issue:**
```python
with Session(engine) as session:
    request = session.get(Request, request_id)
    # ... (read-only operations) ...
    asyncio.run(bot.send_message(...))
    session.commit()  # ← commits nothing (session is read-only)
```
The notify task only reads `request` and `client`; it never writes to the database. `session.commit()` on a read-only session is harmless but misleading: it implies there are pending writes, creating confusion for future developers who might add writes and expect commit semantics. It also performs a round-trip to the database unnecessarily.

**Fix:** Remove the `session.commit()` call. The `with Session(engine) as session:` block will automatically close (not commit) when exiting.

---

### MR-02: `uploadFile` in `api/client.ts` Declares Return Type `Promise<void>` but `apiFetch` Always Calls `res.json()` — Silent Parse Error ✓ RESOLVED (commit 0379b82, co-fixed with CR-02)

**File:** `webapp/src/api/client.ts:53` and `webapp/src/api/client.ts:87`

**Issue:** `uploadFile` is typed as `Promise<void>` and the caller in `Confirm.tsx` ignores the returned value. However, `apiFetch` always calls `return res.json() as Promise<T>` on successful responses. The backend returns HTTP 201 with a `RequestFileOut` JSON body. The `res.json()` call succeeds, returning a value that is then discarded as `void`. This is correct at runtime but masks the fact that there is a usable response: if a future caller wants the returned file ID or metadata, they will find the type says `void` and not realise the data is there.

More importantly: if the backend is ever changed to return HTTP 204 No Content, `res.json()` will throw a parse error, which propagates as an unhandled `ApiError` in the `catch` block in `Confirm.tsx`. The type `Promise<void>` gives no warning that this path is fragile.

**Fix:** Either type `uploadFile` as `Promise<RequestFileMeta>` (matching the actual 201 response) and use the result in `Confirm.tsx`, or document clearly in the type that the body is ignored. If 204 is ever intended, handle the empty-body case in `apiFetch`.

---

### MR-03: `RequestDetailOut` Schema Omits Several Fields Present on the `Request` Model — Incomplete Detail View ✓ RESOLVED (commits ab59e70, ce4b26a)

**File:** `backend/app/schemas/webapp.py:115-130`

**Issue:** `RequestDetailOut` exposes only a subset of the fields written during `create_request`. Missing from the detail response:
- `polymer_type` (one of the two D-02 minimum fields)
- `volume_unit`
- `destination_country`
- `port_or_city`
- `desired_date`
- `validity_days`
- `urgency`
- `comment`

The frontend `RequestDetail.tsx` shows `detail.grade_text` but cannot show `detail.polymer_type` because it is absent from the schema. A request submitted with only `polymer_type` (no `grade_text`) would appear to have no product identity in the detail view. Additionally, the `RequestDetail` TypeScript interface in `types.ts` matches the incomplete backend schema, so there is no type error, but the data is missing end-to-end.

**Fix:** Add the missing fields to `RequestDetailOut`:
```python
class RequestDetailOut(RequestOut):
    product_id: int
    grade_text: str | None
    polymer_type: str | None      # ← add
    volume: decimal.Decimal
    volume_unit: str               # ← add
    target_price: decimal.Decimal | None
    currency: str
    incoterms: PriceBasis
    destination_country: str       # ← add
    port_or_city: str | None       # ← add
    desired_date: datetime.date | None  # ← add
    validity_days: int             # ← add
    urgency: Urgency               # ← add
    comment: str | None            # ← add
    files: list[RequestFileOut]
    history: list[StatusHistoryOut]
```
Also update `backend/app/api/webapp/requests.py:128-141` to pass these fields to `RequestDetailOut(...)` and update `webapp/src/types.ts:RequestDetail` to include them.

---

## Low Severity

### LR-01: No Input Length Limit on Free-Text Fields in `RequestCreate` — Unbounded DB Writes ✓ RESOLVED (commit 2f50b36)

**File:** `backend/app/schemas/webapp.py:42-54`

**Issue:** `grade_text`, `polymer_type`, `comment`, and `port_or_city` are all `str | None` with no `max_length` constraint. The database columns are `Text` (PostgreSQL unbounded). A malicious client could submit a multi-megabyte string for `comment` on each request. There is no server-side length enforcement between the JSON parser and the database write.

**Fix:** Add `Field(max_length=...)` constraints appropriate to each field:
```python
from pydantic import BaseModel, Field, field_validator

grade_text: str | None = Field(default=None, max_length=500)
polymer_type: str | None = Field(default=None, max_length=500)
comment: str | None = Field(default=None, max_length=2000)
port_or_city: str | None = Field(default=None, max_length=200)
```

---

## What Was Checked (Clean)

The following areas were reviewed and found to be correct:

- **initData HMAC algorithm** (`client_service.py`): Telegram's two-stage HMAC (`HMAC(b"WebAppData", token)` → `HMAC(secret, data_check_string)`) implemented correctly. `hmac.compare_digest` used for constant-time comparison. Both arguments are `str` (ASCII hex), satisfying `compare_digest`'s type requirement.
- **IDOR scoping** (`requests.py`, `files.py`): Every `db.query(Request).filter(Request.id == ..., Request.client_id == client.id)` pattern is correct. Cross-client probing returns 404, not 403 (opaque by design). No endpoint reads `client_id` from the request body.
- **Webhook dual-check** (`telegram_webhook.py`): Both path secret and `X-Telegram-Bot-Api-Secret-Token` header are verified via `hmac.compare_digest`. Missing header → `header_ok = False` → 403. Correct.
- **S3 key path traversal** (`storage_service.py`): `os.path.basename` strips directory components; additional `.replace("/", "_")` and `".."` stripping closes Windows-path edge cases. `secrets.token_hex(8)` provides enumeration resistance.
- **Magic-byte MIME** (`storage_service.py`): File type checked by byte prefix, not file extension. Content-Type from client ignored; magic-detected MIME passed to `put_object`. Correct.
- **File count limit** (`files.py`): `existing_count >= MAX_FILES` checked before any S3 write. Correct.
- **Status state machine** (`request_service.py`): `VALID_TRANSITIONS` dict enforced server-side; `ValueError` on invalid transition; correct `cancelled → {}` and `closed → {}` terminal states.
- **REQ number generation** (`request_service.py`): `yyyymmdd.isdigit()` guard before `seq_name` interpolation in `sa.text(f"CREATE SEQUENCE ...")`. Because `yyyymmdd` comes from `today.strftime("%Y%m%d")` (always 8 ASCII digits), this is safe, and the guard is defense-in-depth. Correct.
- **`get_current_client` generic 401** (`deps.py`): All failure paths (`InvalidInitData`, missing header, missing `user` field, invalid `id`) raise the same `HTTPException(401, "Authentication required")`. No hint leakage.
- **Celery task never-raises contract** (`notify.py`): Top-level `except Exception` catches all failures; returns `{"status": "error", "error": str(exc)}` instead of re-raising. Worker stays alive.
- **`asyncio.run` in Celery task** (`notify.py`): Celery workers run synchronous tasks; `asyncio.run()` creates a new event loop for the `bot.send_message` coroutine. This is correct for Celery's default worker model (not Celery with gevent/eventlet; those would conflict, but the compose config uses the default prefork pool).
- **Client profile patch scoping** (`me.py`): `PATCH /webapp/me` only applies to fields from the `ClientProfilePatch` schema (`language`, `company_name`, `contact_name`). No `telegram_user_id` or `id` field is writable. Correct.
- **`product_id ?? 0` in Confirm.tsx**: Line 55 sends `product_id: 0` if the store somehow has `null`. The backend `RequestCreate` schema will accept `0` for `product_id` since the field is `int` with no minimum validation. This is a pre-existing data integrity gap (no `ge=1` on `product_id`), but cannot be triggered through normal wizard flow because Step 1 validates `product_id >= 1` via Zod before advancing. Low risk in practice; documented here for completeness.

---

_Reviewed: 2026-06-17_
_Reviewer: Claude (adversarial code review — deep mode)_
