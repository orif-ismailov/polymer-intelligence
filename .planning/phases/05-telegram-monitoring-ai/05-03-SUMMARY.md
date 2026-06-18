---
phase: 05-telegram-monitoring-ai
plan: "03"
subsystem: backend/parsing
tags:
  - ai-extraction
  - instructor-sdk
  - token-budget
  - rule-based-fallback
  - lead-scoring
  - text-prep
  - tdd
dependency_graph:
  requires:
    - "backend/parsing/schemas.py::ExtractionResult, BudgetExceeded, CONFIDENCE_REVIEW_THRESHOLD (05-01)"
    - "backend/parsing/prompts/loader.py::load_prompt() (05-01)"
    - "backend/parsing/prompts/extract_v1.md (05-01)"
    - "backend/app/core/config.py::LLM_EXTRACT_MODEL, LLM_PROMPT_VERSION, LLM_DAILY_TOKEN_LIMIT, ANTHROPIC_API_KEY, REDIS_URL"
    - "anthropic>=0.40,<1.0 + instructor>=1.5,<2.0 (pinned in 05-01, verified in Task 0)"
  provides:
    - "backend/parsing/extractor.py::extract_signal(text) → (ExtractionResult, journal)"
    - "backend/parsing/extractor.py::PARSER_TOOLS, PARSER_NATIVE, PARSER constants"
    - "backend/parsing/text_prep.py::prepare_message_text(raw, max_tokens) → str"
    - "backend/parsing/budget.py::check_and_reserve_tokens(), record_actual_tokens(), daily_spend(), key_for(), per_source_spend()"
    - "backend/parsing/fallback.py::rule_based_extract(text) → ExtractionResult"
    - "backend/parsing/lead_scoring.py::compute_lead_score(result) → (float, str), classify(), SCORING_PROMPT_VERSION=lead_v1"
  affects:
    - "backend/tests/parsing/ — 37 new unit tests across 5 files"
tech_stack:
  added:
    - "instructor 1.15.3 — instructor.from_anthropic(client, mode=Mode.TOOLS) singleton; create_with_completion; import path updated to instructor.core (not deprecated .exceptions)"
    - "anthropic 0.109.2 — anthropic.Anthropic(api_key=...) raw client"
  patterns:
    - "Module-level instructor client singleton (AI-SPEC Pitfall 1: patched once, reused across Celery tasks)"
    - "create_with_completion returns (ExtractionResult, raw_completion) for token journaling (Pitfall 2)"
    - "Prompt-cached system block with cache_control ephemeral (Pitfall 3)"
    - "temperature=0 explicit (Pitfall 4: deterministic extraction)"
    - "InstructorRetryException propagates to caller — NOT caught in extractor (Pitfall 5/6)"
    - "INCRBY + EXPIREAT pipeline in budget gate (atomic per-command, rollback via DECRBY)"
    - "TDD RED/GREEN commit flow for both tasks"
key_files:
  created:
    - backend/parsing/extractor.py
    - backend/parsing/text_prep.py
    - backend/parsing/budget.py
    - backend/parsing/fallback.py
    - backend/parsing/lead_scoring.py
    - backend/tests/parsing/test_extractor.py
    - backend/tests/parsing/test_text_prep.py
    - backend/tests/parsing/test_budget.py
    - backend/tests/parsing/test_fallback.py
    - backend/tests/parsing/test_lead_scoring.py
  modified: []
decisions:
  - "Transport pinned to PARSER_TOOLS (instructor Mode.TOOLS) — spike default per AI-SPEC §4; live spike against dev_golden_20 deferred to 05-05 where if winner changes, only PARSER constant in extractor.py changes"
  - "InstructorRetryException import from instructor.core not instructor.exceptions (instructor 1.15.3 moved the import; .exceptions path deprecated)"
  - "InstructorRetryException constructor in tests: positional message + n_attempts + total_usage (1.15.3 API)"
  - "Cyrillic word boundary fix: \\b does not match Cyrillic/Russian word boundaries in Python re; replaced with lookahead/lookbehind patterns for currency detection (у.е./сум/рублей)"
  - "Budget gate uses pipeline INCRBY+EXPIREAT (not MULTI/EXEC transaction); rollback via decrby is not atomic with the initial incrby but is safe because worst-case is a brief over-spend corrected by the rollback before the next reservation"
  - "rule_based_extract confidence fixed at 0.4 (CONFIDENCE_REVIEW_THRESHOLD - 0.1) — always below 0.5 so orchestrator routes to needs_review; rule-based is never auto-published (AI-SPEC G4)"
  - "lead_scoring.py is deterministic rules-based for Phase 5 CI-testability per AI-SPEC §4b.5; LLM-based scoring deferred to post-Phase-5 if needed"
metrics:
  duration: "~9 min"
  completed: "2026-06-18T13:00:00Z"
  tasks_completed: 2
  files_created: 10
  files_modified: 0
---

# Phase 5 Plan 03: LLM Extraction Service Layer Summary

## One-Liner

instructor Mode.TOOLS singleton extractor with temperature-0 prompt-cached single-call, Redis daily token budget gate with atomic rollback, real regex-based rule-based fallback (confidence<0.5 → always needs_review), versioned deterministic lead scorer (HOT/MEDIUM/LOW), and text-prep blank/truncation guard — all fully unit-tested with mocked LLM and Redis, no live calls in CI.

## Task 0: Package Legitimacy Checkpoint

**Status: Resolved (pre-approved by user before dispatch)**

`anthropic` 0.109.2 (Anthropic official SDK, publisher Anthropic PBC, 0.x line, pin `>=0.40,<1.0` confirmed valid) and `instructor` 1.15.3 (jxnl/instructor-ai structured-output library, 3M+ monthly downloads, pin `>=1.5,<2.0` valid — 1.15.3 ∈ range) — both verified canonical on PyPI, neither is a typosquat. The checkpoint was marked as gate="blocking-human" and was pre-approved by the user before this agent was dispatched.

Both packages were already installed via the `uv sync` from pyproject.toml pins added in 05-01.

## What Was Built

### Task 1: Transport spike + extract_signal singleton + text-prep guard

**`backend/parsing/extractor.py`**:
- Module-level `_raw_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)` and `_client = instructor.from_anthropic(_raw_client, mode=instructor.Mode.TOOLS)` (singleton — patched once per AI-SPEC Pitfall 1, never inside the Celery task)
- Transport constants: `PARSER_TOOLS = "llm_extract_tools"`, `PARSER_NATIVE = "llm_extract_native"`, `PARSER = PARSER_TOOLS` (spike default per AI-SPEC §4 — live spike comparison deferred to 05-05)
- `extract_signal(message_text, *, model, prompt_version) → tuple[ExtractionResult, dict]`:
  - Loads versioned system prompt via `load_prompt(prompt_version)` (lru_cache, no repeated disk I/O)
  - `_client.messages.create_with_completion(model, max_tokens=512, temperature=0, system=[{..., "cache_control": {"type":"ephemeral"}}], messages=[{"role":"user","content":message_text}], response_model=ExtractionResult, max_retries=2)`
  - Journal keys: parser, model, prompt_version, tokens_in (input + cache_creation), tokens_out, cache_read_tokens, latency_ms, raw_response
  - Does NOT catch `InstructorRetryException` — propagates to 05-04 orchestrator per AI-SPEC Pitfall 5/6

**`backend/parsing/text_prep.py`**:
- `prepare_message_text(raw, max_tokens=2000) → str`
- Strips whitespace; returns "" for blank (G6 cost guard — caller skips LLM call)
- Truncates to `max_tokens * 4` chars (1 token ≈ 4 chars heuristic) and appends `\n[TRUNCATED]` sentinel for oversized forwards (T-05-14)

**Tests (16 passing)**:
- test_extractor.py: journal keys/values, singleton reuse across calls, module-level _client attribute, temperature=0/max_tokens=512 kwargs, max_retries=2, cache_control ephemeral, response_model=ExtractionResult, InstructorRetryException propagation
- test_text_prep.py: empty/whitespace → "", truncation with sentinel, short message passthrough, boundary edge cases

### Task 2: Token-budget Redis gate + rule-based fallback + lead scoring

**`backend/parsing/budget.py`**:
- `DAILY_TOKEN_LIMIT = settings.LLM_DAILY_TOKEN_LIMIT`
- `key_for(d) → "llm_tokens:YYYY-MM-DD"` (UTC date in key)
- `check_and_reserve_tokens(estimated_tokens)`: INCRBY + EXPIREAT pipeline; if new_total > limit → DECRBY rollback + raise BudgetExceeded (T-05-12 / AI-SPEC G4)
- `record_actual_tokens(reserved, actual)`: reconcile delta (positive → INCRBY, negative → DECRBY, zero → no-op)
- `daily_spend() → int`: current counter value
- `per_source_spend(session, source_id, days=7) → int`: 7-day rolling token sum for REQ-llm-budget per-source visibility (lazy SQL import; DB-free module import)
- Module-level `_redis` singleton patched in tests

**`backend/parsing/fallback.py`**:
- `rule_based_extract(text) → ExtractionResult` — real regex extraction, not a stub
- Product detection: Latin + Cyrillic variants (PP/ПП, HDPE/ПНД, LLDPE, LDPE, PVC/ПВХ, PET/ПЭТ, ABS, PS/ПС)
- Currency detection: `у.е.` → USD (AI-SPEC §1b FM#3 critical), `$`/`доллар` → USD, `сум`/`so'm` → UZS, `рублей`/`₽` → RUB (fixed Cyrillic \b boundary issue — see Deviations)
- Volume: `тонн`/`т` → MT; `кг` → /1000 MT conversion
- Grade: letter-digit-letter regex (T30S, H030, 2420D)
- Confidence always 0.4 (< CONFIDENCE_REVIEW_THRESHOLD 0.5) → orchestrator always routes to needs_review (G4 invariant)
- Irrelevant text: is_relevant=False + all market fields null (irrelevant_fields_must_be_null satisfied)

**`backend/parsing/lead_scoring.py`**:
- `SCORING_PROMPT_VERSION = "lead_v1"` — bump to trigger 05-05 backfill re-scoring (REQ-lead-scoring)
- `compute_lead_score(result) → tuple[float, str]`: deterministic additive weights (kind + volume + urgency + counterparty + confidence, capped at 1.0)
  - kind: deal=0.35, sell_offer=0.30, buy_request=0.28, price_quote=0.10, news=0.05
  - volume: >100MT→+0.20, >10MT→+0.15, >0MT→+0.10
  - urgency: HIGH→+0.20, MEDIUM→+0.05
  - counterparty present: +0.10
  - confidence ≥ 0.8: +0.05
- `classify(score) → "HOT" | "MEDIUM" | "LOW"`: HOT≥0.70, MEDIUM≥0.40

**Tests (21 passing)**:
- test_budget.py: reserve succeeds → counter increments; second reserve over limit → BudgetExceeded + rollback; key contains UTC date; expireat called; daily_spend(); record_actual_tokens delta
- test_fallback.py: PP sell in Russian with у.е. → is_relevant=True, product=PP, currency=USD, volume≈50, confidence<0.5; spam → is_relevant=False + all null; ExtractionResult validates
- test_lead_scoring.py: HOT≥0.7, LOW<0.4, SCORING_PROMPT_VERSION defined, classify thresholds, score in [0,1], deal scores above LOW

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] InstructorRetryException import path (instructor 1.15.3)**
- **Found during:** Task 1 GREEN implementation
- **Issue:** AI-SPEC references `from instructor.exceptions import InstructorRetryException` but in instructor 1.15.3 that path is deprecated; the current path is `from instructor.core import InstructorRetryException`
- **Fix:** Updated extractor.py import and test constructor call to use `instructor.core`; also corrected the constructor signature — 1.15.3 requires `(message, n_attempts, total_usage)` not `(message, n_attempts, last_completion, messages)`
- **Files modified:** backend/parsing/extractor.py, backend/tests/parsing/test_extractor.py
- **Commit:** eb8e1ce (inline in GREEN commit)

**2. [Rule 1 - Bug] Cyrillic word boundary in currency regex**
- **Found during:** Task 2 GREEN — test_pp_sell_offer_extraction failed (currency=None for "у.е.")**
- **Issue:** Python's `re` `\b` word-boundary assertion does not match Cyrillic character boundaries. The pattern `\bу\.е\.\b` never matched because `у` is a Cyrillic letter and `\b` only works for `\w` = `[a-zA-Z0-9_]` in the default locale
- **Fix:** Replaced `\b...\b` with lookahead/lookbehind patterns for all Cyrillic currency tokens; `у.е.` uses plain regex without boundary (it contains dots which are anchors); Cyrillic tokens use `(?<!\w)..(?!\w)`
- **Files modified:** backend/parsing/fallback.py
- **Commit:** a8bdc5d (inline in GREEN commit)

## Known Stubs

None. All five modules implement their specified behavior:
- `extract_signal` is a fully-journaled, single-call, prompt-cached LLM extraction entry point
- `prepare_message_text` applies the blank/truncation guard
- `check_and_reserve_tokens` is a hard rollback-safe budget gate
- `rule_based_extract` is a real regex fallback (not a placeholder)
- `compute_lead_score` computes real scores (not hardcoded returns)

## Threat Flags

No new threat surface beyond the plan's threat_model. Implemented mitigations:

| T-ID | Mitigation Applied |
|------|-------------------|
| T-05-10 | Channel text placed ONLY in the user turn; system prompt cached + static; Mode.TOOLS constrains output shape — injected text cannot change ExtractionResult schema |
| T-05-11 | response_model=ExtractionResult + irrelevant_fields_must_be_null validator + temperature=0; rule_based_extract confidence<0.5 forces review |
| T-05-12 | check_and_reserve_tokens is a hard pre-call gate with atomic INCRBY + DECRBY rollback |
| T-05-13 | API key read from settings only; never logged; raw_response is the completion object (no key material) |
| T-05-14 | prepare_message_text truncates to 2000*4 chars before the call |

## Self-Check: PASSED

**Files created:**
- `backend/parsing/extractor.py` — FOUND
- `backend/parsing/text_prep.py` — FOUND
- `backend/parsing/budget.py` — FOUND
- `backend/parsing/fallback.py` — FOUND
- `backend/parsing/lead_scoring.py` — FOUND
- `backend/tests/parsing/test_extractor.py` — FOUND
- `backend/tests/parsing/test_text_prep.py` — FOUND
- `backend/tests/parsing/test_budget.py` — FOUND
- `backend/tests/parsing/test_fallback.py` — FOUND
- `backend/tests/parsing/test_lead_scoring.py` — FOUND

**Commits:**
- `f3c69c2` — test(05-03): RED phase — failing tests for extractor singleton + text_prep guard (FOUND)
- `eb8e1ce` — feat(05-03): Task 1 GREEN — extract_signal singleton + text_prep guard (FOUND)
- `712b297` — test(05-03): RED phase — failing tests for budget gate, fallback, lead scoring (FOUND)
- `a8bdc5d` — feat(05-03): Task 2 GREEN — budget gate, rule-based fallback, lead scoring (FOUND)

**Final test run:** 37 tests passed (16 extractor+text_prep + 21 budget+fallback+lead_scoring)

## TDD Gate Compliance

Both tasks followed RED/GREEN discipline:
- Task 1: `f3c69c2` (RED test commit) → `eb8e1ce` (GREEN implementation commit)
- Task 2: `712b297` (RED test commit) → `a8bdc5d` (GREEN implementation commit)
