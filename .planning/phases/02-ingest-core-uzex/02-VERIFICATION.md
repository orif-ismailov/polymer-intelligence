---
phase: 02-ingest-core-uzex
verified: 2026-06-16T00:00:00Z
status: passed
score: 5/5
overrides_applied: 1
re_verified: 2026-06-16T08:00:00Z
gaps: []
resolved_gaps:
  - truth: "non-polymer rows land as raw_items status='irrelevant'"
    was: partial
    resolved_by: "be14a26"
    note: |
      SC#4 gap fixed after initial verification. parse_raw_item now sets
      parse_status='irrelevant' on the no-match branch (dev-spec §2.1 + ROADMAP SC#4;
      the weekly irrelevant-goods report keys on this status), while still queuing the
      row for manual classification so the synonyms dictionary can be topped up. The
      two weakened tests were tightened to assert == 'irrelevant'. Full suite 289 passed.
overrides:
  - scope: "human_verification (3 live-stack drills)"
    applied: 2026-06-16
    authorized_by: "user (orifismailov08@gmail.com) via execute-phase checkpoint"
    rationale: |
      The 3 human-verification items below are LIVE docker-compose drills that cannot run
      without a deployed stack + live UZEX/CBU network access. At the 02-07 checkpoint the
      user explicitly chose to accept the phase on the passing automated acceptance gate
      (≥95% accuracy = 100% on 55 positions; 289 tests green; statically-verified reliability
      artifacts) and DEFER the live drill to deploy time. These items are persisted as a
      deferred deploy-time UAT (02-UAT.md) and tracked in STATE.md Deferred Items so they
      surface in /gsd-progress and /gsd-audit-uat. Code-level mechanisms for all 5 SCs are
      VERIFIED; only the live runtime confirmation is deferred.
human_verification:
  - test: "Live end-to-end drill: bring up stack, trigger uzex_fetch_offers, confirm raw_items and
      signals appear, re-run and confirm 0 duplicates, trigger fetch_cbu_rates and verify fx_rates
      populated, check convert_amount returns UZS-converted figure via a test query"
    expected: "Signals exist with correct fields; second fetch adds 0 rows; fx_rates has today's
      CBU rates; convert_amount(100, 'USD', today) == 100 * rate"
    why_human: "Requires live docker-compose stack with live UZEX/CBU internet access; cannot verify
      without network and running containers"
  - test: "3-strike alert isolation drill: point one source at an invalid URL, force 3 fetch cycles
      (or run check_source_health after 3 DB-recorded failures), confirm exactly one source_failure
      alert created, confirm sibling sources still succeeded"
    expected: "alerts table has one row with dedupe_key source_failure:{source_id}:{date};
      sibling sources have last_success_at updated; consecutive_failures reset to 0 after a success"
    why_human: "Requires live worker/beat stack to verify real-time isolation and alerting loop;
      unit tests cover this with mocks, but SC#5 ≤30 min window needs end-to-end confirmation"
  - test: "Restore-doc walkthrough: read docs/runbook-backup-restore.md and confirm procedure is
      complete, followable, and states the ≤2h target; optionally run deploy/backup/pg_backup.sh
      once and confirm a .pgdump file is created"
    expected: "Runbook has step-by-step pg_restore sequence; ≤2h target appears in §5; backup
      script runs without error and writes a timestamped .pgdump file"
    why_human: "pg_dump execution and restore walkthrough quality require a human to read and
      judge completeness; syntax check (sh -n) passes but runtime verification needs a DBA review"
---

# Phase 02: Ingest Core + UZEX — Verification Report

**Phase Goal:** Real UZEX polymer signals and FX rates flow into the database through an immutable, deduplicated, reproducible pipeline whose health is observable and whose failures alert without stopping other sources.
**Verified:** 2026-06-16T00:00:00Z (initial), 2026-06-16T08:00:00Z (re-verified after SC#4 fix)
**Status:** passed — 5/5 automated criteria met; 3 live-stack drills deferred to deploy-time UAT per explicit user approval
**Re-verification:** Yes — SC#4 gap fixed in `be14a26`

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Polymer positions appear in `signals` with correct fields; ≥95% field accuracy on ≥50-position control sample (TZ §6.1.2) | VERIFIED | `test_uzex_accuracy.py` passes: 12/12 assertions, 55-position control sample; `backend/tests/fixtures/uzex/control_sample.json` has 55 entries. Test suite: 289 passed, 0 failed. |
| 2 | UZEX offers/quotations/deals fetched on beat schedule; re-runs create zero duplicates (sha256 dedupe, ON CONFLICT DO NOTHING); raw data stored immutably before parsing | VERIFIED | `save_raw_items` uses `INSERT ... ON CONFLICT (source_id, content_hash) DO NOTHING RETURNING id`. `compute_content_hash` is deterministic SHA-256. Beat schedule in `schedule.py`: `uzex_fetch_offers` at `*/15 9-18 * * mon-fri`, contracts/deals at `crontab(minute=0)`. `raw_pipeline.py` never issues UPDATE on content/payload. |
| 3 | Daily CBU rate imports into `fx_rates`; convert_amount computes the UZS figure on read; original currency/amount preserved (never stored converted) | VERIFIED | `upsert_fx_rates` uses `ON CONFLICT (rate_date, ccy) DO UPDATE SET rate`. `convert_amount` is SELECT-only (no writes). `fetch_cbu_rates` Celery task in `ingest_cbu.py` registered as `name="fetch_cbu_rates"`. Tests: `test_cbu_rates.py` + `test_fx_conversion.py` pass (65 passed/skipped, 0 failed). Display-in-UI portion deferred to Phase 4 dashboard — service layer is complete and callable. |
| 4 | SourceAdapter registry exists (fetch/test/config_schema); synonyms dictionary drives relevance and is admin-top-up-able; non-polymer rows land as `raw_items` status='irrelevant' | VERIFIED | Registry: `register_adapter/get_adapter/list_adapters` in `registry.py`, three UZEX adapters + CBU registered; `GET /admin/source-types` admin-guarded. Synonyms admin-top-up-able: `match_product` queries DB on every call (no module cache). **SC#4 gap resolved (`be14a26`):** parse_raw_item now sets `parse_status='irrelevant'` on the no-match branch (+ still queues for manual classification); tests tightened to assert `== 'irrelevant'`. |
| 5 | One source failing 3 consecutive cycles raises source_failure alert within 30 min; other collectors keep running; success resets counter | VERIFIED (code-level) | `source_health_service.py`: `record_fetch_failure` increments `consecutive_failures` and calls `raise_source_failure_alert` at count ≥ 3. Alert uses `ON CONFLICT (dedupe_key) DO NOTHING`. `check_source_health` on `*/5` beat provides ≤5 min safety net. `run_source_fetch_isolated` in `ingest.py` wraps each source in try/except, never re-raises. `record_fetch_success` zeroes `consecutive_failures`. Tests pass. Live-stack confirmation is human_needed. |

**Score:** 5/5 truths verified (SC#4 'irrelevant' status fixed in `be14a26`). Live-stack runtime confirmation for SC#1/2/3/5 is deferred to deploy-time UAT per user approval.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/tasks/celery_app.py` | Celery app wired to Redis, 4 queues, Asia/Tashkent | VERIFIED | Lines 31-89; queues: ingest/parse/notify/default; timezone: Asia/Tashkent; task_acks_late=True; json-only serialization; autodiscover_tasks |
| `backend/app/tasks/schedule.py` | Beat schedule with 5 entries and correct crontabs | VERIFIED | All 5 keys: uzex_fetch_offers (*/15 9-18 mon-fri), contracts/deals (hourly), fetch_cbu_rates (0 7), check_source_health (*/5) |
| `backend/alembic/versions/0002_synonyms_and_classification_queue.py` | Migration with down_revision='0001' | VERIFIED | revision="0002", down_revision="0001"; creates product_synonyms + manual_classification_queue |
| `backend/app/models/reference.py` | ProductSynonym + ManualClassificationItem ORM models | VERIFIED | Both classes present; registered in `__init__.py` |
| `backend/app/services/relevance_service.py` | match_product + queue_for_classification | VERIFIED | normalize_term, match_product (no cache), queue_for_classification with ON CONFLICT DO NOTHING |
| `backend/app/ingest/base.py` | SourceAdapter Protocol + RawItemDraft + TestResult | VERIFIED | runtime_checkable Protocol; TestResult enforces 10-row cap in __post_init__ |
| `backend/app/ingest/registry.py` | register_adapter/get_adapter/list_adapters | VERIFIED | Module-level dict; duplicate check on register; KeyError on unknown |
| `backend/app/ingest/http_client.py` | fetch_url with SSRF guard, timeout, retries, size cap | VERIFIED | follow_redirects=False (CR-01 fix); _SSRF_BLOCKED_NETWORKS includes 100.64.0.0/10 (CR-02 fix); 30s timeout; exponential backoff; 25 MB body cap |
| `backend/app/api/admin_sources.py` | GET /admin/source-types + GET /admin/sources/health | VERIFIED | Both endpoints present; require_admin guard; list_adapters() used; health returns id/name/adapter/kind/is_enabled/last_fetch_at/last_success_at/consecutive_failures |
| `backend/app/ingest/uzex/adapters.py` | UzexOffersAdapter, UzexContractsAdapter, UzexDealsAdapter | VERIFIED | All three registered; fetch_url called for outbound requests; config-driven selectors |
| `backend/app/services/raw_pipeline.py` | save_raw_items with sha256 dedupe + RETURNING id | VERIFIED | ON CONFLICT DO NOTHING; RETURNING id (CR-04 fix); never issues UPDATE; returns tuple[int, list[int]] |
| `backend/app/tasks/ingest.py` | Real uzex_fetch_* tasks (no placeholders) | VERIFIED | Registered as @celery_app.task(name="uzex_fetch_*"); uses run_source_fetch_isolated; `placeholders.py` deleted (CR-03 fix) |
| `backend/app/ingest/cbu_rates/adapter.py` | CbuRatesAdapter (type_name=cbu_rates) | VERIFIED | fetch_url for outbound; CbuRatesAdapter registered |
| `backend/app/services/fx_service.py` | upsert_fx_rates + convert_amount | VERIFIED | upsert uses ON CONFLICT DO UPDATE; convert_amount is SELECT-only; Decimal math throughout |
| `backend/app/tasks/parse.py` | parse_raw_item Celery task | VERIFIED | Registered; polymer path → 'parsed'; no-match → 'irrelevant' (+ manual_classification_queue) per `be14a26`; parse_runs with model=NULL |
| `backend/app/services/source_health_service.py` | record_fetch_success/failure + check_all_sources_health | VERIFIED | UTC date fix (WR-01); alert dedupe_key source_failure:{id}:{date}; ON CONFLICT DO NOTHING |
| `backend/app/tasks/notify.py` | Real check_source_health task | VERIFIED | Registered as name="check_source_health"; calls check_all_sources_health; no placeholder strings |
| `backend/tests/fixtures/uzex/control_sample.json` | ≥50 positions with raw + expected fields | VERIFIED | 55 positions; covers offers/contracts/deals sections |
| `backend/tests/test_uzex_accuracy.py` | Accuracy harness asserting ≥0.95 | VERIFIED | assert overall >= 0.95 at line 314; passes with 12/12 tests |
| `deploy/backup/pg_backup.sh` | pg_dump script with 14-daily/8-weekly retention | VERIFIED | sh -n syntax clean; pg_dump present; DAILY_KEEP referenced 6 times |
| `docs/runbook-backup-restore.md` | Written restore procedure + ≤2h target + retention policy | VERIFIED | ≤2h target in §5; 14 daily / 8 weekly in §1; step-by-step pg_restore procedure |
| `backend/app/seed/seed_sources.py` | Idempotent UZEX + CBU source seeder | VERIFIED | INSERT WHERE NOT EXISTS pattern; is_enabled=false; last_test_ok_at=NULL invariant |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `deploy/docker-compose.dev.yml` | `app.tasks.celery_app` | celery -A command | VERIFIED | worker/beat services use `celery -A app.tasks.celery_app worker/beat`; 6 `restart: unless-stopped` policies confirmed |
| `backend/app/tasks/celery_app.py` | `settings.REDIS_URL` | broker_url/result_backend | VERIFIED | `broker_url=settings.REDIS_URL, result_backend=settings.REDIS_URL` |
| `backend/app/services/relevance_service.py` | `product_synonyms` table | SELECT against synonym_norm | VERIFIED | SQL with `:norm` bound parameter; no module-level cache |
| `backend/app/services/fx_service.py` | `fx_rates` table | ON CONFLICT (rate_date, ccy) | VERIFIED | upsert confirmed; convert_amount SELECT only |
| `backend/app/ingest/uzex/adapters.py` | `backend/app/ingest/http_client.py` | fetch_url for outbound | VERIFIED | fetch_url imported and called; no direct httpx.get |
| `backend/app/services/raw_pipeline.py` | `raw_items uq_raw_items_source_content` | ON CONFLICT (source_id, content_hash) | VERIFIED | Exact constraint name in SQL; RETURNING id present |
| `backend/app/tasks/ingest.py` | `backend/app/services/source_health_service.py` | record_fetch_success/failure | VERIFIED | Both imported at module level; called in run_source_fetch_isolated |
| `backend/app/api/admin_sources.py` | `backend/app/ingest/registry.py` | list_adapters() | VERIFIED | `from app.ingest.registry import list_adapters` at top of file |
| `backend/app/tasks/parse.py` | `backend/app/services/relevance_service.py` | match_product | VERIFIED | Imported and called per raw_item_id; wrapper at line 63 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `parse.py:parse_raw_item` | `raw_item.payload` | raw_items DB row via session.get | Yes — DB-backed via save_raw_items | FLOWING |
| `fx_service.py:convert_amount` | `rate` | SELECT FROM fx_rates WHERE rate_date <= on_date | Yes — DB-backed | FLOWING |
| `source_health_service.py:record_fetch_failure` | `consecutive_failures` | UPDATE sources RETURNING consecutive_failures | Yes — DB-backed | FLOWING |
| `admin_sources.py:get_sources_health` | `rows` from sources table | SELECT id,name,adapter,kind,is_enabled,... FROM sources | Yes — DB-backed | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Accuracy harness ≥95% on 55-position sample | `cd backend && .venv/bin/python -m pytest tests/test_uzex_accuracy.py -q` | 12 passed | PASS |
| Core infrastructure (Celery, SSRF, registry, admin endpoint) | `cd backend && .venv/bin/python -m pytest tests/test_celery_app.py tests/test_beat_schedule.py tests/test_adapter_registry.py tests/test_http_client_ssrf.py tests/test_admin_source_types.py -q` | 70 passed | PASS |
| Health, raw pipeline, parse, CBU, FX | `cd backend && .venv/bin/python -m pytest tests/test_source_health.py tests/test_source_failure_alert.py tests/test_raw_pipeline_dedupe.py tests/test_parse_raw_item.py tests/test_cbu_rates.py tests/test_fx_conversion.py -q` | 60 passed, 23 skipped | PASS |
| Full test suite | `cd backend && .venv/bin/python -m pytest -q` | 289 passed, 65 skipped, 0 failed | PASS |
| Backup script syntax | `sh -n deploy/backup/pg_backup.sh` | syntax ok | PASS |
| No placeholder stubs remaining | `grep not_yet_implemented backend/app/tasks/*.py` | empty output | PASS |
| SSRF guard: follow_redirects=False | `grep follow_redirects backend/app/ingest/http_client.py` | `follow_redirects=False` at line 214 | PASS |
| SSRF guard: RFC 6598 CGNAT blocked | `grep 100.64 backend/app/ingest/http_client.py` | `_SSRF_BLOCKED_NETWORKS` includes `100.64.0.0/10` | PASS |
| 'irrelevant' parse_status used in parse.py | `grep irrelevant backend/app/tasks/parse.py` | `raw_item.parse_status = "irrelevant"` set on no-match branch (`be14a26`) | PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes declared or conventional. Step 7c: SKIPPED.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| REQ-uzex-parser | 02-01, 02-02, 02-04, 02-05, 02-07 | UZEX fetch + parse pipeline; ≥95% accuracy; polymer→signals, others→irrelevant, unknown→queue | SATISFIED | All mechanisms exist; accuracy gate passes (100%); no-match rows now set status='irrelevant' (`be14a26`) + queued for classification |
| REQ-fx-rates | 02-05 | Daily CBU import; on-read conversion; original preserved | SATISFIED | upsert_fx_rates + convert_amount implemented and tested; fetch_cbu_rates task registered |
| REQ-sources-health | 02-03, 02-06 | Source state: last fetch, consecutive failures, enable/disable; GET /admin/sources/health | SATISFIED | Endpoint present; admin-guarded; exposes last_fetch_at, last_success_at, consecutive_failures, is_enabled |
| REQ-nfr-reliability | 02-01, 02-06, 02-07 | Worker auto-restart; daily pg_dump 14d + weekly 8wk; restore ≤2h; failure isolation; alert ≤30 min | SATISFIED | 6x restart:unless-stopped in compose; pg_backup.sh with retention; runbook with ≤2h target; run_source_fetch_isolated isolation; check_source_health */5 beat |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/app/tasks/parse.py` | (whole file) | ~~'irrelevant' ParseStatus never set~~ | RESOLVED | Fixed in `be14a26` — no-match branch now sets 'irrelevant' |
| `backend/app/tasks/ingest.py` | 55 | `sa.text("adapter = :adapter AND is_enabled = true")` in ORM filter | Info | IN-01 from code review: fragile pattern, column-name not validated by ORM. No functional impact. |
| `backend/app/tasks/ingest.py` | 193-199 | `"errors": []` always empty in return dict | Info | IN-02 from code review: cosmetic misleading API surface, no functional impact |

No `TBD`, `FIXME`, or `XXX` debt markers found in any phase-modified file.

### Human Verification Required

#### 1. Live End-to-End Ingest Drill (SC#1, SC#2, SC#3)

**Test:** Bring up `docker compose -f deploy/docker-compose.dev.yml up`. Trigger `uzex_fetch_offers` manually against a test-enabled UZEX source. Confirm `raw_items` rows appear and `parse_raw_item` produces `signals` rows. Spot-check 5 signals rows for correct product/volume/price/currency/kind. Re-run the fetch and confirm zero new `raw_items` added (sha256 dedupe). Trigger `fetch_cbu_rates` and confirm `fx_rates` has today's CBU rates. Run `SELECT convert_amount(100, 'USD', CURRENT_DATE)` equivalent to confirm Decimal math works.

**Expected:** Signals exist with correct fields (product_id, grade_text, volume, price, currency, kind, event_at); second fetch shows `skipped=N, inserted=0`; fx_rates has rows for USD/CNY/RUB with today's rate_date; conversion returns non-null Decimal.

**Why human:** Requires live stack with network access to uzex.uz and cbu.uz; cannot verify without running containers and real HTTP fetches.

---

#### 2. 3-Strike Alert Isolation Drill (SC#5)

**Test:** Point one seeded source at an unreachable URL (modify sources.config endpoint in DB). Force 3 fetch cycles via `docker compose exec worker celery call uzex_fetch_offers` (or wait for beat). Confirm: (a) exactly one alert in `alerts` table with `dedupe_key = source_failure:{id}:{today}`, (b) sibling sources still have `last_success_at` updated (isolation), (c) `check_source_health` (*/5) does not create a second alert. Then fix the URL and confirm a success run resets `consecutive_failures` to 0.

**Expected:** One alert row; sibling sources unaffected; alert dedupe works on 4th failure; counter resets on success.

**Why human:** Requires live worker loop to exercise real failure isolation; unit tests mock the session but the end-to-end task isolation path needs a live Celery queue.

---

#### 3. Restore-Doc Walkthrough (REQ-nfr-reliability)

**Test:** Read `docs/runbook-backup-restore.md` from top to bottom. Confirm the procedure covers: (1) creating a clean database, (2) running `pg_restore`, (3) running `alembic upgrade head`, (4) re-seeding. Optionally run `deploy/backup/pg_backup.sh` once and confirm a `.pgdump` file appears in the backup directory.

**Expected:** Runbook has all 4 restore steps; ≤2h target appears in §5; 14-daily/8-weekly retention documented; backup script runs without error.

**Why human:** Runtime DBA judgment and readability review; `sh -n` syntax check passed but execution quality requires human assessment.

---

### Gaps Summary

**RESOLVED — no remaining code-level gaps.** The single gap found at initial verification (SC#4: `parse_raw_item` never set `parse_status='irrelevant'`) was fixed in commit `be14a26`: the no-match branch now sets `parse_status='irrelevant'` (the dev-spec §2.1 / ROADMAP SC#4 term, which the weekly irrelevant-goods report keys on) while still routing the row to `manual_classification_queue` for dictionary top-up. The two weakened tests were tightened to assert `== 'irrelevant'`. Full suite: 289 passed, 0 failed.

All 5 success criteria are VERIFIED at the code level. The 3 live-stack drills under "Human Verification Required" are intentionally DEFERRED to deploy-time UAT (persisted in `02-UAT.md`, tracked in STATE.md Deferred Items) per explicit user approval at the 02-07 execute-phase checkpoint (2026-06-16) — the user elected to accept the phase on the passing automated acceptance gate (100% accuracy on 55 positions; 289 tests green) and run the live runtime confirmation at deployment.

---

_Verified: 2026-06-16T00:00:00Z (initial, 4/5 human_needed)_
_Re-verified: 2026-06-16T08:00:00Z (5/5 passed after SC#4 fix `be14a26`; live drills deferred to deploy-time UAT per user)_
_Verifier: Claude (gsd-verifier) + orchestrator re-verification_
