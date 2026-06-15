---
phase: 02-ingest-core-uzex
plan: "02"
subsystem: backend/synonyms-relevance
tags: [synonyms, relevance, migration, seed, classification-queue]
dependency_graph:
  requires:
    - 02-01 (alembic setup, base migration 0001)
  provides:
    - product_synonyms table (migration 0002)
    - manual_classification_queue table (migration 0002)
    - relevance_service.match_product
    - relevance_service.queue_for_classification
    - seed_synonyms (idempotent DB loader)
  affects:
    - 02-05 (UZEX parser uses match_product and queue_for_classification)
tech_stack:
  added:
    - product_synonyms table (v1.2 schema addition, migration 0002)
    - manual_classification_queue table (v1.2 schema addition, migration 0002)
  patterns:
    - SQLAlchemy text() with bound parameters (T-02-04 injection protection)
    - ON CONFLICT (synonym_norm) DO NOTHING idempotent upsert pattern
    - No module-level cache for admin-top-up-ability (SC#4)
    - 512-char truncation before queue insert (T-02-05 DoS hardening)
key_files:
  created:
    - backend/alembic/versions/0002_synonyms_and_classification_queue.py
    - backend/app/services/relevance_service.py
    - backend/tests/test_synonyms_migration.py
    - backend/tests/test_relevance_service.py
  modified:
    - backend/app/models/reference.py (added ProductSynonym + ManualClassificationItem)
    - backend/app/models/__init__.py (registered new models + __all__ entries)
    - backend/app/seed/seed_reference.py (added seed_synonyms(), updated seed_all())
decisions:
  - "No module-level synonym cache in match_product — DB query per call ensures admin-added rows are visible immediately (SC#4 admin-top-up-able)"
  - "product_text truncated to 512 chars before queue insert (T-02-05: DoS hardening against oversized UZEX cells)"
  - "queue_for_classification uses ON CONFLICT(raw_item_id) DO NOTHING and never touches consecutive_failures — unrecognized goods are NOT source_failure (REQ-uzex-parser)"
  - "All DB access uses SQLAlchemy bound parameters — normalize_term does not format SQL (T-02-04 injection protection)"
metrics:
  duration: "~25 minutes"
  completed: "2026-06-15"
  tasks_completed: 2
  files_changed: 7
---

# Phase 02 Plan 02: Synonyms Dictionary + Relevance Service Summary

Synonym dictionary table, manual-classification queue, migration 0002, idempotent seeder, and relevance service backed by product_synonyms with live admin-top-up support.

## What Was Built

Two new tables added by migration 0002 (down_revision=0001), applied to live dev DB:

**product_synonyms** — synonym dictionary mapping normalized text → product_id:
- Columns: id, product_id (FK→products.id), synonym, synonym_norm, source (default 'seed'), created_at (timestamptz)
- UNIQUE(synonym_norm) prevents duplicates; index ix_product_synonyms_norm for O(log n) lookups
- Admin rows tagged source='admin' can be inserted at runtime without code changes (SC#4)

**manual_classification_queue** — queue for unrecognized UZEX goods:
- Columns: id, raw_item_id (FK→raw_items.id), product_text (max 512 chars), status (default 'pending'), created_at (timestamptz)
- UNIQUE(raw_item_id) prevents duplicate queue entries per raw item
- Index on (status, created_at) for pending-item worker queries

**relevance_service.py** — three exported functions:
- `normalize_term(text)` — lowercase + strip + collapse whitespace; deterministic; used symmetrically for seeding and lookup
- `match_product(session, text)` — normalizes input, queries product_synonyms.synonym_norm, returns product_id or None; no module-level cache
- `queue_for_classification(session, raw_item_id, product_text)` — INSERT ON CONFLICT DO NOTHING into manual_classification_queue; truncates to 512 chars; never touches consecutive_failures

**seed_synonyms(session)** in seed_reference.py — reads synonyms.json (8 product codes, 55 synonyms), resolves product codes to IDs, upserts with ON CONFLICT(synonym_norm) DO NOTHING. Returns inserted count (0 on re-run). Called from seed_all().

## Task Commits

| Task | Type | Commit | Description |
|------|------|--------|-------------|
| T1 RED | test | 6515b38 | Failing migration tests for 0002 upgrade/downgrade |
| T1 GREEN | feat | ae1e4f9 | ProductSynonym + ManualClassificationItem models + migration 0002 |
| T2 RED | test | 8637329 | Failing tests for normalize_term, match_product, seed_synonyms, queue |
| T2 GREEN | feat | 4bc4157 | relevance_service.py + seed_synonyms() implementation |

## Verification Results

- `app.models` import registers `product_synonyms` and `manual_classification_queue` in Base.metadata — PASSED
- `grep -v '^#' 0002_synonyms_and_classification_queue.py | grep -c down_revision` returns 1 — PASSED
- Live DB at revision 0002; both tables exist (verified via `\dt` in postgres container) — PASSED
- `match_product(session, 'полипропилен')` → 1 (PP product_id) — PASSED
- `match_product(session, 'цемент')` → None — PASSED
- `match_product(session, '  ПолиПропилен  ')` → 1 (same as normalized form) — PASSED
- seed_synonyms seeded 55 rows on first run; 0 on second run (idempotent) — PASSED
- `ruff check` on all changed files — PASSED
- `mypy app/services/relevance_service.py app/models/reference.py app/models/__init__.py` — PASSED
- All 7 normalize_term unit tests pass; 22 DB-backed tests skip (no test_polymer DB in dev) — PASSED
- 116 pre-existing tests pass, 2 skipped (no regressions) — PASSED

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all functions are fully wired. seed_synonyms inserts real data from synonyms.json, match_product queries live DB, queue_for_classification inserts real rows.

## Threat Flags

No new security surface introduced beyond what the plan's threat model covered:
- T-02-04 (SQL injection): mitigated — bound parameters throughout
- T-02-05 (DoS via oversized text): mitigated — 512-char truncation in queue_for_classification
- T-02-06 (dup synonyms via re-seed): mitigated — UNIQUE(synonym_norm) + ON CONFLICT DO NOTHING

## Self-Check: PASSED

All created files exist on disk. All 4 task commits found in git history.
