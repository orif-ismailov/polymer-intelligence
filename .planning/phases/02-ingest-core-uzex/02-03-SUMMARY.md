---
phase: 02-ingest-core-uzex
plan: 03
subsystem: api
tags: [ingest, adapter, registry, ssrf, httpx, fastapi, pydantic]

# Dependency graph
requires:
  - phase: 02-ingest-core-uzex
    provides: "02-01 config settings (INGEST_HTTP_TIMEOUT_SECONDS, INGEST_HTTP_RETRIES, INGEST_USER_AGENT, INGEST_PER_HOST_DELAY_SECONDS) and 02-02 models/services foundation"
provides:
  - "SourceAdapter Protocol (typing.Protocol, runtime_checkable) with type_name, config_schema, fetch(), test()"
  - "RawItemDraft dataclass (external_id, content, payload, event_at)"
  - "TestResult dataclass (ok, sample_rows capped at 10, error)"
  - "Name-keyed adapter registry (register_adapter, get_adapter, list_adapters)"
  - "SSRF-hardened httpx fetch client (is_safe_url + fetch_url with timeout/retries/UA/per-host-delay/body-cap)"
  - "GET /api/v1/admin/source-types endpoint (admin-guarded, returns type_name+config_schema+no_code)"
affects:
  - "02-04-UZEX: registers uzex_* adapters against this registry"
  - "02-05-CBU: registers cbu_rates adapter against this registry"
  - "Phase 4 source constructor: reads config_schema from GET /admin/source-types to auto-generate add-source form"
  - "All future collectors: MUST route outbound fetches through fetch_url (SSRF chokepoint)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SourceAdapter Protocol pattern: concrete adapters need no base class, just satisfy Protocol"
    - "Registry self-registration pattern: adapters register at import time via register_adapter()"
    - "SSRF guard at DNS-resolution time: is_safe_url() resolves hostname before any socket activity"
    - "Streaming body read with size cap: aiter_bytes() + accumulate with MAX_RESPONSE_BYTES check"
    - "Deferred imports in test files to avoid Settings() before conftest patch_env fixture runs"

key-files:
  created:
    - "backend/app/ingest/__init__.py"
    - "backend/app/ingest/base.py"
    - "backend/app/ingest/registry.py"
    - "backend/app/ingest/http_client.py"
    - "backend/app/api/admin_sources.py"
    - "backend/tests/test_adapter_registry.py"
    - "backend/tests/test_http_client_ssrf.py"
    - "backend/tests/test_admin_source_types.py"
  modified:
    - "backend/app/main.py"
    - "backend/pyproject.toml"

key-decisions:
  - "DEC-source-adapter-registry: SourceAdapter is a typing.Protocol (runtime_checkable) not a base class — adapters self-register at import time via register_adapter(); registry indexed by type_name"
  - "DEC-ssrf-dns-resolution: SSRF guard resolves hostname via socket.getaddrinfo() at validation time and rejects loopback/private/link-local/reserved IPs; DNS failure = fail-safe reject"
  - "DEC-body-cap-streaming: fetch_url reads in 64 KB chunks via aiter_bytes() and raises ValueError before buffering completes — prevents worker OOM on oversized responses (T-02-08)"
  - "DEC-http-client-deferred-import: app.ingest.__init__.py does NOT re-export from http_client to avoid triggering Settings() at pytest collection time; tests import http_client directly inside function bodies"
  - "DEC-no-code-flag: no_code=True for telegram_channel/llm_page/html_table/rss (admin-addable via Phase-4 wizard); no_code=False for uzex_*/cbu_rates/sunsirs/dce (built-in specialized adapters)"
  - "DEC-jose-mypy-override: added jose/jose.* ignore_missing_imports override to pyproject.toml (pre-existing gap in celery/kombu override list) to unblock mypy on admin_sources.py"

patterns-established:
  - "Protocol-based adapters: no inheritance required, type_name + config_schema + fetch() + test() suffice"
  - "Deferred app module imports in test functions (not at module level) to sidestep Settings() at pytest collection time"
  - "Admin-guarded registry endpoints: Depends(require_admin) returns 403 for all non-admin roles"

requirements-completed:
  - REQ-uzex-parser
  - REQ-sources-health

# Metrics
duration: 10min
completed: 2026-06-15
---

# Phase 02 Plan 03: SourceAdapter Registry + Hardened HTTP Client Summary

**SourceAdapter Protocol + name-keyed registry + SSRF-hardened httpx fetch client + GET /admin/source-types admin endpoint; 46 tests all passing, ruff + mypy clean**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-15T12:29:00Z
- **Completed:** 2026-06-15T12:39:45Z
- **Tasks:** 2 completed
- **Files modified:** 10 (8 created, 2 modified)

## Accomplishments

- Defined the SourceAdapter Protocol (`type_name`, `config_schema`, `fetch()`, `test()`) with `RawItemDraft` and `TestResult` dataclasses; `TestResult` enforces the 10-row preview cap in `__post_init__`
- Built the name-keyed adapter registry with `register_adapter`/`get_adapter`/`list_adapters`; raises `ValueError` on duplicate `type_name` and `KeyError` with registered list on unknown lookup
- Implemented SSRF-hardened httpx fetch client: `is_safe_url()` rejects loopback/private/link-local/reserved IPs via DNS resolution and blocks non-http(s) schemes; `fetch_url()` enforces 30s timeout, 3 retries with exponential backoff, `INGEST_USER_AGENT`, per-host delay, and 25 MB streaming body cap
- Exposed `GET /api/v1/admin/source-types` returning `[{type_name, config_schema, no_code}]` for all registered adapters, guarded by `require_admin` (T-02-10); router mounted in main.py under `/api/v1`

## Task Commits

Each task was committed atomically:

1. **Task 1: SourceAdapter Protocol, registry, and SSRF-hardened httpx fetch client** - `edcf4d0` (feat)
2. **Task 2: GET /admin/source-types endpoint** - `ff62e8a` (feat)

**Plan metadata:** (committed with state updates below)

## Files Created/Modified

- `backend/app/ingest/__init__.py` - Package entry point; re-exports Protocol + registry symbols (http_client deferred)
- `backend/app/ingest/base.py` - `SourceAdapter` Protocol (runtime_checkable), `RawItemDraft`, `TestResult` dataclasses
- `backend/app/ingest/registry.py` - Name-keyed adapter registry with `_clear_registry()` for test isolation
- `backend/app/ingest/http_client.py` - `is_safe_url()` SSRF guard + `fetch_url()` with all transport controls + `MAX_RESPONSE_BYTES` cap
- `backend/app/api/admin_sources.py` - `GET /admin/source-types` with `SourceTypeItem` response model, `no_code` flag logic
- `backend/app/main.py` - Added `admin_sources_router` import and mount under `/api/v1`
- `backend/tests/test_adapter_registry.py` - 14 tests: Protocol, registry round-trip, duplicate/unknown key, dataclass cap
- `backend/tests/test_http_client_ssrf.py` - 20 tests: SSRF rejection, public URL acceptance, retry count, body cap, UA header
- `backend/tests/test_admin_source_types.py` - 12 tests: admin 200, 403 for trader/viewer/analyst, 401 no token, no_code flags, router mount
- `backend/pyproject.toml` - Added `jose`/`jose.*` mypy override (pre-existing gap)

## Decisions Made

- `SourceAdapter` is a `typing.Protocol` (not an ABC) — concrete adapters need no import from base, just satisfy the Protocol signature; registered by calling `register_adapter()` at import time
- `is_safe_url()` performs DNS resolution via `socket.getaddrinfo()` at validation time (before any HTTP socket activity); DNS failure = fail-safe reject to prevent bypass via non-resolving hostnames
- `fetch_url()` uses `async with client.stream()` and `aiter_bytes(64KB)` to read in chunks — raises `ValueError` if accumulated bytes exceed `MAX_RESPONSE_BYTES` without ever buffering the full body
- `app/ingest/__init__.py` does NOT re-export from `http_client` to avoid triggering `Settings()` at pytest collection time; the `patch_env` session fixture only runs before test execution, not collection
- `no_code=True` for `telegram_channel`/`llm_page`/`html_table`/`rss` (admin-addable via Phase-4 no-code wizard); `no_code=False` for `uzex_*`/`cbu_rates`/`sunsirs`/`dce` (built-in specialized adapters shipped with the system)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Python 3.14 class body variable scoping NameError in test helper**
- **Found during:** Task 1 (test execution)
- **Issue:** `class DummyAdapter: type_name = type_name` raises `NameError` in Python 3.14 because class body variable lookup changed; outer `type_name` parameter is not visible in class scope
- **Fix:** Set `adapter.type_name = adapter_type_name` on the instance after class creation
- **Files modified:** `backend/tests/test_adapter_registry.py`
- **Verification:** 14 tests passed after fix
- **Committed in:** edcf4d0 (Task 1 commit)

**2. [Rule 2 - Missing Critical] Deferred http_client imports in test files**
- **Found during:** Task 1 (test collection error)
- **Issue:** `test_http_client_ssrf.py` imported `from app.ingest.http_client import ...` at module level, triggering `Settings()` before conftest `patch_env` session fixture ran, causing 10-field ValidationError during pytest collection
- **Fix:** Moved all `app.ingest.http_client` imports inside test function bodies (same pattern as `test_celery_app.py` and `test_rbac.py`)
- **Files modified:** `backend/tests/test_http_client_ssrf.py`
- **Verification:** 20 tests collected and passed after fix
- **Committed in:** edcf4d0 (Task 1 commit)

**3. [Rule 1 - Bug] Removed eager http_client re-export from package __init__**
- **Found during:** Task 1 (test collection — same root cause as deviation 2)
- **Issue:** `app/ingest/__init__.py` imported `from app.ingest.http_client import fetch_url, is_safe_url` at package level, which triggered Settings() when any submodule of `app.ingest` was imported
- **Fix:** Removed the `http_client` re-export from `__init__.py`; callers import directly from `app.ingest.http_client`
- **Files modified:** `backend/app/ingest/__init__.py`
- **Verification:** Both test files collected and 34 tests passed
- **Committed in:** edcf4d0 (Task 1 commit)

**4. [Rule 2 - Missing Critical] Added `jose` mypy override to pyproject.toml**
- **Found during:** Task 2 (mypy verification of admin_sources.py)
- **Issue:** `mypy app/api/admin_sources.py` failed with "Library stubs not installed for jose" — pre-existing gap in mypy overrides (celery/kombu were covered but jose was not); `admin_sources.py` imports from `deps.py` which imports `jose`
- **Fix:** Added `[[tool.mypy.overrides]] module = ["jose", "jose.*"] ignore_missing_imports = true` to pyproject.toml
- **Files modified:** `backend/pyproject.toml`
- **Verification:** `mypy app/ingest app/api/admin_sources.py` passes cleanly
- **Committed in:** ff62e8a (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (2 Rule 1 bugs, 2 Rule 2 missing critical)
**Impact on plan:** All auto-fixes necessary for test collection, correctness, and mypy verification. No scope creep.

## Issues Encountered

- Python 3.14 tightened class body variable scoping — `type_name = type_name` in a class body now raises NameError where Python 3.12 would have resolved the outer variable. Fixed by instance attribute assignment after class creation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `app.ingest` package with Protocol + registry + HTTP client is complete; 02-04 (UZEX) and 02-05 (CBU) can register their adapters against this
- `GET /api/v1/admin/source-types` is live and returns each adapter's `config_schema` — Phase 4 source constructor can use this as-is
- All future collectors MUST import and use `fetch_url()` from `app.ingest.http_client` as the single outbound HTTP chokepoint

---
*Phase: 02-ingest-core-uzex*
*Completed: 2026-06-15*
