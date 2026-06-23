---
phase: 03-client-circuit
plan: 02
subsystem: request-api
tags: [requests, status-machine, webapp, fastapi, idor, request-number, tdd]

# Dependency graph
requires:
  - phase: 03-client-circuit
    plan: 01
    provides: "get_current_client, validate_upload, upload_request_file, MAX_FILES, webapp Pydantic schemas, storage_service"
provides:
  - "request_service.py: generate_request_number (REQ-YYYY-MM-DD-NNNNN), create_request, transition_status, VALID_TRANSITIONS, CLIENT_STATUS_MAP, client_facing_status"
  - "POST /api/v1/webapp/requests: create request, returns REQ number, writes history, enqueues notify"
  - "GET /api/v1/webapp/requests: list authenticated client's requests (IDOR-safe)"
  - "GET /api/v1/webapp/requests/{id}: detail with history, IDOR-scoped 404 on cross-client"
  - "POST /api/v1/webapp/requests/{id}/files: ownership-scoped MinIO upload (MAX_FILES=5, magic bytes)"
  - "GET/PATCH /api/v1/webapp/me: client profile read + language update (ru/uz)"
affects:
  - "03-03-bot (notify task receives request.id to push status to client)"
  - "03-04-webapp-wizard (calls POST /webapp/requests)"
  - "03-05-webapp-my-requests (calls GET /webapp/requests + GET /webapp/requests/{id})"

# Tech tracking
tech-stack:
  added:
    - "python-multipart (installed in venv — was in pyproject.toml since 03-01 but not installed)"
  patterns:
    - "Per-date PostgreSQL sequence for atomic REQ number generation (req_seq_{YYYYMMDD})"
    - "Service-never-commits: request_service uses db.flush() only; routers own db.commit()"
    - "IDOR guard: WHERE client_id = dep.client.id (never body/query id) in all /webapp/* queries"
    - "Lazy notify import inside create_request/transition_status function bodies"
    - "TDD RED→GREEN: failing tests committed before each implementation"

key-files:
  created:
    - "backend/app/services/request_service.py (generate_request_number, create_request, transition_status, VALID_TRANSITIONS, CLIENT_STATUS_MAP, client_facing_status)"
    - "backend/app/api/webapp/__init__.py (package marker)"
    - "backend/app/api/webapp/requests.py (POST/GET /webapp/requests, GET /webapp/requests/{id})"
    - "backend/app/api/webapp/me.py (GET/PATCH /webapp/me)"
    - "backend/app/api/webapp/files.py (POST /webapp/requests/{id}/files)"
    - "backend/tests/test_request_service.py (32 tests — all green)"
    - "backend/tests/test_webapp_requests_api.py (21 tests — all green)"
  modified:
    - "backend/app/main.py (added three webapp router includes under /api/v1)"

key-decisions:
  - "DEC-lazy-notify-import: send_status_change_notification imported inside create_request/transition_status function bodies (not at module level) — keeps module import socket-free, avoids circular imports; test target is app.tasks.notify.send_status_change_notification with create=True"
  - "DEC-idor-opaque-404: GET /webapp/requests/{id} returns 404 for both 'not found' and 'not yours' — no cross-client information disclosure (T-03-07)"
  - "DEC-per-date-postgres-sequence: REQ number uses CREATE SEQUENCE IF NOT EXISTS req_seq_{YYYYMMDD} + SELECT nextval — atomic, concurrency-safe, no application-level locking"
  - "DEC-service-never-commits-confirmed: request_service.create_request and transition_status only call db.flush(); routers call db.commit() — grep db.commit() in request_service.py returns 0"

# Metrics
duration: 14min
completed: 2026-06-16
---

# Phase 3 Plan 02: Request API + Service Summary

**REQ-YYYY-MM-DD-NNNNN number generation via per-date PostgreSQL sequence, dev-spec §3 status machine, IDOR-scoped /webapp/* request + profile + file API**

## Performance

- **Duration:** 14 min
- **Started:** 2026-06-16T11:17:19Z
- **Completed:** 2026-06-16T11:31:26Z
- **Tasks:** 2 (Task 1: request_service; Task 2: webapp routers)
- **Files modified:** 9 (7 new, 2 modified)

## Accomplishments

- `request_service.py` implements the full dev-spec §3 status machine via `VALID_TRANSITIONS`, `generate_request_number` with Asia/Tashkent date + per-date PostgreSQL sequence, `create_request` (D-02 validated body, history row, lazy notify enqueue), `transition_status` (ValueError on invalid, audit_log for staff via `write_audit`, notify enqueue)
- `/webapp/requests`, `/webapp/me`, `/webapp/requests/{id}/files` — all handlers gated by `get_current_client`, data always scoped by `client.id` from verified dep
- IDOR guard (T-03-07): cross-client GET /requests/{id} and file upload return 404, never 403
- Status machine enforced server-side (T-03-09): client-facing API never sets status directly
- Audit trail (T-03-10): `transition_status` writes `audit_log` row via `write_audit` when `changed_by` is staff
- Service-never-commits axiom: `grep -c "db.commit()" request_service.py` → 0
- All 53 new tests green; full suite 368 passed (no regressions)

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 RED | Failing tests for request_service | 6d8572b | test_request_service.py |
| 1 GREEN | Implement request_service | 39a140c | request_service.py, test_request_service.py |
| 2 RED | Failing tests for webapp API | 94f6081 | test_webapp_requests_api.py |
| 2 GREEN | Implement webapp routers + main.py | 8964724 | 5 new files + main.py + test_webapp_requests_api.py |

## TDD Gate Compliance

Both tasks followed the required RED/GREEN cycle:
- Task 1: `test(03-02)` commit 6d8572b (RED) → `feat(03-02)` commit 39a140c (GREEN)
- Task 2: `test(03-02)` commit 94f6081 (RED) → `feat(03-02)` commit 8964724 (GREEN)
- No REFACTOR commits needed (implementation was clean on first write)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] python-multipart was in pyproject.toml but not installed in venv**
- **Found during:** Task 2 (when FastAPI's UploadFile routing raised RuntimeError at test collection)
- **Issue:** `python-multipart>=0.0.9` was added to pyproject.toml in 03-01 but the venv had not been updated (no `uv sync` or `pip install` was run). FastAPI's `ensure_multipart_is_installed()` check raised `RuntimeError: Form data requires "python-multipart" to be installed.`
- **Fix:** `pip install python-multipart` in the venv (version 0.0.32 installed). This is a standard install from pypi.org/project/python-multipart (legitimate, already approved in 03-01 Task 0 gate).
- **Files modified:** venv only (no code change)
- **Committed in:** Not a separate commit — venv install is not tracked by git

**2. [Rule 1 - Bug] Test patching target for notify task needed create=True**
- **Found during:** Task 1 (GREEN phase) when tests tried to patch `app.tasks.notify.send_status_change_notification`
- **Issue:** The `send_status_change_notification` task does not yet exist in `app.tasks.notify` (it is added in 03-03). Using `patch()` without `create=True` raises `AttributeError` when the attribute doesn't exist on the target module.
- **Fix:** Added `create=True` to all `patch("app.tasks.notify.send_status_change_notification", ...)` calls in `test_request_service.py`.
- **Files modified:** `backend/tests/test_request_service.py`
- **Committed in:** 39a140c (Task 1 GREEN commit)

**3. [Rule 1 - Bug] Test fixtures for webapp router tests needed direct db mock wiring**
- **Found during:** Task 2 (GREEN phase) when TestGetRequestDetail and TestFileUpload tests failed
- **Issue:** Tests patched `app.api.webapp.requests.Request` class but the actual `db.query()` chain used the fixture's MagicMock db — not the patched class. The mock returned MagicMock objects that failed Pydantic validation (not real ORM attributes). Tests for list/detail/file-upload needed the db mock to be configured to return proper mock Request objects.
- **Fix:** Rewrote those tests to create fresh TestClient instances with properly wired db mocks (setting `db.query().filter().first()` to return real typed mock objects). Tests for 401/422/404 error paths were straightforward; 200 happy-paths needed proper setup.
- **Files modified:** `backend/tests/test_webapp_requests_api.py`
- **Committed in:** 8964724 (Task 2 GREEN commit)

## Known Stubs

None. All new modules wire real logic:
- `generate_request_number` issues real SQL via `sa.text()` (CREATE SEQUENCE IF NOT EXISTS + SELECT nextval)
- `create_request` inserts real ORM objects, writes real history row
- `transition_status` validates against real `VALID_TRANSITIONS` dict
- All router handlers return real Pydantic-validated responses

## Threat Surface Scan

All threat surface introduced by this plan is covered by the plan's `<threat_model>`:

| Threat ID | Status |
|-----------|--------|
| T-03-07 (IDOR) | Mitigated — all queries scope by client.id from dep, cross-client returns 404 |
| T-03-08 (Spoofing) | Mitigated — create_request takes Client ORM from dep, no client_id in body |
| T-03-09 (Tampering) | Mitigated — VALID_TRANSITIONS enforced; ValueError→422 |
| T-03-10 (Repudiation) | Mitigated — transition_status writes audit_log when changed_by is staff |
| T-03-05 (DoS/files) | Mitigated — MAX_FILES=5 enforced before S3 write; validate_upload checks size |
| T-03-04 (Tampering/files) | Mitigated — magic-byte MIME detection via validate_upload |

No new threat surface beyond what the plan's threat model documents.

## Self-Check: PASSED

Files exist:
- backend/app/services/request_service.py — FOUND
- backend/app/api/webapp/__init__.py — FOUND
- backend/app/api/webapp/requests.py — FOUND
- backend/app/api/webapp/me.py — FOUND
- backend/app/api/webapp/files.py — FOUND
- backend/tests/test_request_service.py — FOUND
- backend/tests/test_webapp_requests_api.py — FOUND

Commits exist:
- 6d8572b — test(03-02): add failing tests for request_service (TDD RED)
- 39a140c — feat(03-02): implement request_service (TDD GREEN)
- 94f6081 — test(03-02): add failing tests for webapp request/me/files API (TDD RED)
- 8964724 — feat(03-02): implement webapp request/me/files routers, mount in main.py (TDD GREEN)

Acceptance criteria:
- grep -c "db.commit()" request_service.py → 0 (PASS)
- grep -c "webapp" main.py → 7 ≥ 3 (PASS)
- pytest tests/test_request_service.py → 32 passed (PASS)
- pytest tests/test_webapp_requests_api.py → 21 passed (PASS)
- pytest -q (full suite) → 368 passed, 65 skipped (PASS)
