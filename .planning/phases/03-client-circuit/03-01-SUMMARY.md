---
phase: 03-client-circuit
plan: 01
subsystem: auth
tags: [telegram, initdata, hmac, minio, s3, boto3, fastapi, auth, upload, pydantic]

# Dependency graph
requires:
  - phase: 02-ingest-core-uzex
    provides: "Settings class with S3_* fields, existing deps.py with get_current_staff_user pattern, audit_service db.flush() convention"
provides:
  - "Telegram initData HMAC verification + 24h TTL (verify_init_data, T-03-01/02/03)"
  - "get_current_client FastAPI dependency — upserts clients row, returns Client (T-03-06)"
  - "S3/MinIO client constructor (core/storage.py, lazy import-safe, ensure_bucket())"
  - "Upload validation: magic-byte MIME + 10MB limit + traversal-safe S3 key (T-03-04/05/06)"
  - "webapp Pydantic schemas: RequestCreate (D-02), RequestOut, RequestDetailOut, ClientProfileOut, ClientProfilePatch"
  - "MinIO dev-compose service with healthcheck + volume; S3_ENDPOINT wired to api+worker"
  - "New deps: aiogram>=3.13.0, boto3>=1.34.0, python-multipart>=0.0.9, moto>=5.0.0 (dev)"
affects:
  - "03-02-request-api (uses get_current_client + RequestCreate schemas + upload_request_file)"
  - "03-03-bot (uses client_service.get_or_create_client)"
  - "03-04-webapp-wizard (uses RequestCreate schema + POST /webapp/requests)"
  - "03-05-webapp-my-requests (uses RequestOut/RequestDetailOut schemas)"
  - "03-06-ops (uses MinIO volume for backup/restore)"

# Tech tracking
tech-stack:
  added:
    - "aiogram>=3.13.0 (Telegram bot framework, webhook via FastAPI)"
    - "boto3>=1.34.0 (AWS/MinIO S3 SDK)"
    - "python-multipart>=0.0.9 (FastAPI multipart file upload parsing)"
    - "moto>=5.0.0 (dev) — S3 mock for storage tests"
  patterns:
    - "Lazy S3 client via _LazyS3Client proxy — module import never opens socket"
    - "Magic-byte MIME detection: size check first, then MAGIC_BYTES startswith"
    - "Traversal-safe S3 key: requests/{id}/{token_hex(8)}-{sanitized_basename}"
    - "TDD RED→GREEN: failing test committed before implementation"
    - "db.flush() not db.commit() in service layer (client_service, storage_service)"

key-files:
  created:
    - "backend/app/services/client_service.py (verify_init_data, get_or_create_client)"
    - "backend/app/core/storage.py (get_s3_client, _LazyS3Client, ensure_bucket)"
    - "backend/app/services/storage_service.py (validate_upload, upload_request_file)"
    - "backend/app/schemas/webapp.py (RequestCreate, RequestOut, RequestDetailOut, ClientProfileOut, ClientProfilePatch, etc.)"
    - "backend/tests/test_init_data_auth.py (13 tests — all green)"
    - "backend/tests/test_storage_validation.py (13 tests — all green)"
  modified:
    - "backend/pyproject.toml (added 4 packages)"
    - "backend/app/core/config.py (PUBLIC_WEBAPP_URL, TELEGRAM_INIT_DATA_TTL_SECONDS)"
    - "backend/app/api/deps.py (added get_current_client dependency)"
    - "deploy/docker-compose.dev.yml (minio service + volume + S3_ENDPOINT wiring)"

key-decisions:
  - "DEC-lazy-s3-client: _LazyS3Client proxy defers boto3 import until first attribute access — keeps pytest collection socket-free when boto3 is not installed"
  - "DEC-magic-byte-size-order: size check fires BEFORE magic-byte check in validate_upload — fast-path rejection for oversize files regardless of content type"
  - "DEC-traversal-safe-key: S3 key built as requests/{id}/{token_hex(8)}-{os.path.basename(filename)} — strips directory components + random token prevents enumeration (T-03-06)"
  - "DEC-generic-401: all initData failure paths raise InvalidInitData (ValueError subclass) caught by deps.py → generic 401 — never reveals which check failed (T-03-03)"
  - "DEC-dep-owns-commit: get_current_client dependency calls db.commit() after upsert; service functions call db.flush() only"

patterns-established:
  - "verify_init_data: URL-decode → extract hash → build data_check_string (sorted key=value) → HMAC_SHA256(HMAC_SHA256(b'WebAppData', BOT_TOKEN), dcs) → compare_digest → TTL check → json.loads(user)"
  - "_LazyS3Client proxy pattern: module-level singleton that defers boto3 instantiation until first use"
  - "upload_request_file: validate_upload → traversal-safe key → s3_client.put_object → RequestFile ORM insert → db.flush()"

requirements-completed: [REQ-webapp-auth, REQ-nfr-performance]

# Metrics
duration: 10min
completed: 2026-06-16
---

# Phase 3 Plan 01: Client Circuit Foundation Summary

**Telegram initData HMAC auth dependency (get_current_client), MinIO S3 client with traversal-safe upload validation, and webapp Pydantic schema contract for the request wizard**

## Performance

- **Duration:** 10 min
- **Started:** 2026-06-16T11:01:07Z
- **Completed:** 2026-06-16T11:11:07Z
- **Tasks:** 3 (Tasks 1-3; Task 0 was the human-gate approved by user prior to this executor)
- **Files modified:** 10

## Accomplishments

- initData HMAC authentication dependency (`get_current_client`) verified per Telegram algorithm with 24h TTL, idempotent client upsert, and generic 401 on all failure paths
- Upload validation (`validate_upload`) enforces magic-byte MIME detection (not extension), 10 MB limit, traversal-safe S3 keys before any MinIO write
- webapp Pydantic schemas contract established: `RequestCreate` with D-02 minimum-to-submit validator, read-side schemas for requests/files/history, and `ClientProfilePatch`
- MinIO added to docker-compose.dev.yml with healthcheck, named volume, and `S3_ENDPOINT` wired to api and worker services

## Task 0: Package Legitimacy Gate (Human Approval Outcome)

Task 0 was a `checkpoint:human-verify` gate (gate="blocking-human") requiring human verification of four packages on pypi.org before install:

| Package | PyPI URL | Verification |
|---------|----------|--------------|
| aiogram | pypi.org/project/aiogram/ | Approved by user |
| boto3 | pypi.org/project/boto3/ | Approved by user |
| python-multipart | pypi.org/project/python-multipart/ | Approved by user |
| moto | pypi.org/project/moto/ | Approved by user |

**Outcome:** Human reviewed all four packages and provided the "approved" resume signal before this executor ran. No typosquats found. All four packages added to pyproject.toml as specified.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add deps, config, MinIO compose** - `4bf7064` (feat)
2. **Task 2 RED: Failing tests for initData HMAC auth** - `7e62bdd` (test — TDD RED)
3. **Task 2 GREEN: client_service + get_current_client** - `03ff0be` (feat — TDD GREEN)
4. **Task 3 RED: Failing tests for storage validation** - `3fb7658` (test — TDD RED)
5. **Task 3 GREEN: storage.py + storage_service.py + schemas/webapp.py** - `a8d78dc` (feat — TDD GREEN)

## TDD Gate Compliance

Both TDD tasks followed the required RED/GREEN cycle:
- Task 2: `test(03-01)` commit 7e62bdd (RED) → `feat(03-01)` commit 03ff0be (GREEN)
- Task 3: `test(03-01)` commit 3fb7658 (RED) → `feat(03-01)` commit a8d78dc (GREEN)
- No REFACTOR commits needed (implementation was clean on first write)

## Files Created/Modified

- `backend/pyproject.toml` — added aiogram, boto3, python-multipart (runtime), moto (dev)
- `backend/app/core/config.py` — added PUBLIC_WEBAPP_URL and TELEGRAM_INIT_DATA_TTL_SECONDS
- `deploy/docker-compose.dev.yml` — added minio service, minio_data volume, S3_ENDPOINT on api/worker
- `backend/app/services/client_service.py` — verify_init_data + get_or_create_client
- `backend/app/api/deps.py` — added get_current_client dependency
- `backend/app/core/storage.py` — get_s3_client() + _LazyS3Client proxy + ensure_bucket()
- `backend/app/services/storage_service.py` — validate_upload + upload_request_file
- `backend/app/schemas/webapp.py` — RequestCreate/Out/DetailOut, StatusHistoryOut, RequestFileOut, ClientProfileOut/Patch
- `backend/tests/test_init_data_auth.py` — 13 tests (all green)
- `backend/tests/test_storage_validation.py` — 13 tests (all green)

## Decisions Made

- **DEC-lazy-s3-client:** `_LazyS3Client` proxy defers boto3 import until first attribute access — keeps pytest collection socket-free when boto3 is not installed in the venv (e.g., CI before install step).
- **DEC-magic-byte-size-order:** size check fires BEFORE magic-byte check in `validate_upload` — fast-path rejection for oversize files regardless of content type (mirrors the plan's documented order).
- **DEC-traversal-safe-key:** S3 key = `requests/{id}/{token_hex(8)}-{os.path.basename(filename)}` — `os.path.basename` strips directory components, random token prevents enumeration (T-03-06).
- **DEC-generic-401:** All initData failures raise `InvalidInitData` (ValueError subclass); `get_current_client` catches `ValueError` and returns a single generic 401 "Authentication required" — never reveals which check failed (T-03-03).
- **DEC-dep-owns-commit:** `get_current_client` calls `db.commit()` after upsert (the dep owns the upsert transaction); service functions `client_service` and `storage_service` call `db.flush()` only (caller commits pattern).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed _LazyS3Client to make storage.py import-safe**
- **Found during:** Task 3 (storage_service.py implementation — GREEN phase)
- **Issue:** The plan pattern showed `s3_client = get_s3_client()` at module level, but boto3 is not installed in the test venv. Running tests imports the module which immediately tried to `import boto3` — raising `ModuleNotFoundError`.
- **Fix:** Replaced the direct `s3_client = get_s3_client()` call with a `_LazyS3Client` proxy class that defers `import boto3` until the first attribute access (method call). The module now imports cleanly even without boto3 installed.
- **Files modified:** `backend/app/core/storage.py`
- **Verification:** `pytest tests/test_storage_validation.py` passes 13 tests; full suite 315 passed.
- **Committed in:** a8d78dc (Task 3 feat commit)

**2. [Rule 1 - Bug] Fixed test patching target for upload_request_file S3 key test**
- **Found during:** Task 3 (test_storage_validation.py, traversal-safe key test)
- **Issue:** Test patched `storage_service.s3_client` but `s3_client` is only imported inside the function body (lazy), so it does not exist as a module attribute on `storage_service`.
- **Fix:** Updated test to patch `app.core.storage.s3_client` (the actual module where `s3_client` lives as `_LazyS3Client` instance) and also fixed the import to use `app.core.storage as storage_module`.
- **Files modified:** `backend/tests/test_storage_validation.py`
- **Verification:** Traversal-safe key test passes.
- **Committed in:** a8d78dc (Task 3 feat commit)

---

**Total deviations:** 2 auto-fixed (Rule 1 — bugs in plan pattern vs. actual runtime behavior)
**Impact on plan:** Both fixes necessary for test correctness. No scope creep. All acceptance criteria met.

## Issues Encountered

None beyond the two auto-fixed deviations documented above.

## Known Stubs

None. All new modules wire real logic:
- `verify_init_data` implements full Telegram HMAC algorithm
- `get_or_create_client` does a real SELECT-then-INSERT pattern
- `validate_upload` checks actual magic bytes
- schemas enforce real D-02 field validation

## Threat Surface Scan

No new threat surface beyond what the plan's `<threat_model>` documents (T-03-01 through T-03-06 all mitigated by this plan's implementation).

## Next Phase Readiness

- `get_current_client` dependency is ready for 03-02 request API (`POST /webapp/requests`)
- `validate_upload` + `upload_request_file` ready for 03-02 file upload router
- All webapp schemas ready for 03-02 response serialization
- Bot can call `get_or_create_client` directly from 03-03 start handler
- MinIO compose service ready for integration testing

---
*Phase: 03-client-circuit*
*Completed: 2026-06-16*
