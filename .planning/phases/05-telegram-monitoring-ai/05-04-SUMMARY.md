---
phase: 05-telegram-monitoring-ai
plan: "04"
subsystem: backend/tasks + backend/services + dashboard
tags:
  - celery-orchestrator
  - ai-signal-pipeline
  - needs-review
  - budget-gate
  - nightly-catchup
  - lead-scoring
  - guardrails
dependency_graph:
  requires:
    - "backend/parsing/extractor.py::extract_signal (05-03)"
    - "backend/parsing/budget.py::check_and_reserve_tokens, record_actual_tokens, per_source_spend (05-03)"
    - "backend/parsing/fallback.py::rule_based_extract (05-03)"
    - "backend/parsing/lead_scoring.py::compute_lead_score, SCORING_PROMPT_VERSION (05-03)"
    - "backend/parsing/text_prep.py::prepare_message_text (05-03)"
    - "backend/parsing/schemas.py::ExtractionResult, BudgetExceeded, CONFIDENCE_REVIEW_THRESHOLD (05-01)"
    - "backend/app/models/sources.py::ParseRun, RawItem (05-01: latency_ms column)"
    - "backend/app/tasks/schedule.py::BEAT_SCHEDULE check_userbot_health entry (05-02 — not clobbered)"
  provides:
    - "backend/app/tasks/parse_telegram.py::parse_telegram_item, enqueue_for_telegram_parse"
    - "backend/app/services/ai_signal_service.py::write_parse_run, create_signal_from_extraction, raise_budget_exceeded_alert"
    - "backend/app/tasks/nightly_catchup.py::nightly_llm_catchup"
    - "BEAT_SCHEDULE::nightly_llm_catchup (crontab hour=2)"
    - "GET /feed?needs_review=true (parameterized filter)"
    - "GET /admin/sources/health::token_spend_7d (per-source 7-day token spend)"
    - "FeedItem::needs_review: bool"
    - "NeedsReviewChip: enabled real toggle"
  affects:
    - "backend/app/tasks/celery_app.py (parse_telegram_item + nightly_llm_catchup routes)"
    - "backend/app/tasks/schedule.py (nightly_llm_catchup beat entry added)"
    - "backend/app/api/feed.py (needs_review filter + SQL JOIN for ai JSONB)"
    - "backend/app/api/admin_sources.py (token_spend_7d field)"
    - "backend/app/schemas/dashboard.py (FeedItem.needs_review)"
    - "dashboard/app/(dashboard)/signals/NeedsReviewChip.tsx (disabled stub → real toggle)"
    - "dashboard/app/(dashboard)/signals/page.tsx (useState + LiveFeedTable wiring)"
    - "dashboard/components/feed/LiveFeedTable.tsx (needsReview prop + buildFeedUrl)"
tech_stack:
  added: []
  patterns:
    - "get_session seam (contextmanager wrapper, patchable in tests — mirrors parse.py)"
    - "Thin wrapper functions at task module level for each service import (patchable)"
    - "G5 attribution ordering: write_parse_run called before create_signal_from_extraction"
    - "BudgetExceeded → rule_based_extract + parse_status='budget_deferred' + nightly deferred"
    - "InstructorRetryException dead-letter: parse_runs.status='error', no signal, task returns"
    - "ON CONFLICT (dedupe_key) DO NOTHING for budget exceeded alert (mirrors source_health pattern)"
    - "CAST(:needs_review AS boolean) bound param in SQL (T-05-19 parameterized)"
    - "needsReview prop in LiveFeedTable with cursor-stack reset on filter change (WR-05)"
key_files:
  created:
    - backend/app/tasks/parse_telegram.py
    - backend/app/services/ai_signal_service.py
    - backend/app/tasks/nightly_catchup.py
    - backend/tests/test_parse_telegram.py
    - backend/tests/test_ai_signal_service.py
    - backend/tests/test_nightly_catchup.py
    - backend/tests/test_needs_review_feed.py
    - backend/tests/test_source_token_spend.py
  modified:
    - backend/app/tasks/celery_app.py (parse_telegram_item + nightly_llm_catchup routes)
    - backend/app/tasks/schedule.py (nightly_llm_catchup beat entry)
    - backend/app/api/feed.py (needs_review filter + JOIN + _row_to_feed_item)
    - backend/app/api/admin_sources.py (token_spend_7d + per_source_spend import)
    - backend/app/schemas/dashboard.py (FeedItem.needs_review: bool)
    - dashboard/app/(dashboard)/signals/NeedsReviewChip.tsx (enabled toggle)
    - dashboard/app/(dashboard)/signals/page.tsx (useState + prop wiring)
    - dashboard/components/feed/LiveFeedTable.tsx (needsReview prop)
    - backend/tests/test_beat_schedule.py (nightly_llm_catchup in required_keys)
decisions:
  - "parse_status='budget_deferred' as re-processable state marker — distinct from 'pending' to make nightly catch-up query explicit (not polluting the main pending queue)"
  - "Thin wrapper functions in parse_telegram.py for all imported services — matches parse.py pattern for clean test patching without patching module internals"
  - "ai JSONB includes scoring_prompt_version (SCORING_PROMPT_VERSION constant) in addition to prompt_version (extraction version) — both needed for backfill audit in 05-05"
  - "Feed SQL JOIN to signals table for ai JSONB — v_live_feed does not expose ai column; LEFT JOIN on id+origin='signal' is the minimal surface change"
  - "InstructorRetryException: constructor in tests uses positional message + n_attempts=int + total_usage=int (instructor v2 API, same fix as 05-03)"
  - "Dashboard TSC not run in-worktree (no node_modules); edits are type-correct; covered by post-merge gate"
metrics:
  duration: "~60 min"
  completed: "2026-06-19T05:51:16Z"
  tasks_completed: 2
  files_created: 8
  files_modified: 9
---

# Phase 5 Plan 04: Pipeline Wiring — Orchestrator, Catch-Up, Feed Filter Summary

## One-Liner

parse_telegram_item Celery orchestrator enforcing G1-G6 guardrails (budget gate, LLM extract, confidence routing, dead-letter, rule-based fallback with nightly catch-up + deduped budget alert), ai_signal_service mapping ExtractionResult→Signal with full ai JSONB stamp, and the complete surface layer: needs_review feed filter (parameterized SQL), per-source 7-day token spend in admin, enabled NeedsReviewChip toggle wired to LiveFeedTable.

## What Was Built

### Task 1: parse_telegram_item + ai_signal_service (TDD RED/GREEN)

**`backend/app/tasks/parse_telegram.py`** (367 lines):
- `@celery_app.task(name="parse_telegram_item")` routed to `parse` queue
- Flow: get_session seam → double-parse guard → prepare_message_text → blank check (G6) → check_and_reserve_tokens → extract_signal → record_actual_tokens; OR BudgetExceeded → rule_based_extract + parse_status='budget_deferred' + enqueue_nightly_reprocess + raise_budget_exceeded_alert; OR InstructorRetryException → write_parse_run(error) + parse_status='failed' + return (dead-letter, G3, no signal)
- **G5 attribution ordering**: `write_parse_run` called BEFORE `create_signal_from_extraction` always
- **G2**: `needs_review = result.confidence < CONFIDENCE_REVIEW_THRESHOLD` — no path skips this check
- `enqueue_for_telegram_parse(raw_item_id)` helper dispatches via `.delay()`
- Thin module-level wrapper functions for all service imports (clean test seam, mirrors parse.py)

**`backend/app/services/ai_signal_service.py`**:
- `write_parse_run(session, raw_item_id, *, parser, model, prompt_version, tokens_in, tokens_out, latency_ms, result, status, error)` → inserts ParseRun + flush, returns id. Never commits (service-never-commits axiom).
- `create_signal_from_extraction(session, raw_item, result, journal, *, needs_review)` → resolves product_id/grade_id, computes lead_score via compute_lead_score, stamps ai JSONB: `{lead_score, classification, needs_review, model, prompt_version, scored_at, scoring_prompt_version}`. Maps ExtractionResult→Signal columns (kind, volume, price, currency, region, counterparty_text, urgency denormalized, event_at fallback chain). Never commits.
- `raise_budget_exceeded_alert(session)` → INSERT INTO alerts with `dedupe_key=llm_budget_exceeded:{UTC_date}` ON CONFLICT DO NOTHING + flush.

**`backend/app/tasks/celery_app.py`**: Added `parse_telegram_item` and `nightly_llm_catchup` routes to parse queue.

**Tests (32 passing)**:
- test_parse_telegram.py: 9 tests (happy path, needs_review, irrelevant, dead-letter, budget degrade, double-parse guard, G5 attribution ordering, blank content G6, enqueue helper)
- test_ai_signal_service.py: 23 tests (write_parse_run fields/flush/no-commit; create_signal_from_extraction ai JSONB keys, needs_review True/False, model/prompt_version, lead_score range, classification HOT/MEDIUM/LOW, scored_at ISO, kind/volume/price/currency/region/counterparty, urgency, scoring_prompt_version, event_at fallback, status=new, source_id; raise_budget_exceeded_alert ON CONFLICT DO NOTHING, dedupe_key today, flush/no-commit)

### Task 2: Nightly catch-up + needs_review feed filter + per-source token spend + dashboard chip

**`backend/app/tasks/nightly_catchup.py`**:
- `@celery_app.task(name="nightly_llm_catchup")` at beat `crontab(minute=0, hour=2)`
- Selects raw_items JOIN sources WHERE parse_status='budget_deferred' AND adapter='telegram_channel' ORDER BY fetched_at ASC LIMIT 200
- Resets parse_status → 'pending' (clears double-parse guard), commits, then dispatches `enqueue_for_telegram_parse` for each item

**`backend/app/tasks/schedule.py`**: `nightly_llm_catchup` beat entry added at `crontab(minute=0, hour=2)`; `check_userbot_health` entry preserved (not clobbered)

**`backend/app/api/feed.py`**:
- `needs_review: bool | None = Query(default=None)` parameter added to `get_feed`
- SQL updated to LEFT JOIN signals for ai JSONB: `COALESCE((s.ai->>'needs_review')::boolean, false) AS needs_review`
- Filter: `AND (CAST(:needs_review AS boolean) IS NULL OR (s.ai->>'needs_review')::boolean = CAST(:needs_review AS boolean))` — fully parameterized (T-05-19)
- `_row_to_feed_item` reads `row.needs_review` attribute (or index 12 for tuples)

**`backend/app/schemas/dashboard.py`**: `FeedItem.needs_review: bool` field added

**`backend/app/api/admin_sources.py`**:
- `from parsing.budget import per_source_spend` import added
- `SourceHealthItem.token_spend_7d: int` field added
- `get_sources_health` populates `token_spend_7d` via `per_source_spend(db, source_id, days=7)` for `telegram_channel`/`llm_page` adapter prefixes; 0 for all other adapter types

**Dashboard (TypeScript — TSC not run in-worktree)**:
- `NeedsReviewChip.tsx`: disabled stub replaced with real toggle (`active: bool, onToggle: () => void` props); no `disabled` attribute; styling uses Tailwind token classes (border-accent/bg-accent on active, border-border on inactive)
- `page.tsx`: converted to `"use client"`, added `useState<boolean>(false)` for `needsReview`; passes `active={needsReview}` + `onToggle` to NeedsReviewChip; passes `needsReview={needsReview || undefined}` to LiveFeedTable
- `LiveFeedTable.tsx`: `needsReview?: boolean` prop added to `LiveFeedTableProps`; `buildFeedUrl` passes `needs_review=true` when set; cursor reset `useEffect` includes `needsReview` in dependency array

**Tests (14 passing)**:
- test_nightly_catchup.py: beat entry at hour=2, deferred items re-enqueued, empty list no crash, status reset to pending
- test_needs_review_feed.py: FeedItem has needs_review:bool, filter passes param to SQL, :needs_review is bound param, _row_to_feed_item maps True/False/default-False
- test_source_token_spend.py: SourceHealthItem has token_spend_7d:int, telegram_channel returns real spend, uzex_offers returns 0, llm_page returns real spend

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] InstructorRetryException constructor — instructor v2 API**
- **Found during:** Task 1 RED phase (test construction)
- **Issue:** instructor v2 (`InstructorRetryException.__init__`) requires positional message + keyword-only `n_attempts: int` + `total_usage: int` (not `message=` keyword, and `total_usage` is `int` not `Any`)
- **Fix:** Updated test to use `InstructorRetryException("...", n_attempts=2, total_usage=0, last_completion=None, messages=[])`
- **Files modified:** backend/tests/test_parse_telegram.py
- **Commit:** Inline in RED commit 56b9d25

**2. [Rule 1 - Bug] Test patching for match_product/extract_grade in ai_signal_service**
- **Found during:** Task 1 GREEN phase — AttributeError: module has no attribute 'match_product'
- **Issue:** Tests patched `app.services.ai_signal_service.match_product` but those functions were imported lazily inside `create_signal_from_extraction`. Lazy imports inside functions are not patchable at the module attribute level.
- **Fix:** Added module-level imports of `match_product` and `extract_grade` in ai_signal_service.py (moved out of function body), making them patchable as module attributes
- **Files modified:** backend/app/services/ai_signal_service.py
- **Commit:** 0704287

**3. [Rule 1 - Bug] test_beat_schedule hardcoded key set didn't include nightly_llm_catchup**
- **Found during:** Post-task 2 regression check
- **Issue:** `test_all_five_keys_present` used exact set equality with 6 keys; adding `nightly_llm_catchup` (required new beat entry) caused the test to fail with "Extra items: nightly_llm_catchup"
- **Fix:** Added `nightly_llm_catchup` to `required_keys` set with Phase 5 (05-04) attribution comment
- **Files modified:** backend/tests/test_beat_schedule.py
- **Commit:** 40626ba

**4. [Rule 1 - Bug] Test mock self-reference issue in test_feed_needs_review_param_is_bound_not_interpolated**
- **Found during:** Task 2 test run
- **Issue:** Test replaced `mock_db.execute` with a capture function, then tried to return `mock_db.execute.return_value` (which was now the function itself, not the MagicMock)
- **Fix:** Created a separate `mock_result = MagicMock()` and returned that from the capture function
- **Files modified:** backend/tests/test_needs_review_feed.py
- **Commit:** c283a82 (inline fix before commit)

## Known Stubs

None. All production code is wired:
- `parse_telegram_item` calls real extract_signal/rule_based_extract (mocked in tests only)
- `ai_signal_service.create_signal_from_extraction` calls real lead_scoring.compute_lead_score
- `raise_budget_exceeded_alert` inserts real alerts via ORM
- `nightly_llm_catchup` queries real DB and dispatches real Celery tasks
- `NeedsReviewChip` is a real toggle (no `disabled` attribute, no placeholder tooltip)
- `LiveFeedTable` passes `needs_review` to buildFeedUrl (real query param)

## TDD Gate Compliance

Task 1 followed RED/GREEN discipline:
- `56b9d25` — test(05-04): RED phase — failing tests (32 failures)
- `0704287` — feat(05-04): Task 1 GREEN — implementation (32 pass)

Task 2 did not use explicit TDD (plan type is `auto`, not `tdd="true"`). Tests were written simultaneously with implementation.

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`. Implemented mitigations:

| T-ID | Mitigation Applied |
|------|-------------------|
| T-05-15 | G5: write_parse_run called before create_signal_from_extraction in every code path; asserted in test_attribution_invariant_parse_run_before_signal |
| T-05-16 | G3: InstructorRetryException path returns immediately after error parse_run; create_signal_from_extraction never called on this path (test_instructor_retry_exception_dead_letters) |
| T-05-17 | G2: `needs_review = result.confidence < CONFIDENCE_REVIEW_THRESHOLD` evaluated before signal write; no code path bypasses this (test_low_confidence_sets_needs_review_true) |
| T-05-18 | G4: BudgetExceeded → rule_based_extract + parse_status='budget_deferred' + enqueue_nightly_reprocess + raise_budget_exceeded_alert; pipeline never indefinitely blocked (test_budget_exceeded_degrades_to_rule_based) |
| T-05-19 | CAST(:needs_review AS boolean) bound parameter in GET /feed SQL; asserted in test_feed_needs_review_param_is_bound_not_interpolated |

## Self-Check: PASSED

**Files created:**
- `backend/app/tasks/parse_telegram.py` — FOUND (367 lines, ≥90 required)
- `backend/app/services/ai_signal_service.py` — FOUND
- `backend/app/tasks/nightly_catchup.py` — FOUND
- `backend/tests/test_parse_telegram.py` — FOUND
- `backend/tests/test_ai_signal_service.py` — FOUND
- `backend/tests/test_nightly_catchup.py` — FOUND
- `backend/tests/test_needs_review_feed.py` — FOUND
- `backend/tests/test_source_token_spend.py` — FOUND

**Files modified (confirmed):**
- `backend/app/tasks/celery_app.py` — FOUND
- `backend/app/tasks/schedule.py` — FOUND
- `backend/app/api/feed.py` — FOUND
- `backend/app/api/admin_sources.py` — FOUND
- `backend/app/schemas/dashboard.py` — FOUND
- `dashboard/app/(dashboard)/signals/NeedsReviewChip.tsx` — FOUND
- `dashboard/app/(dashboard)/signals/page.tsx` — FOUND
- `dashboard/components/feed/LiveFeedTable.tsx` — FOUND
- `backend/tests/test_beat_schedule.py` — FOUND

**Commits verified:**
- `56b9d25` — test(05-04): RED phase (FOUND)
- `0704287` — feat(05-04): Task 1 GREEN (FOUND)
- `c283a82` — feat(05-04): Task 2 (FOUND)
- `40626ba` — fix(05-04): beat schedule test (FOUND)

**Final test run:** 46 plan tests pass; full suite 666 pass / 1 pre-existing flaky (test_adapter_self_registers — ordering-sensitive, passes in isolation, pre-existing from 05-02)

**Beat schedule:** `nightly_llm_catchup` at `<crontab: 0 2 * * *>` confirmed; `check_userbot_health` at `*/5` preserved

**Celery routes:** `parse_telegram_item → parse`, `nightly_llm_catchup → parse` confirmed
