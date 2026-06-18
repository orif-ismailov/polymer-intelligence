---
phase: 05-telegram-monitoring-ai
plan: "01"
subsystem: backend/parsing
tags:
  - ai-extraction
  - pydantic-schema
  - alembic-migration
  - phase5-contract
dependency_graph:
  requires:
    - "backend/app/models/enums.py (SignalKind, Urgency DB ENUM values)"
    - "backend/alembic/versions/0002_synonyms_and_classification_queue.py (down_revision chain)"
    - "backend/app/core/config.py (Settings LLM env vars)"
  provides:
    - "backend/parsing/schemas.py::ExtractionResult (Pydantic schema)"
    - "backend/parsing/schemas.py::SignalKind, UrgencyLevel, FieldConfidence, BudgetExceeded, CONFIDENCE_REVIEW_THRESHOLD"
    - "backend/parsing/prompts/loader.py::load_prompt(version) -> str"
    - "backend/parsing/prompts/extract_v1.md (immutable v1 system prompt)"
    - "docs/extraction-schema.json (published fixed schema, ROADMAP SC#2)"
    - "backend/alembic/versions/0003_phase5_ai_extraction.py (revision 0003)"
    - "parse_runs.latency_ms column (migrated)"
    - "ix_parse_runs_llm_created partial index"
    - "LLM_PROMPT_VERSION config setting"
  affects:
    - "backend/app/models/sources.py::ParseRun (latency_ms column added)"
    - "backend/app/core/config.py (LLM_PROMPT_VERSION added)"
    - "backend/pyproject.toml (3 new deps + parsing* package include + mypy overrides)"
    - "deploy/.env.example (LLM_PROMPT_VERSION)"
tech_stack:
  added:
    - "anthropic>=0.40,<1.0 (Anthropic Python SDK — dep pin; install gated to 05-02/05-03)"
    - "instructor>=1.5,<2.0 (structured outputs wrapper — dep pin only)"
    - "telethon>=1.36,<2.0 (MTProto userbot client — dep pin only)"
    - "parsing Python package (backend/parsing/)"
  patterns:
    - "Pydantic 2 ExtractionResult with model_validator + field_validator"
    - "functools.lru_cache(maxsize=16) on prompt loader"
    - "Alembic partial index (postgresql_where)"
    - "TDD RED/GREEN commit flow"
key_files:
  created:
    - backend/parsing/__init__.py
    - backend/parsing/schemas.py
    - backend/parsing/prompts/__init__.py
    - backend/parsing/prompts/loader.py
    - backend/parsing/prompts/extract_v1.md
    - docs/extraction-schema.json
    - backend/alembic/versions/0003_phase5_ai_extraction.py
    - backend/tests/parsing/__init__.py
    - backend/tests/parsing/test_schemas.py
    - backend/tests/parsing/test_prompt_loader.py
    - backend/tests/test_migration_0003.py
  modified:
    - backend/app/models/sources.py (ParseRun.latency_ms column added)
    - backend/app/core/config.py (LLM_PROMPT_VERSION setting added)
    - backend/pyproject.toml (3 deps + parsing* include + mypy overrides)
    - deploy/.env.example (LLM_PROMPT_VERSION=v1)
decisions:
  - "ExtractionResult.event_at is Optional[str] (not Optional[datetime]) — avoids timezone conversion complexity in the extraction schema; downstream consumers parse to datetime as needed"
  - "ExtractionResult.is_forwarded default=False — set by userbot layer from Telethon fwd_from, not by LLM; schema carries it for completeness"
  - "Migration 0003 does NOT add columns to signals table — lead_score/needs_review/scored_at live in signals.ai JSONB per db-architecture §4; no signals table change needed"
  - "extract_v1.md padded to 277 lines with field reference table and 3 annotated few-shot examples to approach 4096-token caching threshold for Claude Haiku 4.5"
  - "test_migration_0003.py is OFFLINE only — live alembic upgrade head deferred to deploy-time drill per established phase UAT deferral pattern"
metrics:
  duration: "~25 min"
  completed: "2026-06-18T12:40:00Z"
  tasks_completed: 2
  files_created: 11
  files_modified: 4
---

# Phase 5 Plan 01: AI Extraction Contract — Schema, Prompt, Migration Summary

## One-Liner

Phase 5 extraction contract: `ExtractionResult` Pydantic schema with enum parity + irrelevant-fields validator, immutable versioned `extract_v1.md` prompt with 3 few-shot examples, `load_prompt()` lru-cached loader, `docs/extraction-schema.json` published JSON schema, three dep pins (`anthropic`, `instructor`, `telethon`), and Alembic migration `0003` adding `parse_runs.latency_ms` + `ix_parse_runs_llm_created` partial index.

## What Was Built

### Task 1 (TDD): Extraction schema, versioned prompt, loader, deps, published JSON schema

**`backend/parsing/` package** (new top-level backend package alongside `app/`):

- **`parsing/schemas.py`** — `ExtractionResult(BaseModel)` with 17 fields. Key validators:
  - `normalise_currency`: uppercase + regex fullmatch `[A-Z]{3}` — rejects "DOLLAR", "US", normalizes "usd" → "USD"
  - `irrelevant_fields_must_be_null`: model_validator blocks fabricated values when `is_relevant=False` (threat T-05-01)
  - `SignalKind`: `buy_request | sell_offer | deal | price_quote | news` — exact parity with `app.models.enums.SignalKind`
  - `UrgencyLevel`: `low | medium | high` — exact parity with `app.models.enums.Urgency`
  - `FieldConfidence`: per-field 0.0–1.0 confidence for eval precision metrics
  - `BudgetExceeded(Exception)` sentinel
  - `CONFIDENCE_REVIEW_THRESHOLD = 0.5`
  - `event_at: Optional[str]` for stale-repost handling (AI-SPEC §1b FM#5 / D14)
  - `is_forwarded: bool = False` (set by userbot layer, not LLM)

- **`parsing/prompts/loader.py`** — `load_prompt(version: str) -> str`, `@functools.lru_cache(maxsize=16)`, raises `FileNotFoundError` on unknown version, module docstring states append-only rule.

- **`parsing/prompts/extract_v1.md`** — 277-line immutable v1 system prompt including:
  - Task description (classify + extract)
  - Full field reference table with null semantics
  - Currency mapping table (у.е. → USD, сум → UZS, ₽ → RUB)
  - Signal kind rules (Куплю → buy_request, etc.)
  - Volume normalisation (кг → /1000)
  - Urgency rules
  - Prompt-injection defense section (user turn is untrusted data, not instructions — T-05-04)
  - 3 annotated few-shot examples (full sell_offer, partial buy_request with nulls, irrelevant forwarded news)

- **`docs/extraction-schema.json`** — `ExtractionResult.model_json_schema()` output, pretty-printed, with `$comment` noting generated source (ROADMAP SC#2 published fixed schema).

**`backend/pyproject.toml`** updates:
  - 3 runtime dep pins: `anthropic>=0.40,<1.0`, `instructor>=1.5,<2.0`, `telethon>=1.36,<2.0` (install gated to 05-02/05-03 legitimacy checkpoints — all three verified canonical on PyPI)
  - `[tool.setuptools.packages.find].include` extended from `["app*"]` to `["app*", "parsing*"]`
  - `[[tool.mypy.overrides]]` for `instructor.*` and `telethon.*` (`ignore_missing_imports = true`)

**`backend/app/core/config.py`**: Added `LLM_PROMPT_VERSION: str = "v1"`.
**`deploy/.env.example`**: Added `LLM_PROMPT_VERSION=v1`.

**Tests (21 passing):**
  - `test_schemas.py`: ExtractionResult validation, irrelevant-fields validator, currency normalisation, confidence bounds, enum parity guard
  - `test_prompt_loader.py`: v1 returns non-empty str with "is_relevant" and "null"; unknown version → FileNotFoundError; lru_cache identity; JSON schema has required fields

### Task 2 (BLOCKING): Alembic migration 0003

**`backend/alembic/versions/0003_phase5_ai_extraction.py`**:
  - `revision = "0003"`, `down_revision = "0002"` — chain: 0001 → 0002 → 0003
  - `upgrade()`: `op.add_column("parse_runs", latency_ms Integer NULL)` + `op.create_index("ix_parse_runs_llm_created", ["created_at"], WHERE parser='llm_extract')`
  - `downgrade()`: drops index then column (correct dependency order)
  - NO `signals` table changes — lead_score/needs_review/scored_at live in `signals.ai` JSONB per db-architecture §4

**`backend/app/models/sources.py`**: `ParseRun.latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)` added with parser discriminator comment.

**Tests (10 passing, offline):**
  - `test_migration_0003.py`: revision chain asserts, upgrade/downgrade callable, alembic walk includes 0002+0003, 0003 is head, ORM latency_ms column type/nullable, no signals table modification

**Deploy-time note:** Live `alembic upgrade head` + `\d parse_runs` verification deferred to deploy-time DB drill per established phase UAT deferral pattern (consistent with phases 2/3/4).

## Deviations from Plan

None — plan executed exactly as written.

The one auto-applied Rule 1 fix: `test_migration_0003_only_touches_parse_runs` regex was too greedy (matched index name `ix_parse_runs_llm_created` as table), fixed inline before committing the test.

## Known Stubs

None. This plan creates the contract layer only — no UI rendering, no LLM calls, no data flow. All fields are typed; no placeholder values. The `lead_score` field defaults to `None` as per spec (populated by lead-scoring pass, not extraction).

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`. The implemented mitigations:
- T-05-01: `irrelevant_fields_must_be_null` + `normalise_currency` validators implemented
- T-05-03: down_revision pinned to "0002"; offline test asserts chain
- T-05-04: prompt explicitly declares user turn as untrusted data (prompt-injection defense)
- T-05-SC: package pins added; install gated to 05-02/05-03 legitimacy checkpoints

## Self-Check: PASSED

All key files verified present. All task commits verified:
- `273c4c0` — test(05-01): RED phase failing tests
- `90ef636` — feat(05-01): GREEN phase implementation (schema + prompt + loader + deps + JSON schema)
- `c21e67e` — feat(05-01): BLOCKING migration 0003

Final test run: 31 tests passed (21 schema/loader + 10 migration offline).
