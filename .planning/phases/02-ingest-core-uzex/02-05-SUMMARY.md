---
phase: 02-ingest-core-uzex
plan: "05"
subsystem: ingest
tags:
  - fx-rates
  - cbu-adapter
  - parse-task
  - signals
  - grade-extraction
dependency_graph:
  requires:
    - 02-01  # Celery app + beat schedule (fetch_cbu_rates placeholder)
    - 02-02  # relevance_service (match_product, queue_for_classification)
    - 02-03  # SourceAdapter registry + http_client (fetch_url)
  provides:
    - fx_rates idempotent daily import (REQ-fx-rates)
    - convert_amount on-read FX conversion
    - parse_raw_item signal pipeline (REQ-uzex-parser)
    - parse_runs provenance journaling
  affects:
    - signals table (new rows created by parse_raw_item)
    - fx_rates table (populated by fetch_cbu_rates)
    - manual_classification_queue (unrecognized goods routed here)
tech_stack:
  added:
    - app.ingest.cbu_rates.CbuRatesAdapter (type_name=cbu_rates, CBU JSON endpoint)
    - app.services.fx_service (upsert_fx_rates, convert_amount)
    - app.tasks.ingest_cbu.fetch_cbu_rates (Celery task, supersedes placeholder)
    - app.services.grade_service.extract_grade (regex + DB lookup)
    - app.services.signal_service.create_signal_from_parse
    - app.tasks.parse.parse_raw_item (Celery task, parse queue)
  patterns:
    - TDD RED/GREEN for both tasks
    - Strict Decimal parsing with try/except (T-02-15, never float/eval for money)
    - ON CONFLICT (rate_date, ccy) DO UPDATE for idempotent upsert
    - ORM + bound parameters only (T-02-16, no f-string SQL)
    - Per-item Celery task isolation (T-02-17)
    - parse_runs provenance journal with model=NULL (T-02-18)
    - Adapter self-registration at import time (DEC-source-adapter-registry)
key_files:
  created:
    - backend/app/ingest/cbu_rates/__init__.py
    - backend/app/ingest/cbu_rates/adapter.py
    - backend/app/services/fx_service.py
    - backend/app/tasks/ingest_cbu.py
    - backend/app/services/grade_service.py
    - backend/app/services/signal_service.py
    - backend/app/tasks/parse.py
    - backend/tests/test_cbu_rates.py
    - backend/tests/test_fx_conversion.py
    - backend/tests/test_parse_raw_item.py
  modified: []
decisions:
  - "CbuRatesAdapter._parse_cbu_json skips non-finite/negative rates (NaN, Inf, zero) in addition to malformed strings — aligns with T-02-15 money-precision requirement"
  - "Grade regex extended to \\d{2,4}[A-Z]{1,3} pattern to capture digit-leading grade codes like 2420D, 5030L (plan spec only showed letter-leading examples)"
  - "parse.py wrapper functions (match_product, queue_for_classification, create_signal_from_parse) kept as thin module-level functions so tests can patch them cleanly without deep mock chains"
  - "signal_service uses Mapping[str, object] for parsed arg (covariant) rather than dict[str, object] (invariant) to satisfy strict mypy without casts"
metrics:
  duration: "13 minutes"
  completed_date: "2026-06-15"
  tasks_completed: 2
  files_created: 10
  files_modified: 0
---

# Phase 02 Plan 05: FX Rates + Parse Pipeline Summary

FX rates daily import via CBU adapter with idempotent upsert and on-read conversion; rule-based UZEX parse pipeline routing polymer rows to signals, unrecognized goods to manual queue, with full provenance journaling in parse_runs.

## Tasks Completed

### Task 1: CBU rates adapter + fx_service (idempotent upsert + on-read conversion)

**Commits:**
- `60746cb` — test(02-05): add failing tests for CBU adapter + fx_service (RED)
- `6026093` — feat(02-05): CBU rates adapter + fx_service + fetch_cbu_rates task (GREEN)

**Files created:**
- `backend/app/ingest/cbu_rates/__init__.py` — package init, imports adapter for self-registration
- `backend/app/ingest/cbu_rates/adapter.py` — CbuRatesAdapter (type_name=cbu_rates); `_parse_cbu_json` with strict Decimal parsing + skip-on-malformed; self-registers at import; CbuRateRow dataclass
- `backend/app/services/fx_service.py` — `upsert_fx_rates` (INSERT ON CONFLICT DO UPDATE, idempotent); `convert_amount` (SELECT-only on-read conversion, original preserved)
- `backend/app/tasks/ingest_cbu.py` — real `fetch_cbu_rates` Celery task superseding placeholder; loads source, calls adapter, upserts via fx_service, updates last_fetch_at/last_success_at
- `backend/tests/test_cbu_rates.py` — CBU JSON parsing tests, adapter registration, live-DB upsert idempotency (guarded)
- `backend/tests/test_fx_conversion.py` — convert_amount math, missing-rate None, read-only assertion (unit + live-DB)

### Task 2: parse_raw_item — rule-based UZEX raw → signals

**Commits:**
- `a892765` — test(02-05): add failing tests for parse_raw_item pipeline (RED)
- `b04bb74` — feat(02-05): parse_raw_item task + grade_service + signal_service (GREEN)

**Files created:**
- `backend/app/services/grade_service.py` — `extract_grade(text, session)`: regex `[A-Z]{1,3}\d{2,4}[A-Z]{0,3}|\d{2,4}[A-Z]{1,3}` + case-insensitive DB lookup in product_grades; returns (grade_id|None, grade_text|None)
- `backend/app/services/signal_service.py` — `create_signal_from_parse`: builds Signal from parsed payload; section→kind mapping; Decimal coercion (T-02-15); Mapping[str, object] for covariance
- `backend/app/tasks/parse.py` — `parse_raw_item` Celery task; polymer→signal, unrecognized→queue (no consecutive_failures); every parse journals parse_runs (parser='uzex_table_v1', model=NULL); double-parse idempotency guard; per-item exception isolation (T-02-17)
- `backend/tests/test_parse_raw_item.py` — extract_grade (regex patterns, DB match, empty), create_signal (kind/fields/malformed), parse routing (polymer/irrelevant/unrecognized), parse_runs model=NULL, consecutive_failures guard, idempotency

## Verification Results

```
$ cd backend && python -m pytest tests/test_cbu_rates.py tests/test_fx_conversion.py tests/test_parse_raw_item.py -q
32 passed, 9 skipped, 1 warning in 0.43s
```

All unit tests pass. DB tests skip without live Postgres (guarded with `_IS_REAL_DB` flag). Full suite: 210 passed, 48 skipped.

Ruff + mypy clean on all touched files:
```
$ ruff check app/ingest/cbu_rates app/services/fx_service.py app/services/signal_service.py app/services/grade_service.py app/tasks/parse.py app/tasks/ingest_cbu.py
All checks passed!

$ mypy app/ingest/cbu_rates app/services/fx_service.py app/services/signal_service.py app/services/grade_service.py app/tasks/parse.py app/tasks/ingest_cbu.py
Success: no issues found in 6 source files
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Grade regex extended for digit-leading codes**
- **Found during:** Task 2 GREEN phase (test `test_extract_grade_regex_patterns` failed for `2420D`)
- **Issue:** Plan spec regex `[A-Z]{1,3}\d{2,4}[A-Z]{0,3}` only matches letter-leading grade codes; `2420D` (valid polymer grade) starts with digits and was not matched
- **Fix:** Extended regex to also match `\d{2,4}[A-Z]{1,3}` pattern via alternation: `[A-Z]{1,3}\d{2,4}[A-Z]{0,3}|\d{2,4}[A-Z]{1,3}`
- **Files modified:** `backend/app/services/grade_service.py`
- **Commit:** `b04bb74`

**2. [Rule 1 - Bug] Comment in parse.py triggered consecutive_failures guard test**
- **Found during:** Task 2 GREEN phase (test `test_unrecognized_does_not_increment_consecutive_failures`)
- **Issue:** Comment text "consecutive_failures is NEVER incremented here" matched the test's pattern search for `consecutive_failures` + `+` character (comment had both)
- **Fix:** Reworded comment to avoid false positive match while maintaining intent documentation
- **Files modified:** `backend/app/tasks/parse.py`
- **Commit:** `b04bb74`

**3. [Rule 1 - Bug] Test incorrectly identified mock signal as ParseRun**
- **Found during:** Task 2 GREEN phase (test `test_parse_writes_parse_run_with_model_null`)
- **Issue:** MagicMock auto-creates `.parser` and `.model` attributes; the mock signal was found before the real ParseRun in added_objects
- **Fix:** Updated test to check `isinstance(obj, ParseRun)` instead of duck-typing
- **Files modified:** `backend/tests/test_parse_raw_item.py`
- **Commit:** `b04bb74`

**4. [Rule 2 - Missing Critical] Mapping[str, object] for signal_service parsed arg**
- **Found during:** Task 2 mypy strictness check
- **Issue:** `dict[str, object]` is invariant; passing `dict[str, int | str | None]` fails strict mypy check
- **Fix:** Changed `parsed` parameter type to `Mapping[str, object]` (covariant) in both signal_service.create_signal_from_parse and the wrapper in parse.py
- **Files modified:** `backend/app/services/signal_service.py`, `backend/app/tasks/parse.py`
- **Commit:** `b04bb74`

## Known Stubs

None — all symbols are fully implemented:
- `CbuRatesAdapter.fetch()` returns proper RawItemDraft list
- `upsert_fx_rates` executes real SQL upsert
- `convert_amount` executes real SQL SELECT
- `parse_raw_item` routes through real services
- `create_signal_from_parse` builds real Signal ORM objects
- `extract_grade` applies real regex and real DB lookup

## Threat Flags

No new threat surface beyond what the plan's threat model covers.

| Flag | File | Description |
|------|------|-------------|
| (none) | — | All new surfaces (CBU fetch, fx_rates upsert, signal creation) are within the plan's T-02-15..T-02-18 threat register |

## Self-Check: PASSED

Files exist:
- backend/app/ingest/cbu_rates/__init__.py: FOUND
- backend/app/ingest/cbu_rates/adapter.py: FOUND
- backend/app/services/fx_service.py: FOUND
- backend/app/tasks/ingest_cbu.py: FOUND
- backend/app/services/grade_service.py: FOUND
- backend/app/services/signal_service.py: FOUND
- backend/app/tasks/parse.py: FOUND
- backend/tests/test_cbu_rates.py: FOUND
- backend/tests/test_fx_conversion.py: FOUND
- backend/tests/test_parse_raw_item.py: FOUND

Commits exist (verified via git log):
- 60746cb: test(02-05): add failing tests for CBU adapter + fx_service (RED)
- 6026093: feat(02-05): CBU rates adapter + fx_service + fetch_cbu_rates task (GREEN)
- a892765: test(02-05): add failing tests for parse_raw_item pipeline (RED)
- b04bb74: feat(02-05): parse_raw_item task + grade_service + signal_service (GREEN)
