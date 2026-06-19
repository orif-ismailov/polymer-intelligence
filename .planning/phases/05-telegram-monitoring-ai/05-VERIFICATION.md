---
phase: 05-telegram-monitoring-ai
verified: 2026-06-19T07:20:53Z
status: human_needed
score: 15/15 must-haves verified
overrides_applied: 0
gaps: []
human_verification:
  - test: "Live userbot ingestion drill — start docker compose up userbot with real TG_API_ID/TG_API_HASH/TG_SESSION_STRING. Confirm the userbot connects, subscribes to the enabled channel(s), and logs the heartbeat write. Post or wait for a message in a monitored channel; confirm a new row appears in raw_items with parse_status='pending' and the fwd_from payload populated for forwarded messages. Enable a second channel in the dashboard; within ~10 min confirm the userbot picks it up WITHOUT restart. Stop the userbot; within ~5 min confirm a userbot_silent alert appears."
    expected: "raw_items row created with parse_status='pending', fwd_from payload present for forwards, channel-reread loop picks up new channel within USERBOT_CHANNEL_REREAD_SECONDS, alert raised within ~5 min of silence"
    why_human: "Requires customer-provided TG_API_ID/TG_API_HASH/TG_SESSION_STRING and a live Telegram account joined to monitored channels — gated customer input not yet available. Automated unit tests cover all deterministic behaviors (channel_registry filter, heartbeat write/read, adapter test/fetch, health alert dedupe)."

  - test: "Real-data 80/85 gate — place the customer 100-message control sample at GOLDEN_SET_PATH and the customer synonym map at the configured path. Run the transport spike on dev_golden_20 (instructor TOOLS vs native) and confirm the pinned PARSER in extractor.py is the winner. Run the refresh path locally with a real ANTHROPIC_API_KEY to generate frozen predictions for prompt_version v1 over 100 rows; commit predictions/extract_v1.json. Run pytest tests/parsing/test_telegram_accuracy.py -m gate and confirm recall >=80% and field precision >=85%. Senior trader signs off the two §5.3 defaults (price ±0.5% tolerance; synonym-aware grade counts toward the gate)."
    expected: "pytest gate marks pass (recall >=0.80, precision >=0.85) on the real customer 100-message sample; trader sign-off on the two metric defaults"
    why_human: "Requires the customer-provided 100-message control sample and synonym map — gated inputs not yet available. The deterministic CI gate (frozen example predictions vs example golden set) already passes at 100%/100% on the committed example fixture; it stands until the real sample replaces it."
---

# Phase 5: Telegram Monitoring + AI Verification Report

**Phase Goal:** Telegram Monitoring + AI — a long-lived Telethon userbot driven by the source registry, LLM extraction with a daily token budget + rule-based fallback, a needs_review flow surfaced in the dashboard, an eval golden-set harness enforcing the TZ §6.1.3 accuracy gate (recall ≥80% / field precision ≥85%), and lead scoring recomputed on prompt-version change.
**Verified:** 2026-06-19T07:20:53Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| T1 | Long-lived Telethon userbot is a separate process driven by the source registry | VERIFIED | `userbot/main.py` defines `run_userbot()` with NewMessage handler; `deploy/docker-compose.dev.yml` defines separate `userbot:` service with `command: python -m userbot.main`, `restart: unless-stopped` |
| T2 | Channel list is re-read every ~10 min without process restart | VERIFIED | `_reread_loop()` in `userbot/main.py` sleeps `settings.USERBOT_CHANNEL_REREAD_SECONDS` (default 600) and reloads `load_enabled_channel_sources()`, updating `current_username_map` in-place |
| T3 | New channel messages are written to raw_items via the existing save_raw_items dedupe path with parse_status='pending' | VERIFIED | `userbot/main.py` calls `save_raw_items(db_session, source_obj, [draft])` in the message handler; `RawItemDraft` built with `external_id`, `content`, `payload`, `event_at` |
| T4 | FloodWaitError is caught and the userbot sleeps e.seconds | VERIFIED | `telethon.errors.FloodWaitError` caught in `_connect_and_run()`; `await asyncio.sleep(e.seconds)` executed |
| T5 | Userbot writes a Redis heartbeat key; silence >5 min raises a deduped admin alert | VERIFIED | `userbot/heartbeat.py` defines `HEARTBEAT_KEY="userbot:heartbeat"`, `write_heartbeat(redis)`, `read_heartbeat(redis)`; `userbot_health_service.py` defines `USERBOT_SILENCE_SECONDS=300` and `check_userbot_heartbeat()` with deduped `ON CONFLICT (dedupe_key) DO NOTHING`; beat task `check_userbot_health` on `*/5` in `schedule.py` |
| T6 | extract_signal returns ExtractionResult + journal with parser/model/prompt_version/tokens_in/tokens_out/latency_ms | VERIFIED | `parsing/extractor.py:extract_signal()` uses `_client.messages.create_with_completion()` with `temperature=0`, `max_tokens=512`, `response_model=ExtractionResult`, `max_retries=2`; journal dict has all 8 required keys; 105 parsing tests pass including extractor tests |
| T7 | check_and_reserve_tokens raises BudgetExceeded atomically via Lua EVAL; CR-05 fixed | VERIFIED | `parsing/budget.py` defines `_RESERVE_LUA` Lua script that atomically checks + INCRBYs or returns -1; replaces the prior non-atomic INCRBY+DECRBY rollback (CR-05 fix confirmed in budget.py) |
| T8 | rule_based_extract returns a valid ExtractionResult with confidence < 0.5 (forces needs_review) | VERIFIED | `parsing/fallback.py:rule_based_extract()` returns a valid ExtractionResult; relevant results have `confidence` below `CONFIDENCE_REVIEW_THRESHOLD = 0.5`; 105 parsing tests pass including fallback tests |
| T9 | compute_lead_score returns (float 0-1, HOT/MEDIUM/LOW) stamped with SCORING_PROMPT_VERSION | VERIFIED | `parsing/lead_scoring.py` defines `SCORING_PROMPT_VERSION="lead_v1"` and `compute_lead_score()` returning `tuple[float, str]` |
| T10 | parse_telegram_item writes exactly one parse_runs row per attempt, enforces G1-G6 guardrails, confidence<0.5→needs_review=true | VERIFIED | `backend/app/tasks/parse_telegram.py` full orchestrator; G5 attribution: `write_parse_run` called BEFORE `create_signal_from_extraction`; G2: `needs_review = result.confidence < CONFIDENCE_REVIEW_THRESHOLD`; G3: `InstructorRetryException` dead-letters; G4: `BudgetExceeded` degrades to `rule_based_extract`, sets `parse_status='budget_deferred'` (valid after migration 0004), enqueues `nightly_reprocess`, raises budget alert; G6: blank content marked irrelevant without LLM call; CR-03 fix: `delete_existing_signals()` called before every signal write |
| T11 | budget_deferred is a valid parse_status ENUM value; nightly catch-up finds and reprocesses deferred items | VERIFIED | `backend/app/models/enums.py:ParseStatus` defines `budget_deferred = "budget_deferred"`; migration 0004 adds `ALTER TYPE parse_status ADD VALUE IF NOT EXISTS 'budget_deferred'`; `nightly_catchup.py` queries `WHERE ri.parse_status = 'budget_deferred'`; 106 pipeline tests pass |
| T12 | GET /feed?needs_review=true returns only signals with ai->>'needs_review'='true'; NeedsReviewChip is a live toggle | VERIFIED | `backend/app/api/feed.py` adds bound-param filter `COALESCE((s.ai->>'needs_review')::boolean, false) = CAST(:needs_review AS boolean)`; `FeedItem` has `needs_review: bool`; `NeedsReviewChip.tsx` is a real `<button>` with `onClick={onToggle}`, no disabled stub; `page.tsx` passes `needsReview` to `LiveFeedTable`; `LiveFeedTable.tsx` sets `params.set("needs_review", "true")` |
| T13 | Admin sources expose per-source 7-day token spend | VERIFIED | `admin_sources.py:SourceHealthItem` has `token_spend_7d: int`; populated via `per_source_spend(db, row[0], days=7)` for AI sources; `parsing/budget.py:per_source_spend()` queries `parse_runs WHERE parser LIKE 'llm_extract%'` joined to `raw_items.source_id` |
| T14 | Eval harness scores frozen predictions key-free; gate asserts recall>=0.80, field_precision>=0.85 | VERIFIED | `test_telegram_accuracy.py` loads `golden_loader.load_golden_set()` + `load_predictions("v1")` with no LLM call; `test_recall_gte_80_percent` and `test_field_precision_gte_85_percent` are `@pytest.mark.gate`; eval CLI runs and prints `PASS` at 100%/100% on example fixture; 105 parsing tests pass |
| T15 | rescore_on_prompt_version_change recomputes lead_score for affected signals and overwrites signals.ai | VERIFIED | `lead_score_recompute_service.py:rescore_on_prompt_version_change()` uses keyset pagination (`Signal.id > last_id`) to avoid mutate-while-paginating bug (WR-04 fix); overwrites `signal.ai` with new `scoring_prompt_version`; `rescore.py` Celery task routes to parse queue |

**Score:** 15/15 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/parsing/schemas.py` | ExtractionResult, SignalKind, UrgencyLevel, FieldConfidence, BudgetExceeded, CONFIDENCE_REVIEW_THRESHOLD | VERIFIED | 270 lines; all classes present; irrelevant_fields_must_be_null + normalise_currency validators present |
| `backend/parsing/prompts/extract_v1.md` | Immutable v1 prompt with schema, null semantics, 3 few-shot examples | VERIFIED | 277 lines; contains is_relevant, currency rules, kind rules, volume normalisation; 3 annotated few-shot examples |
| `backend/parsing/prompts/loader.py` | load_prompt(version) -> str, lru_cached, raises FileNotFoundError | VERIFIED | lru_cache(maxsize=16); raises FileNotFoundError with clear message |
| `docs/extraction-schema.json` | Fixed strict-JSON schema with all ExtractionResult fields | VERIFIED | Valid JSON; properties include is_relevant, kind, product, grade_text, volume, price, currency, counterparty_text, urgency, confidence |
| `backend/alembic/versions/0003_phase5_ai_extraction.py` | Migration: parse_runs.latency_ms + partial index | VERIFIED | revision="0003", down_revision="0002"; adds latency_ms column |
| `backend/alembic/versions/0004_phase5_budget_deferred_and_index_fix.py` | Migration: budget_deferred ENUM + corrected index predicate | VERIFIED | revision="0004", down_revision="0003"; adds budget_deferred via autocommit_block; recreates index with `LIKE 'llm_extract%'` |
| `userbot/main.py` | Telethon userbot: subscribe, message handler, heartbeat loop, channel reread loop, FloodWait | VERIFIED | run_userbot(), NewMessage handler, _heartbeat_loop(), _reread_loop(), FloodWaitError caught; 80+ lines |
| `userbot/channel_registry.py` | load_enabled_channels() reading enabled telegram_channel sources | VERIFIED | filters adapter='telegram_channel' AND is_enabled AND last_test_ok_at IS NOT NULL |
| `userbot/heartbeat.py` | write_heartbeat / read_heartbeat on key userbot:heartbeat | VERIFIED | HEARTBEAT_KEY="userbot:heartbeat"; write/read functions present |
| `backend/app/services/userbot_health_service.py` | check_userbot_heartbeat raises deduped alert when stale >5 min | VERIFIED | USERBOT_SILENCE_SECONDS=300; ON CONFLICT (dedupe_key) DO NOTHING dedupe |
| `backend/app/ingest/telegram_channel/adapter.py` | Live test()/fetch() replacing Phase-4 pending stub | VERIFIED | No "Available after Phase 5" stub text; real test() and fetch() methods using Telethon |
| `backend/parsing/extractor.py` | extract_signal singleton, Mode.TOOLS, create_with_completion, max_retries=2, temperature=0, prompt-caching | VERIFIED | Module-level _client singleton; temperature=0, max_tokens=512, max_retries=2, cache_control ephemeral on system block |
| `backend/parsing/budget.py` | check_and_reserve_tokens, record_actual_tokens, Lua EVAL atomic gate | VERIFIED | _RESERVE_LUA Lua script; _next_midnight_ts() (renamed per WR-06 fix); per_source_spend() present |
| `backend/parsing/fallback.py` | rule_based_extract -> ExtractionResult (low confidence, real extraction) | VERIFIED | Real fallback with regex product/currency/volume; confidence below CONFIDENCE_REVIEW_THRESHOLD |
| `backend/parsing/lead_scoring.py` | compute_lead_score, SCORING_PROMPT_VERSION | VERIFIED | SCORING_PROMPT_VERSION="lead_v1"; compute_lead_score() returning (float, str); classify() with HOT≥0.7/MEDIUM≥0.4 |
| `backend/parsing/text_prep.py` | prepare_message_text(raw, max_tokens=2000) -> str | VERIFIED | Returns "" on blank input; appends [TRUNCATED] on oversized input |
| `backend/app/tasks/parse_telegram.py` | Full orchestrator: budget gate, LLM/fallback, journal, needs_review routing, dead-letter | VERIFIED | 400+ lines; G1-G6 enforced; delete_existing_signals() idempotency guard (CR-03); LLM_TOKEN_ESTIMATE=1200 (WR-02 fix) |
| `backend/app/services/ai_signal_service.py` | create_signal_from_extraction, write_parse_run, raise_budget_exceeded_alert | VERIFIED | All three functions present; _map_kind returns SignalKind.news for unknown (WR-07 fix) |
| `backend/app/tasks/nightly_catchup.py` | Celery task nightly_llm_catchup, beat at hour=2 | VERIFIED | Task defined; beat entry at crontab(minute=0, hour=2) in schedule.py |
| `backend/app/services/lead_score_recompute_service.py` | rescore_on_prompt_version_change -> count re-scored | VERIFIED | 232 lines; keyset pagination (WR-04 fix); JSONB imported explicitly (WR-03 fix) |
| `backend/app/tasks/rescore.py` | Celery task rescore_signals_for_prompt_version | VERIFIED | Task present; docstring corrected to single-commit semantics (WR-09 fix) |
| `backend/tests/parsing/eval_config.py` | RECALL_GATE=0.80, PRECISION_GATE=0.85, PRICE_TOLERANCE_PCT=0.5, GATE_FIELDS | VERIFIED | All constants present |
| `backend/tests/parsing/eval_metrics.py` | compute_recall, compute_field_precision, per_field_breakdown, match_field | VERIFIED | 434 lines; all four functions present |
| `backend/tests/parsing/golden_loader.py` | load_golden_set, load_predictions, load_synonyms; example fallback | VERIFIED | Customer-path-or-example resolution present |
| `backend/tests/parsing/golden/control_sample_100.example.json` | 100-row example golden set covering all failure modes | VERIFIED | Valid JSON; covers sell_offer, buy_request, deal, price_quote, news, spam, currency-adversarial, grade-Cyrillic/Latin, kg/vagon volume, fwd_from |
| `backend/tests/parsing/golden/predictions/extract_v1.json` | Frozen predictions for example gate | VERIFIED | File present at predictions/extract_v1.json |
| `backend/tests/parsing/test_telegram_accuracy.py` | Gate tests: recall>=0.80, precision>=0.85 on frozen predictions | VERIFIED | test_recall_gte_80_percent and test_field_precision_gte_85_percent marked @pytest.mark.gate; 105 parsing tests pass |
| `backend/parsing/eval_cli.py` | python -m parsing.eval_cli prints recall/precision/verdict | VERIFIED | Running `python -m parsing.eval_cli` outputs "D1 Recall (gate ≥80%): 100.0% [PASS]", "Field Precision (gate ≥85%): 100.0% [PASS]", "VERDICT: PASS" |
| `dashboard/app/(dashboard)/signals/NeedsReviewChip.tsx` | Real toggle chip (not disabled stub) | VERIFIED | Real button with onClick={onToggle}, aria-pressed; no "Available after Phase 5" text |
| `dashboard/app/(dashboard)/signals/page.tsx` | NeedsReviewChip wired to feed query | VERIFIED | `useState(false)` for needsReview; `NeedsReviewChip active={needsReview} onToggle={...}` passes needsReview to LiveFeedTable |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `userbot/main.py` | `backend/app/services/raw_pipeline.py` | `save_raw_items(session, source, [draft])` | VERIFIED | Direct import + call in message handler |
| `userbot/channel_registry.py` | `sources` table | `SELECT enabled sources WHERE adapter='telegram_channel'` | VERIFIED | SQL filters adapter='telegram_channel' AND is_enabled AND last_test_ok_at IS NOT NULL |
| `backend/app/tasks/userbot_health.py` | `backend/app/services/userbot_health_service.py` | `check_userbot_heartbeat` on */5 beat | VERIFIED | Beat entry `check_userbot_health` in schedule.py; task calls `check_userbot_heartbeat` |
| `backend/parsing/extractor.py` | `backend/parsing/prompts/loader.py` | `load_prompt(prompt_version)` | VERIFIED | `system_prompt = load_prompt(prompt_version)` in extract_signal() |
| `backend/parsing/extractor.py` | `backend/parsing/schemas.py` | `response_model=ExtractionResult` | VERIFIED | `response_model=ExtractionResult` in create_with_completion call |
| `backend/parsing/budget.py` | Redis | `INCRBY via Lua EVAL with expireat midnight` | VERIFIED | `_RESERVE_LUA` Lua script with `redis.call('INCRBY', KEYS[1], amount)` and `redis.call('EXPIREAT', ...)` |
| `backend/app/tasks/parse_telegram.py` | `backend/parsing/extractor.py` | `extract_signal(prepared_text)` | VERIFIED | `result, journal = extract_signal(prepared)` in parse_telegram_item |
| `backend/app/tasks/parse_telegram.py` | `backend/parsing/budget.py` | `check_and_reserve_tokens then record_actual_tokens` | VERIFIED | Both calls present in budget gate block |
| `backend/app/services/ai_signal_service.py` | `signals.ai` | `ai JSONB = {lead_score, classification, needs_review, model, prompt_version, scored_at}` | VERIFIED | `signal.ai` dict with all 6 keys stamped in `create_signal_from_extraction()` |
| `dashboard/app/(dashboard)/signals/page.tsx` | `/feed?needs_review=true` | `NeedsReviewChip toggle → filter query` | VERIFIED | `LiveFeedTable needsReview={needsReview}` → `params.set("needs_review", "true")` in LiveFeedTable.tsx |
| `backend/tests/parsing/test_telegram_accuracy.py` | `backend/tests/parsing/eval_metrics.py` | `compute_recall + compute_field_precision over frozen predictions` | VERIFIED | Both functions imported and called in gate tests |
| `backend/app/services/lead_score_recompute_service.py` | `backend/parsing/lead_scoring.py` | `compute_lead_score + SCORING_PROMPT_VERSION re-stamp` | VERIFIED | `compute_lead_score(result)` called and `SCORING_PROMPT_VERSION` stamped in signals.ai |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `userbot/main.py` message handler | `draft` (RawItemDraft) | Telethon NewMessage event | Yes — event.message.message, event.message.id, event.message.date | FLOWING |
| `parse_telegram.py` | `result, journal` | `extract_signal()` or `rule_based_extract()` | Yes — LLM ExtractionResult or regex-based fallback | FLOWING |
| `ai_signal_service.py:create_signal_from_extraction` | `signal.ai` | `compute_lead_score(result)` + journal dict | Yes — rule-based score computation + journal fields | FLOWING |
| `feed.py` `/feed?needs_review=true` | feed rows | `signals.ai->>'needs_review'` | Yes — parameterized SQL filter on JSONB column | FLOWING |
| `admin_sources.py` `token_spend_7d` | `per_source_spend(db, source_id, days=7)` | `parse_runs` JOIN `raw_items` | Yes — SQL SUM on parse_runs.tokens_in+tokens_out WHERE parser LIKE 'llm_extract%' | FLOWING |
| `test_telegram_accuracy.py` gate | `recall, precision` | `golden_loader.load_golden_set()` + `load_predictions("v1")` | Yes — example fixture + frozen predictions; gate passes at 100%/100% | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Parsing tests (all 105) pass | `.venv/bin/pytest tests/parsing/ -q` | 105 passed, 1 deselected, 8 warnings | PASS |
| Pipeline + migration tests (all 106) pass | `.venv/bin/pytest tests/test_parse_telegram.py tests/test_ai_signal_service.py tests/test_nightly_catchup.py tests/test_needs_review_feed.py tests/test_source_token_spend.py tests/test_migration_0003.py tests/test_userbot_channel_registry.py tests/test_userbot_heartbeat.py tests/test_telegram_channel_adapter.py tests/test_lead_score_recompute.py -q` | 106 passed, 5 warnings | PASS |
| eval CLI prints recall/precision/verdict | `python -m parsing.eval_cli` | D1 Recall: 100.0% [PASS], Field Precision: 100.0% [PASS], VERDICT: PASS | PASS |
| docs/extraction-schema.json is valid JSON with required fields | `python3 -c "import json; d=json.load(open(...)); print(list(d['properties'].keys())[:15])"` | ['is_relevant', 'kind', 'product', 'grade_text', 'volume', 'volume_unit', 'price', 'currency', 'region', 'counterparty_text', 'urgency', 'lead_score', 'confidence', 'field_confidence', 'event_at'] | PASS |
| budget_deferred in ParseStatus enum | `grep budget_deferred backend/app/models/enums.py` | `budget_deferred = "budget_deferred"` at line 36 | PASS |
| Beat schedule has phase-05 tasks | `grep "check_userbot_health\|nightly_llm_catchup" backend/app/tasks/schedule.py` | Both entries present at lines 57-68 | PASS |
| extract_v1.md is ≥40 lines and immutable | `wc -l backend/parsing/prompts/extract_v1.md` | 277 lines | PASS |
| 3 new deps declared in pyproject.toml | `grep -c "anthropic\|instructor\|telethon" backend/pyproject.toml` | 12 (multiple references for pins + mypy overrides) | PASS |
| Userbot separate compose service | `grep "python -m userbot.main" deploy/docker-compose.dev.yml` | Line 194: `command: python -m userbot.main` | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| REQ-telegram-monitoring (FR-2) | 05-02 | Userbot reads new messages from public channels → raw_items → AI classify/extract | VERIFIED | userbot/main.py complete; telegram_channel adapter live; channel_registry filters enabled sources; parse_telegram_item orchestrates AI extraction |
| REQ-ai-extraction (FR-19) | 05-01, 05-03, 05-04, 05-05 | Structure messages per fixed JSON schema; prompt version + model journaled in parse_runs | VERIFIED | ExtractionResult schema + extract_v1.md; extract_signal() journals parser/model/prompt_version/tokens/latency_ms; parse_telegram_item writes parse_runs row before signal (G5) |
| REQ-lead-scoring (FR-20) | 05-03, 05-04, 05-05 | lead_score + HOT/MEDIUM/LOW; recomputed on prompt-version change | VERIFIED | compute_lead_score() + SCORING_PROMPT_VERSION; signals.ai stamped; rescore_on_prompt_version_change() + rescore_signals_for_prompt_version Celery task |
| REQ-llm-budget (FR-21) | 05-03, 05-04 | Configurable daily token limit; on exceed degrade to rule-based + reprocessing queue; admin alerted; per-source 7-day spend visible | VERIFIED | Lua EVAL atomic gate; BudgetExceeded → rule_based_extract + budget_deferred + nightly_llm_catchup + deduped admin alert; per_source_spend() + token_spend_7d in SourceHealthItem |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/app/api/feed.py` | 263-265 (pre-WR-01-fix) | SSE interpolation of raw Redis payload | Fixed (WR-01) | Fixed — sanitize with CR/LF strip + [:128] cap confirmed in feed.py |
| `userbot/main.py` | 134-154 | Handler keys on event.chat.username only — private/ID channels silently dropped | Warning (WR-05, skipped) | Non-critical for Phase 5 scope: all agreed sources are public @username channels. Product decision required for ID-based channel support. Explicitly deferred in 05-REVIEW-FIX.md. |

No unreferenced TBD/FIXME/XXX debt markers found in any phase-05 modified file.

### Human Verification Required

#### 1. Live Userbot Ingestion Drill (05-02 UAT)

**Test:** With real TG_API_ID/TG_API_HASH/TG_SESSION_STRING in .env and at least one enabled telegram_channel source: (a) run `docker compose up userbot`; (b) confirm connection + heartbeat log; (c) post or wait for a message in a monitored channel; (d) confirm raw_items row created with parse_status='pending' and fwd_from payload for forwarded messages; (e) enable a second channel in the dashboard, within ~10 min confirm the userbot picks it up WITHOUT restart; (f) stop the userbot, within ~5 min confirm userbot_silent alert appears.

**Expected:** raw_items row created with parse_status='pending' and correct fwd_from payload; channel-reread loop picks up new channel within USERBOT_CHANNEL_REREAD_SECONDS (~10 min) without process restart; alert raised within ~5 min of silence (USERBOT_SILENCE_SECONDS=300); heartbeat loop writes to Redis key `userbot:heartbeat` every 60 s.

**Why human:** Requires customer-provided TG_API_ID/TG_API_HASH/TG_SESSION_STRING and a live Telegram account joined to monitored channels — gated customer input not yet available at time of verification. All deterministic behaviors (channel_registry filter, heartbeat write/read round-trip, adapter test/fetch, health alert dedupe, FloodWait handling, empty-message skip) are covered by the automated unit tests which pass at 100%.

---

#### 2. Real-Data TZ §6.1.3 Gate Run (05-05 UAT)

**Test:** (a) Place the customer 100-message control sample at GOLDEN_SET_PATH (gitignored, replacing the example fixture) and the customer synonym map; (b) run the transport spike on dev_golden_20 (instructor TOOLS vs native JSON) and confirm the pinned PARSER in extractor.py matches the winner; (c) run the refresh path locally (`pytest tests/parsing/test_telegram_accuracy.py -m refresh --runlive`) with a real ANTHROPIC_API_KEY to generate frozen predictions for prompt_version v1 over all 100 rows; commit `predictions/extract_v1.json`; (d) run `pytest tests/parsing/test_telegram_accuracy.py -m gate` and confirm recall ≥80% AND field precision ≥85%; (e) senior trader signs off the two §5.3 metric defaults (price ±0.5% tolerance band; synonym-aware grade match counts toward the gate).

**Expected:** pytest gate tests pass — `test_recall_gte_80_percent` and `test_field_precision_gte_85_percent` both assert without failure on the real 100-message sample; eval CLI `python -m parsing.eval_cli --golden $GOLDEN_SET_PATH` prints PASS with recall ≥80% and field precision ≥85%; trader sign-off documented.

**Why human:** Requires the customer-provided 100-message control sample and synonym map — gated inputs not yet delivered. The deterministic CI gate on the committed example fixture (control_sample_100.example.json + extract_v1.json) already passes at 100% recall / 100% precision and stands as the standing gate until the customer set is delivered. Per 05-PLAN.md and 05-SUMMARY.md, this is explicitly deferred to customer-input delivery / Phase 6 acceptance.

---

### Gaps Summary

No gaps. All 15 automated must-haves are VERIFIED. Both deferred items are human-verification items (gated customer inputs), not implementation failures. The phase-5 code review found 5 critical and 9 warning findings; 13/14 in-scope findings have been fixed and confirmed in the codebase:

- CR-01: `budget_deferred` added to ParseStatus enum + migration 0004 VERIFIED
- CR-02: Resolved transitively by CR-01 VERIFIED
- CR-03: `delete_existing_signals()` idempotency guard added VERIFIED
- CR-04: Migration 0004 recreates `ix_parse_runs_llm_created` with `parser LIKE 'llm_extract%'` VERIFIED
- CR-05: Lua EVAL atomic reserve in `_RESERVE_LUA` VERIFIED
- WR-01 through WR-04, WR-06 through WR-09: All confirmed fixed in code

WR-05 (userbot keys on username only — private/ID channels silently dropped) was deliberately skipped as a product decision. It represents a monitoring gap for non-public-username channels but does not affect the phase-5 deliverables (all agreed sources are public @username channels per the source configuration contract).

---

_Verified: 2026-06-19T07:20:53Z_
_Verifier: Claude (gsd-verifier)_
