---
phase: 02-ingest-core-uzex
plan: "01"
subsystem: infra
tags: [celery, redis, kombu, beat-schedule, crontab, task-queue, ingest]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Settings/pydantic-settings pattern, REDIS_URL in config, docker-compose with worker+beat commands
provides:
  - "app.tasks package (backend/app/tasks/__init__.py)"
  - "celery_app Celery instance (app.tasks.celery_app:celery_app) with 4 queues, json-only serialization, Asia/Tashkent timezone"
  - "BEAT_SCHEDULE dict (app.tasks.schedule) with 5 crontab entries"
  - "Placeholder tasks for uzex_fetch_offers, uzex_fetch_contracts, uzex_fetch_deals, fetch_cbu_rates, check_source_health"
  - "INGEST_HTTP_TIMEOUT_SECONDS, INGEST_HTTP_RETRIES, INGEST_USER_AGENT, INGEST_PER_HOST_DELAY_SECONDS settings"
affects:
  - 02-02 (httpx client uses INGEST_* settings)
  - 02-03 (httpx ingest client)
  - 02-04 (UZEX fetchers replace placeholder tasks)
  - 02-05 (CBU rates task replaces placeholder)
  - 02-06 (health check task replaces placeholder)

# Tech tracking
tech-stack:
  added: []  # celery+kombu already in pyproject.toml; no new packages installed
  patterns:
    - "Celery autodiscover_tasks(['app.tasks']) for zero-config task registration"
    - "Placeholder task pattern: register contract task names pre-implementation so beat+worker boot cleanly"
    - "mypy overrides for celery/kombu (no py.typed) via [[tool.mypy.overrides]] ignore_missing_imports"
    - "Crontab assertions in tests use resolved sets (Celery 5.x stores minute/hour/day as frozensets)"

key-files:
  created:
    - backend/app/tasks/__init__.py
    - backend/app/tasks/celery_app.py
    - backend/app/tasks/schedule.py
    - backend/app/tasks/placeholders.py
    - backend/tests/test_celery_app.py
    - backend/tests/test_beat_schedule.py
  modified:
    - backend/app/core/config.py (added 4 INGEST_* fields)
    - backend/pyproject.toml (added celery/kombu mypy overrides)
    - .gitignore (added celerybeat-schedule)

key-decisions:
  - "json-only serialization (task_serializer=json, accept_content=[json]) enforced at Celery conf level to block pickle deserialization attacks (T-02-01)"
  - "task_acks_late=True + worker_prefetch_multiplier=1 for crash-safe task delivery (T-02-02 / REQ-nfr-reliability)"
  - "Placeholder task pattern: register 5 task names as thin logging stubs now; plans 02-04/05/06 overwrite with real bodies"
  - "Beat schedule imported into celery_app.conf at module bottom (after app instance created) to avoid circular import"
  - "mypy overrides for celery/* and kombu/* (ignore_missing_imports) added to pyproject.toml - celery has no py.typed marker"

patterns-established:
  - "Schedule-first: beat_schedule.py is the single source of truth for cron expressions; celery_app.py wires it in"
  - "Contract task names are string literals shared between schedule.py and placeholder/real task decorators — no magic, no dynamic lookup"

requirements-completed:
  - REQ-nfr-reliability
  - REQ-uzex-parser

# Metrics
duration: 7min
completed: 2026-06-15
---

# Phase 02 Plan 01: Celery App + Beat Schedule Summary

**Bootable Celery worker+beat with 4 named queues, Asia/Tashkent crontabs, json-only serialization, and placeholder task stubs closing Phase-1 SC#1 ModuleNotFoundError**

## Performance

- **Duration:** 7 min
- **Started:** 2026-06-15T12:05:49Z
- **Completed:** 2026-06-15T12:12:33Z
- **Tasks:** 2
- **Files modified:** 9 (6 created, 3 modified)

## Accomplishments

- Created `app.tasks.celery_app:celery_app` — the Celery application instance that the worker and beat containers reference via `celery -A app.tasks.celery_app worker/beat`. Fixes Phase-1 SC#1 (worker+beat crash-looped with ModuleNotFoundError).
- Wired 4 queues matching the existing compose `-Q ingest,parse,notify,default` flag, json-only serialization (T-02-01), task_acks_late + worker_prefetch_multiplier=1 (T-02-02/REQ-nfr-reliability), and Asia/Tashkent timezone.
- Defined BEAT_SCHEDULE with 5 Asia/Tashkent crontab entries (uzex_fetch_offers every 15 min business hours, contracts/deals hourly, cbu_rates daily at 07:00, health every 5 min) and registered placeholder task bodies under the 5 contract names so the worker boots cleanly before plans 02-04/05/06 implement the real bodies.
- Added 4 INGEST_* settings to `app.core.config.Settings` (timeout, retries, user-agent, per-host delay) for consumption by the httpx client in 02-03.
- 20 new tests all pass; full suite 125 passed, 17 skipped.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create the Celery application, queue topology, and ingest config keys** - `fe7292c` (feat)
2. **Task 2: Define the Asia/Tashkent beat schedule with crontab entries** - `d9a4b41` (feat)

## Files Created/Modified

- `backend/app/tasks/__init__.py` - Package init; imports placeholders for side-effect registration, re-exports celery_app
- `backend/app/tasks/celery_app.py` - Celery instance with 4 queues, timezone, serialization, routing, autodiscovery, beat_schedule
- `backend/app/tasks/schedule.py` - BEAT_SCHEDULE dict with 5 crontab entries
- `backend/app/tasks/placeholders.py` - 5 placeholder tasks registered under contract names (overwritten by 02-04/05/06)
- `backend/app/core/config.py` - Added INGEST_HTTP_TIMEOUT_SECONDS, INGEST_HTTP_RETRIES, INGEST_USER_AGENT, INGEST_PER_HOST_DELAY_SECONDS
- `backend/pyproject.toml` - Added celery/kombu mypy overrides (ignore_missing_imports)
- `backend/tests/test_celery_app.py` - 11 tests: queues, timezone, UTC, acks_late, prefetch, json-only, task_track_started, placeholder names
- `backend/tests/test_beat_schedule.py` - 9 tests: 5 keys, uzex_fetch_offers minute/hour/day_of_week, contracts/deals hourly, cbu_rates at 07:00, health every 5 min
- `.gitignore` - Added celerybeat-schedule (created by Celery during import)

## Decisions Made

- json-only serialization pinned at Celery conf level (not per-task) to close T-02-01 globally
- Placeholder task pattern chosen over empty task registry — worker+beat can boot and run the full beat cycle without NotRegistered errors even before implementing plans land
- Beat schedule imported at the bottom of celery_app.py (after `celery_app = Celery(...)` call) to avoid circular import since schedule.py does not import celery_app
- mypy `ignore_missing_imports` overrides for celery/* and kombu/* added to pyproject.toml (not inline type: ignore) to maintain single-source config

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test assertions for Celery 5.x crontab set representation**
- **Found during:** Task 2 (running test_beat_schedule.py)
- **Issue:** Tests asserted `str(sched.minute) == "*/15"` but Celery 5.x stores crontab fields as resolved frozensets (`{0, 15, 30, 45}`), not expression strings. 7 tests failed.
- **Fix:** Updated all test assertions to compare against the resolved set values (e.g., `sched.minute == {0, 15, 30, 45}`, `sched.hour == set(range(9, 19))`, `sched.day_of_week == {1, 2, 3, 4, 5}`)
- **Files modified:** backend/tests/test_beat_schedule.py
- **Verification:** All 20 tests pass after fix
- **Committed in:** d9a4b41 (Task 2 commit)

**2. [Rule 2 - Missing Critical] Added mypy overrides for celery/kombu (no py.typed)**
- **Found during:** Task 1 (mypy run)
- **Issue:** celery and kombu have no py.typed marker; mypy strict mode raised import-untyped errors
- **Fix:** Added `[[tool.mypy.overrides]]` for `celery`, `celery.*`, `kombu`, `kombu.*` with `ignore_missing_imports = true` in pyproject.toml. Also fixed `type: ignore[misc]` to `type: ignore[untyped-decorator]` in placeholders.py.
- **Files modified:** backend/pyproject.toml, backend/app/tasks/placeholders.py
- **Verification:** `mypy app/tasks` returns "Success: no issues found in 4 source files"
- **Committed in:** fe7292c / d9a4b41

---

**Total deviations:** 2 auto-fixed (1 Rule 1 bug in test assertions, 1 Rule 2 missing mypy config)
**Impact on plan:** Both auto-fixes necessary for test correctness and CI mypy gate. No scope creep.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## User Setup Required

None — no external service configuration required. The celerybeat-schedule file is gitignored.

## Next Phase Readiness

- `app.tasks.celery_app:celery_app` is fully importable; Phase-1 SC#1 (worker+beat ModuleNotFoundError) is resolved at the import layer.
- The 4-queue topology matches the existing compose `-Q` flag — worker+beat containers will start without ModuleNotFoundError.
- 5 beat task names are registered as placeholders; plans 02-04, 02-05, 02-06 can register real task bodies under the same names.
- `settings.INGEST_HTTP_*` fields are ready for the httpx client in 02-03.
- No blockers for 02-02 (storage models) or 02-03 (httpx client).

---
*Phase: 02-ingest-core-uzex*
*Completed: 2026-06-15*
