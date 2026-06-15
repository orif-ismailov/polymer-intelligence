---
phase: 02-ingest-core-uzex
plan: "06"
subsystem: ingest-health
tags:
  - source-health
  - failure-isolation
  - alerting
  - celery
  - fastapi
dependency_graph:
  requires:
    - 02-01 (celery_app, beat schedule, check_source_health slot)
    - 02-04 (uzex_fetch_* tasks, raw_pipeline)
    - 02-05 (fetch_cbu_rates task pattern)
  provides:
    - source_health_service (record_fetch_success, record_fetch_failure, check_all_sources_health)
    - check_source_health Celery beat task (*/5 min)
    - GET /api/v1/admin/sources/health endpoint
    - run_source_fetch_isolated helper in ingest.py
  affects:
    - app/tasks/ingest.py (wraps all per-source fetches with isolation + health recording)
    - app/api/admin_sources.py (adds health route to existing router)
tech_stack:
  added: []
  patterns:
    - "3-strike deduped alert: dedupe_key source_failure:{source_id}:{date} + ON CONFLICT DO NOTHING"
    - "db.flush() inside raise_source_failure_alert; caller commits (audit_service pattern)"
    - "run_source_fetch_isolated: try/except per source, NEVER re-raises"
key_files:
  created:
    - backend/app/services/source_health_service.py
    - backend/app/tasks/notify.py
    - backend/tests/test_source_health.py
    - backend/tests/test_source_failure_alert.py
  modified:
    - backend/app/tasks/ingest.py
    - backend/app/api/admin_sources.py
decisions:
  - "source_health_service uses db.flush() not db.commit() — caller commits (consistent with audit_service)"
  - "save_raw_items promoted to module-level import in ingest.py for testability (was local import)"
  - "run_source_fetch_isolated returns int (inserted count) so caller can track batch totals"
  - "_execute_uzex_fetch simplified — errors list removed since run_source_fetch_isolated never re-raises"
metrics:
  duration: "8 minutes"
  completed_date: "2026-06-15"
  tasks: 2
  files_created: 4
  files_modified: 2
---

# Phase 02 Plan 06: Source Health + Failure Isolation Summary

**One-liner:** 3-strike deduped source_failure alert via source_health_service with per-source fetch isolation in ingest tasks and GET /admin/sources/health for the dashboard.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 (RED) | Failing tests for source_health_service | 3120200 | tests/test_source_health.py |
| 1 (GREEN) | source_health_service implementation | b88d5bc | app/services/source_health_service.py |
| 2 (RED) | Failing tests for isolation + task + endpoint | 45b578b | tests/test_source_failure_alert.py |
| 2 (GREEN) | Isolation helper, notify task, health endpoint | 5353d42 | app/tasks/ingest.py, app/tasks/notify.py, app/api/admin_sources.py |

## What Was Built

### source_health_service (backend/app/services/source_health_service.py)

- `record_fetch_success(session, source_id)`: UPDATE sources SET last_fetch_at=now(), last_success_at=now(), consecutive_failures=0
- `record_fetch_failure(session, source_id, error)`: increments consecutive_failures by 1, logs structured error; if new count >= 3 calls raise_source_failure_alert; returns new count
- `raise_source_failure_alert(session, source_id)`: INSERT alert kind=source_failure, severity=warning, dedupe_key=source_failure:{source_id}:{date.today()} ON CONFLICT (dedupe_key) DO NOTHING; calls db.flush()
- `check_all_sources_health(session)`: scans enabled sources with consecutive_failures >= 3, calls raise_source_failure_alert for each — idempotent defense-in-depth (T-02-22)

### check_source_health task (backend/app/tasks/notify.py)

Replaces the 02-01 placeholder. Registered under the same task name so the */5 beat schedule in schedule.py automatically routes to it. Calls check_all_sources_health and commits. Guarantees the deduped source_failure alert surfaces within 30 minutes.

### run_source_fetch_isolated (backend/app/tasks/ingest.py)

Per-source fetch isolation wrapper. Wraps fetch + save + health recording in try/except:
- On success: calls record_fetch_success, enqueues parse tasks
- On exception: logs structured, rolls back, calls record_fetch_failure, NEVER re-raises

`_execute_uzex_fetch` now iterates sources through this helper — the inline try/except and manual last_fetch_at UPDATE were removed.

### GET /admin/sources/health (backend/app/api/admin_sources.py)

Added to existing admin_sources router (prefix /admin). Returns: id, name, adapter, kind, is_enabled, last_fetch_at, last_success_at, consecutive_failures. Never exposes sources.config or credentials (T-02-21). require_admin guard — returns 403 for trader/viewer, 401 for unauthenticated.

## Verification Results

- `pytest tests/test_source_health.py tests/test_source_failure_alert.py -q`: 19 passed, 10 skipped (live-DB), 0 failed
- `pytest -q` (full suite): 257 passed, 62 skipped, 0 failed — no regression
- `ruff check` on all 4 touched files: no issues
- `mypy` on all 4 touched files: no issues

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] save_raw_items promoted to module-level import for testability**
- **Found during:** Task 2 GREEN — test tried to patch `app.tasks.ingest.save_raw_items` but it was a local import inside the function
- **Issue:** Local import is not patchable from outside the function call frame
- **Fix:** Moved `save_raw_items` import to module-level in `ingest.py`
- **Files modified:** `backend/app/tasks/ingest.py`
- **Commit:** 5353d42

**2. [Rule 1 - Bug] Health endpoint test mocked rows as MagicMock objects instead of tuples**
- **Found during:** Task 2 GREEN — endpoint uses indexed row access (row[0], row[1]...) but test built MagicMock rows with attributes
- **Issue:** Pydantic validation errors when constructing SourceHealthItem from MagicMock fields
- **Fix:** Changed mock rows to tuples matching the indexed access pattern
- **Files modified:** `backend/tests/test_source_failure_alert.py`
- **Commit:** 5353d42

**3. [Rule 2 - Missing] errors list tracking removed from _execute_uzex_fetch**
- **Found during:** Task 2 GREEN — old errors list was populated in the old per-source try/except; after refactoring to run_source_fetch_isolated, the list is never populated but the status check `"partial_error"` remained
- **Fix:** Removed errors tracking from _execute_uzex_fetch; status is always "ok" since run_source_fetch_isolated never re-raises (failure state is in the DB via health service)
- **Files modified:** `backend/app/tasks/ingest.py`
- **Commit:** 5353d42

## Known Stubs

None — all functionality is wired end-to-end.

## Threat Flags

No new security-relevant surface beyond what was planned in the threat model. The GET /admin/sources/health endpoint is admin-gated and returns only health fields — sources.config is excluded (T-02-21 mitigated).

## TDD Gate Compliance

- RED gate (test commits): 3120200, 45b578b — tests written first and confirmed failing
- GREEN gate (feat commits): b88d5bc, 5353d42 — implementation made tests pass
- Gate compliance: PASSED

## Self-Check

Files exist:
- backend/app/services/source_health_service.py: FOUND
- backend/app/tasks/notify.py: FOUND
- backend/tests/test_source_health.py: FOUND
- backend/tests/test_source_failure_alert.py: FOUND

Commits exist:
- 3120200: FOUND
- b88d5bc: FOUND
- 45b578b: FOUND
- 5353d42: FOUND
