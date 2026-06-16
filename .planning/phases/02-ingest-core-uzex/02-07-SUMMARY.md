---
phase: 02-ingest-core-uzex
plan: "07"
subsystem: infra
tags: [celery, postgres, pg_dump, backup, seeder, accuracy-harness, reliability, uzex]

# Dependency graph
requires:
  - phase: 02-06
    provides: "source_health_service, failure isolation, check_source_health task, GET /admin/sources/health"
  - phase: 02-04
    provides: "UZEX adapters, raw_pipeline dedupe, uzex_fetch_* tasks"
  - phase: 02-05
    provides: "CBU rates adapter, rule-based parse_raw_item, create_signal_from_parse"
provides:
  - "worker/beat auto-restart (restart: unless-stopped) — REQ-nfr-reliability"
  - "deploy/backup/pg_backup.sh: pg_dump with 14-daily / 8-weekly retention + umask 077 (T-02-23)"
  - "deploy/backup/README.md: cron installation guide"
  - "docs/runbook-backup-restore.md: step-by-step restore procedure with ≤2h target (TZ §6.1.5)"
  - "backend/app/seed/data/sources_seed.json: UZEX offers/contracts/deals + cbu_rates rows (is_enabled=false)"
  - "backend/app/seed/seed_sources.py: idempotent ON CONFLICT DO NOTHING seeder (T-02-24)"
  - "backend/tests/test_uzex_accuracy.py: ≥95% field-accuracy gate on ≥50 positions (TZ §6.1.2)"
  - "backend/tests/fixtures/uzex/control_sample.json: 55-position control sample with expected parsed values"
affects:
  - phase-06-acceptance-handover  # restore-doc walkthrough and TZ §6.1 acceptance items

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "pg_dump -Fc timestamped with umask 077 to non-public dir; retention via find -mtime (T-02-23 mitigation)"
    - "Seeder: ON CONFLICT (adapter, name) DO NOTHING — idempotent, is_enabled=false until test passes (T-02-24)"
    - "Accuracy gate: field-level correct/total across ≥50 positions; per-field breakdown on failure; threshold ≥0.95"

key-files:
  created:
    - deploy/backup/pg_backup.sh
    - deploy/backup/README.md
    - docs/runbook-backup-restore.md
    - backend/app/seed/data/sources_seed.json
    - backend/app/seed/seed_sources.py
    - backend/tests/test_seed_sources.py
    - backend/tests/test_uzex_accuracy.py
    - backend/tests/fixtures/uzex/control_sample.json
  modified:
    - deploy/docker-compose.dev.yml
    - backend/app/services/signal_service.py  # Rule-1 bug fix: comma-decimal price parsing
    - backend/app/ingest/uzex/adapters.py      # Rule-1 bug fix: section_label="deals" for UzexDealsAdapter

key-decisions:
  - "pg_backup.sh uses umask 077 + chmod 600 on dump files — closes T-02-23 (info-disclosure on world-readable backups)"
  - "seed_sources: is_enabled=false + last_test_ok_at=NULL invariant enforced at seed time and verified in test — closes T-02-24"
  - "Accuracy harness uses pure-function path (parse_table_rows + create_signal_from_parse) with live-DB guard; no real DB needed for the accuracy assertion"
  - "signal_service: comma-decimal price strings (e.g. '12,500') parsed by replacing comma before float() cast (Rule-1 auto-fix)"
  - "UzexDealsAdapter: section_label corrected to 'deals' so deals rows are stored with the right kind (Rule-1 auto-fix)"
  - "Live end-to-end docker drill (SC#5 live failure-isolation) deferred to deploy time — user approved; automated gate (pytest accuracy + sh -n backup + compose restart policy) passed"

patterns-established:
  - "Backup: pg_dump -Fc with umask 077, retention via find -mtime, cron-installable"
  - "Source seeder: mirrors seed_reference.py pattern — ON CONFLICT DO NOTHING, __main__ runnable"
  - "Accuracy gate: fixture-driven, per-field breakdown on failure, threshold constant 0.95 makes grep-checking the gate trivial"

requirements-completed:
  - REQ-nfr-reliability
  - REQ-uzex-parser

# Metrics
duration: "~35min (Tasks 1+2 executed prior session; finalization 2026-06-16)"
completed: "2026-06-16"
---

# Phase 02 Plan 07: Reliability Hardening + Accuracy Closure Summary

**Worker/beat auto-restart, pg_dump backup with ≤2h restore runbook, UZEX/CBU source seeder (disabled until tested), and a 55-position accuracy harness that enforces the TZ §6.1.2 ≥95% gate — phase-2 acceptance closure.**

## Performance

- **Duration:** ~35 min (Tasks 1+2 prior session; finalization 2026-06-16)
- **Started:** 2026-06-15 (tasks execution)
- **Completed:** 2026-06-16
- **Tasks:** 2 of 3 executed (Task 3 = checkpoint deferred, see below)
- **Files modified:** 12

## Accomplishments

- Worker and beat services carry `restart: unless-stopped` — persistent crash loops surface via the 3-strike source_failure alert rather than silent ingest stoppage (REQ-nfr-reliability / T-02-25)
- `deploy/backup/pg_backup.sh` ships pg_dump -Fc with umask 077 (T-02-23), 14-daily / 8-weekly retention pruning, and `docs/runbook-backup-restore.md` documents the step-by-step restore with the ≤2h target (TZ §6.1.5)
- UZEX offers/contracts/deals and CBU rates source rows seeded via idempotent `seed_sources.py`; all rows land with `is_enabled=false` + `last_test_ok_at IS NULL` (enable-after-test invariant, T-02-24)
- 55-position accuracy harness (`test_uzex_accuracy.py` + `control_sample.json`) gates on ≥0.95 field accuracy, prints per-field breakdown on failure; automated run: **100% accuracy on 55 positions — TZ §6.1.2 PASS** (full suite: 285 passed / 65 skipped / 0 failures)
- Two Rule-1 bug fixes landed automatically: comma-decimal price parsing in `signal_service.py` and `section_label="deals"` in `UzexDealsAdapter` (both required for the accuracy harness to reach ≥95%)

## Task Commits

1. **Task 1: Worker auto-restart, pg_dump backup script, restore runbook, UZEX/CBU source seeder** — `6c6e224` (feat)
2. **Task 2: End-to-end UZEX accuracy harness — ≥95% field accuracy on 55 positions + 2 Rule-1 bug fixes** — `961b706` (feat)
3. **Task 3: Live end-to-end human-verify checkpoint** — DEFERRED to deploy time (user-approved; see "Deferred" section below)

## Files Created/Modified

- `deploy/docker-compose.dev.yml` — confirmed worker/beat `restart: unless-stopped` (6 total restart: policies in compose)
- `deploy/backup/pg_backup.sh` — pg_dump -Fc, timestamped, umask 077, 14-daily/8-weekly retention
- `deploy/backup/README.md` — cron installation guide for daily backup
- `docs/runbook-backup-restore.md` — step-by-step restore (create DB, pg_restore, run entrypoint, re-seed), ≤2h target, 14d/8wk policy
- `backend/app/seed/data/sources_seed.json` — 4 source rows: uzex_offers, uzex_contracts, uzex_deals, cbu_rates (all is_enabled=false)
- `backend/app/seed/seed_sources.py` — idempotent seeder with ON CONFLICT (adapter, name) DO NOTHING
- `backend/tests/test_seed_sources.py` — idempotency + invariant (is_enabled=false, last_test_ok_at IS NULL) tests
- `backend/tests/test_uzex_accuracy.py` — field-accuracy harness, ≥0.95 threshold, per-field breakdown on failure
- `backend/tests/fixtures/uzex/control_sample.json` — 55 UZEX positions with raw payload + expected parsed values
- `backend/app/services/signal_service.py` — Rule-1 fix: comma-decimal price string parsing
- `backend/app/ingest/uzex/adapters.py` — Rule-1 fix: UzexDealsAdapter `section_label="deals"`

## Decisions Made

- `pg_backup.sh` uses `umask 077` + `chmod 600` on dump files, writes to a non-public directory — closes T-02-23 (information disclosure via world-readable backup files)
- Seeder: `is_enabled=false` + `last_test_ok_at=NULL` at seed time, enforced in test — closes T-02-24 (source enabled before passing test)
- Accuracy harness runs the same pure-function parse path (`parse_table_rows` → `create_signal_from_parse`) as the live pipeline; no DB required, live-DB guard in place — makes the gate reproducible in CI without a running database
- Live end-to-end docker drill deferred to deploy time with user approval (see "Deferred" section)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed comma-decimal price string parsing in signal_service**
- **Found during:** Task 2 (accuracy harness development)
- **Issue:** UZEX price cells contain comma as thousands separator (e.g. `'12,500'`); `float('12,500')` raises ValueError, causing price fields to be None and dropping accuracy below 95%
- **Fix:** Added `.replace(',', '')` before float cast in `signal_service.py` price normalization
- **Files modified:** `backend/app/services/signal_service.py`
- **Verification:** Accuracy harness reached 100% on 55 positions; full suite 285 passed / 0 failures
- **Committed in:** `961b706` (Task 2 commit)

**2. [Rule 1 - Bug] Fixed UzexDealsAdapter section_label**
- **Found during:** Task 2 (accuracy harness development)
- **Issue:** `UzexDealsAdapter.section_label` was set to `"concluded_deals"` but the raw_items kind field expected `"deals"`, causing kind mismatch on all deals positions (accuracy below threshold)
- **Fix:** Changed `section_label` to `"deals"` in `backend/app/ingest/uzex/adapters.py`
- **Files modified:** `backend/app/ingest/uzex/adapters.py`
- **Verification:** Accuracy harness reached 100% on 55 positions; full suite 285 passed / 0 failures
- **Committed in:** `961b706` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 × Rule 1 - Bug)
**Impact on plan:** Both fixes were required for the accuracy gate to pass. Without them field accuracy was below 95%. No scope creep.

## Deferred / Human-verify at Deploy Time

**Status:** User-approved deferral. The automated acceptance gate (pytest + sh -n + compose restart-policy grep) passed. The live docker-compose walkthrough is deferred to deployment time.

**What is deferred:** Task 3 checkpoint — live end-to-end drill against a running `docker compose up` stack (SC#5 live failure-isolation evidence):

1. `docker compose -f deploy/docker-compose.dev.yml up` — confirm worker and beat stay up (no crash-loop); `docker compose ps` shows worker/beat healthy
2. Trigger `uzex_fetch_offers` manually via `docker compose exec worker celery ...`; confirm raw_items rows appear and parse_raw_item produces signals; spot-check a few signals rows for correct product/volume/price/currency
3. Re-run the same fetch; confirm NO duplicate raw_items (sha256 dedupe, SC#2)
4. Verify `fx_rates` populated by `fetch_cbu_rates`; confirm converted figure computed alongside original (SC#3)
5. **SC#5 failure-isolation drill:** point one source at an unreachable URL, force 3 fetch cycles (or run `check_source_health` after 3 failures), confirm exactly one `source_failure` alert appears AND other sources kept producing data; confirm alert appears within the 30-min window
6. Restore-doc walkthrough: read `docs/runbook-backup-restore.md`, confirm procedure is followable and states the ≤2h target; optionally run `deploy/backup/pg_backup.sh` and confirm a dump file is produced

**Resume signal:** Reply "approved" after confirming all 6 steps pass on the live stack.

**Traceability:** This UAT item maps to SC#5 (TZ §6.1.4 — one source failing, alert within 30 min, others keep running) and SC#1 carryover (worker/beat stay up).

## Issues Encountered

None beyond the two Rule-1 auto-fixes above. Both were identified and resolved during Task 2 before the accuracy harness was committed.

## User Setup Required

None — no new external services or environment variables introduced. The backup script is parameterized from existing `PGHOST`/`PGUSER`/`PGDATABASE` env vars already required by the app. Cron installation instructions are in `deploy/backup/README.md`.

## Next Phase Readiness

Phase 2 (Ingest Core + UZEX) is execution-complete:
- All 7 plans executed
- Automated acceptance gate: 100% field accuracy on 55 positions (TZ §6.1.2 PASS)
- Full test suite: 285 passed / 65 skipped / 0 failures
- Reliability: worker/beat auto-restart, pg_dump backup + restore runbook in place
- Sources: UZEX + CBU rows seeded (disabled until tested, invariant enforced)
- Deferred live drill: recorded above, surfaces in /gsd-progress and /gsd-audit-uat

**Phase 3 (Client Circuit) can begin.** Key handoffs from Phase 2:
- `SourceAdapter` Protocol + registry fully established — Phase 3's aiogram bot and request submission use the same adapter infrastructure
- `fx_rates` table populated, on-read conversion pattern established
- `sources.config` as the selector store (no CSS literals in adapters.py) — maintainable for Phase 4 no-code source constructor

**Remaining concern:** The live SC#5 failure-isolation drill (deferred above) is the only unverified acceptance item in Phase 2. It should be completed at the earliest practical deploy-time opportunity before the Phase 6 acceptance run.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| 02-07-SUMMARY.md | FOUND |
| Commit 79d5d87 (SUMMARY) | FOUND |
| Commit ea684c9 (STATE/ROADMAP) | FOUND |
| Commit 961b706 (Task 2) | FOUND |
| Commit 6c6e224 (Task 1) | FOUND |

---
*Phase: 02-ingest-core-uzex*
*Completed: 2026-06-16*
