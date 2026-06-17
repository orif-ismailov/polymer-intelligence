---
phase: 03-client-circuit
plan: "06"
subsystem: testing
tags: [acceptance, sla, e2e, minio, performance, checkpoint, pytest, celery, notify]

# Dependency graph
requires:
  - phase: 03-02
    provides: request_service (create_request, transition_status, notify enqueue), /webapp requests API
  - phase: 03-03
    provides: send_status_change_notification notify task, bot webhook handler
  - phase: 03-05
    provides: my-requests UI, detail timeline, frontend build (42.8 KB gzip bundle)
provides:
  - "Automated SLA proxy tests: SC#1 create→readback <10 s, SC#3 immediate notify dispatch"
  - "Phase-3 acceptance doc mapping 5 ROADMAP success criteria to deploy-time live drill"
  - "User-approved deploy-time deferral of live SC#1–SC#5 drill with CI gate (4/4 PASS)"
affects: [phase-04, phase-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Automated-gate-now / live-drill-at-deploy split — same pattern as Phase-2 02-07"
    - "In-process mocked-DB proxy tests for SLA verification (CI-safe, no live infra)"
    - "Acceptance doc as deploy-time checklist with PASS/FAIL/recorded-value fields"

key-files:
  created:
    - backend/tests/test_request_sla.py
    - docs/phase-03-acceptance.md
  modified:
    - docs/phase-03-acceptance.md (added sign-off section + deferral prerequisites)

key-decisions:
  - "DEC-03-06-sla-gate: automated proxy tests (4/4 PASS) serve as CI gate; live wall-clock drill deferred to deploy time per user sign-off on 2026-06-17 (mirrors Phase-2 02-07 precedent)"
  - "DEC-03-06-deferral-prereqs: deploy-time drill requires real BOT_TOKEN, WEBHOOK_SECRET, public HTTPS PUBLIC_WEBAPP_URL, and alternate ports to avoid deploy-* collision"
  - "DEC-03-06-rolled-deferral: live UI verifications from 03-04 (wizard submit path) and 03-05 (list/detail/timeline/refetch) roll into the same deploy-time SC#1/SC#3 drill"

patterns-established:
  - "Proxy-test pattern: assert apply_async(queue='notify', no countdown/eta) to prove immediate dispatch without long sleep"
  - "Source-level sleep guard: inspect.getsource(notify_module) asserts no time.sleep() with constant > 1 s"

requirements-completed: [REQ-nfr-performance, REQ-request-wizard, REQ-my-requests, REQ-bot-clients]

# Metrics
duration: 25min (continuation finalization only — implementation was pre-committed)
completed: 2026-06-17
---

# Phase 03 Plan 06: E2E Acceptance + SLA Gate Summary

**Automated SLA proxy tests (4/4 PASS) prove synchronous request readback and immediate notify dispatch; Phase-3 acceptance doc maps all 5 ROADMAP criteria to a deploy-time drill; live SC#1–SC#5 drill user-approved for deferral to deploy time (BOT_TOKEN + HTTPS URL not provisioned in dev).**

## Performance

- **Duration:** 25 min (continuation finalization; full implementation pre-committed)
- **Started:** 2026-06-17T05:30:00Z
- **Completed:** 2026-06-17T06:00:00Z
- **Tasks:** 3 (Task 1 + Task 2 auto; Task 3 checkpoint resolved by user sign-off)
- **Files modified:** 3

## Accomplishments

- Task 1: Created `backend/tests/test_request_sla.py` with 4 in-process proxy tests (all PASS); full backend suite 384 passed, 65 skipped, no regressions.
- Task 2: Created `docs/phase-03-acceptance.md` mapping all 5 ROADMAP Phase-3 success criteria (SC#1–SC#5) to a deploy-time live drill with recorded-value fields; verified docker-compose.dev.yml (notify queue consumed, MinIO health-gated, all env vars flow — no changes required).
- Task 3: Checkpoint resolved — user signed off on automated SLA gate as the CI gate on 2026-06-17 and explicitly deferred the live SC#1–SC#5 deploy-time drill; deferral recorded in acceptance doc with prerequisites table.

## Task Commits

Each task was committed atomically:

1. **Task 1: Automated SLA proxy tests** — `d60e814` (test)
2. **Task 2: Acceptance doc + compose verification** — `393a31a` (feat)
3. **Task 3: Sign-off + deferral annotation** — included in plan metadata commit below

**Plan metadata:** _(this commit)_ (docs: complete E2E acceptance plan)

## Automated SLA Results (Task 1)

`backend/tests/test_request_sla.py` — 4 tests, all PASS:

| Test | What it asserts | Result |
|---|---|---|
| `test_request_readback_within_10s` | POST /webapp/requests → GET /webapp/requests elapsed < 10.0 s; created REQ number appears in list | PASS |
| `test_status_change_enqueues_notify_promptly` | `transition_status` calls `apply_async(queue="notify")` with no `countdown`/`eta` (immediate dispatch — ≤30 s budget is delivery-only) | PASS |
| `test_notify_task_no_long_sleep` | `inspect.getsource(notify_module)` contains no `time.sleep()` with constant > 1 s (defends ≤30 s budget) | PASS |
| Full backend suite | `python -m pytest -q` — 384 passed, 65 skipped, 0 failures | PASS |

## Files Created/Modified

- `backend/tests/test_request_sla.py` — 4 automated SLA proxy tests (SC#1 readback + SC#3 enqueue timing + sleep guard + full-suite smoke)
- `docs/phase-03-acceptance.md` — Created: 5 ROADMAP SC checklist with PASS/FAIL/recorded-value fields, TZ §6.1.1 citations, compose verification table; Updated: sign-off section with deferral decision, prerequisites table, automated CI gate results table

## Decisions Made

- **DEC-03-06-sla-gate:** Automated proxy tests (4/4 PASS) serve as CI gate; live wall-clock drill deferred to deploy time per user sign-off 2026-06-17. Mirrors Phase-2 02-07 precedent exactly.
- **DEC-03-06-deferral-prereqs:** Deploy-time drill requires: real `BOT_TOKEN` (from @BotFather), `WEBHOOK_SECRET`, public HTTPS `PUBLIC_WEBAPP_URL` (ngrok acceptable), alternate ports to avoid `deploy-*` collision.
- **DEC-03-06-rolled-deferral:** Live UI verifications from 03-04 (wizard submit → REQ-number → confirmation, deferred at 03-04 Task 3 checkpoint) and 03-05 (live my-requests list / detail status-history timeline / foreground-refetch on visibilitychange, deferred at 03-05 Task 3 checkpoint) are included in the same deploy-time SC#1/SC#3 drill.

## Deviations from Plan

None — plan executed exactly as written. Task 3 resolved via user sign-off (deferral approved), consistent with plan's stated option: "OR approves deferral to deploy time (with the automated proxies + build gates standing as the phase gate)."

## Issues Encountered

None. The compose verification confirmed all components already correct from 03-01..03-05: notify queue consumed (`-Q ingest,parse,notify,default`), MinIO health-gated before api, BOT_TOKEN/WEBHOOK_SECRET/PUBLIC_WEBAPP_URL/S3_* flow via `.env`, `polymer-files` bucket auto-created by `storage_service.ensure_bucket()`.

## SC Summary — Phase 3 Closure

| SC | ROADMAP Criterion | CI Gate | Live Drill |
|----|---|---|---|
| SC#1 | Request queryable ≤10 s (TZ §6.1.1) | `test_request_readback_within_10s` PASS | DEFERRED TO DEPLOY |
| SC#2 | Files → MinIO bucket, invalid files rejected | Storage validation tests PASS (13/13) | DEFERRED TO DEPLOY |
| SC#3 | Bot push ≤30 s (TZ §6.1.1) | `test_status_change_enqueues_notify_promptly` + sleep guard PASS | DEFERRED TO DEPLOY |
| SC#4 | RU/UZ toggle + Telegram theme + bundle ≤300 KB | Bundle measured 42.8 KB gzip (03-05 build) | Bundle PASS; theme/toggle DEFERRED |
| SC#5 | Bot greeting + notify queue routing | Webhook + notify task tests PASS (12/12) | DEFERRED TO DEPLOY |

## User Setup Required

At deploy time (when provisioning the live environment), follow `docs/phase-03-acceptance.md` to run the SC#1–SC#5 live drill. Prerequisites:

1. Real `BOT_TOKEN` from @BotFather
2. `WEBHOOK_SECRET` (random 32-char string)
3. Public HTTPS `PUBLIC_WEBAPP_URL` (ngrok or tunnel)
4. `docker compose -f deploy/docker-compose.dev.yml up -d` with `.env` filled
5. Alternate ports if a `deploy-*` stack is already running

## Next Phase Readiness

Phase 3 is complete. All implementation committed and CI green:
- Backend: `request_service` + `/webapp` API + initData auth + MinIO storage + notify task
- Bot: `/start` handler + RU/UZ greeting + Web App button + status push (D-10 labels + deep-link)
- Frontend: 4-step wizard + my-requests + detail/timeline + RU/UZ i18n + settings toggle + 42.8 KB gzip bundle
- Acceptance: automated SLA proxies green; live drill checklist ready for deploy time

Phase 4 (Dashboard + Source Constructor) can begin. It depends on `requests` data from Phase 3 and the `/webapp/requests` API for the Purchase Requests master-detail screen.

---
*Phase: 03-client-circuit*
*Completed: 2026-06-17*
