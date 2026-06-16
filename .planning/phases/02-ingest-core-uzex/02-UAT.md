---
status: deferred
phase: 02-ingest-core-uzex
source: [02-VERIFICATION.md]
deferral: deploy-time — user-approved at 02-07 execute-phase checkpoint (2026-06-16)
started: 2026-06-16T08:00:00Z
updated: 2026-06-16T08:00:00Z
---

# Phase 02 — Deferred Deploy-Time UAT

These 3 live-stack drills require a running `docker compose` stack with live UZEX/CBU
network access. At the 02-07 execute-phase checkpoint the user elected to accept Phase 2
on the passing automated acceptance gate (≥95% accuracy = **100%** on a 55-position control
sample; 289 backend tests green; statically-verified reliability artifacts) and DEFER these
live drills to deployment. Run them at deploy time, then mark each result and re-run
`/gsd-verify-work 2` (or `/gsd-audit-uat`) to close them out.

## Current Test

number: 1
name: Live end-to-end ingest drill (SC#1, SC#2, SC#3)
expected: |
  Signals exist with correct fields; second identical fetch adds 0 raw_items (sha256 dedupe);
  fx_rates has today's CBU rates; convert_amount returns the UZS-converted figure alongside
  the preserved original.
awaiting: deploy-time execution

## Tests

### 1. Live end-to-end ingest drill (SC#1 / SC#2 / SC#3)
expected: |
  `docker compose -f deploy/docker-compose.dev.yml up` → worker + beat start and STAY up
  (no crash-loop). Test-enable a UZEX source, `celery -A app.tasks.celery_app call
  uzex_fetch_offers` → raw_items + correct signals appear (spot-check product/volume/price/
  currency/kind). Re-run the same fetch → 0 new raw_items (sha256 dedupe, SC#2).
  `celery ... call fetch_cbu_rates` → fx_rates populated; convert_amount returns a converted
  figure with the original preserved (SC#3).
result: [pending]

### 2. 3-strike alert isolation drill (SC#5)
expected: |
  Point one source at an unreachable URL, force 3 fetch cycles (or run check_source_health
  after 3 recorded failures) → exactly one source_failure alert (dedupe_key
  source_failure:{source_id}:{date}); sibling sources keep producing data (isolation);
  alert appears within the 30-min window (the */5 check_source_health task). A subsequent
  success resets consecutive_failures to 0.
result: [pending]

### 3. Restore-doc walkthrough (REQ-nfr-reliability)
expected: |
  Read docs/runbook-backup-restore.md top-to-bottom: procedure is complete and followable
  (clean DB → pg_restore → alembic upgrade head → re-seed), states the ≤2h restore target,
  and documents 14-daily / 8-weekly retention. Optionally run deploy/backup/pg_backup.sh once
  and confirm a timestamped .pgdump file is produced.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps

None outstanding at code level — all 5 success criteria verified in 02-VERIFICATION.md
(SC#4 'irrelevant' status fixed in be14a26). These 3 items are live-runtime confirmations
deferred to deploy time by user approval, not gaps.
