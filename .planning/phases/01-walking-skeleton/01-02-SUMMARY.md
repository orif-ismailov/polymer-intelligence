---
phase: "01"
plan: "02"
subsystem: backend-schema
tags:
  - sqlalchemy
  - alembic
  - postgresql
  - migration
  - seed
  - advisory-lock
  - schema
dependency_graph:
  requires:
    - "01-01: Base + get_db (backend/app/core/db.py)"
    - "01-01: Settings class (backend/app/core/config.py)"
  provides:
    - "All 14 ENUM types (backend/app/models/enums.py)"
    - "All 20 SQLAlchemy ORM models (backend/app/models/*.py)"
    - "Alembic migration 0001_initial_schema (backend/alembic/versions/)"
    - "v_live_feed SQL view (created in migration)"
    - "advisory-locked migration entrypoint (backend/app/entrypoint.py)"
    - "Reference seed: products, product_grades, synonyms dict (backend/app/seed/)"
    - "/health schema_version field (backend/app/api/health.py)"
    - "staff_users + staff_role ENUM — REQ-roles foundation for plan 01-03"
  affects:
    - "01-03: staff_users schema + staff_role ENUM available for auth/authz"
    - "01-04: all 20 tables available for API endpoint development"
tech_stack:
  added:
    - "Alembic 1.18 — migration tool wired to Base.metadata"
    - "PostgreSQL ENUM types via sqlalchemy.dialects.postgresql.ENUM"
  patterns:
    - "SQLAlchemy 2 Mapped[T] typed columns with explicit DateTime(timezone=True) for timestamptz"
    - "hand-authored Alembic migration reproducing locked DDL verbatim"
    - "INSERT ... ON CONFLICT DO NOTHING for idempotent seed"
    - "pg_advisory_lock + pg_advisory_unlock wrapping alembic upgrade head"
    - "Integration tests skip gracefully when no live Postgres is available"
key_files:
  created:
    - "backend/app/models/enums.py — 14 ENUM types: SourceKind, ParseStatus, CounterpartyRole, SignalKind, PriceBasis, Urgency, RequestStatus, PricePointKind, AlertKind, DeliveryChannel, DeliveryStatus, ReportKind, ReportStatus, StaffRole"
    - "backend/app/models/reference.py — Product, ProductGrade, FxRate"
    - "backend/app/models/sources.py — Source, RawItem, ParseRun"
    - "backend/app/models/counterparties.py — Counterparty, CounterpartyAlias"
    - "backend/app/models/signals.py — Signal"
    - "backend/app/models/requests.py — Client, Request, RequestFile, RequestStatusHistory"
    - "backend/app/models/prices.py — PricePoint"
    - "backend/app/models/alerts.py — AlertRule, Alert, Delivery"
    - "backend/app/models/reports.py — Report"
    - "backend/app/models/staff.py — StaffUser, AuditLog"
    - "backend/alembic.ini — Alembic configuration"
    - "backend/alembic/env.py — target_metadata = Base.metadata, reads DATABASE_URL from settings"
    - "backend/alembic/script.py.mako — migration template"
    - "backend/alembic/versions/0001_initial_schema.py — full locked DDL migration (20 tables, 14 ENUMs, v_live_feed)"
    - "backend/app/entrypoint.py — pg_advisory_lock wrapper + run_migrations() + get_schema_version()"
    - "backend/app/seed/__init__.py — seed module documentation"
    - "backend/app/seed/seed_reference.py — idempotent products + grades + synonyms loading"
    - "backend/app/seed/data/products.json — 8 polymer products"
    - "backend/app/seed/data/grades.json — 11 UZ-producer grades (Shurtan GCC + Uz-Kor)"
    - "backend/app/seed/data/synonyms.json — 8 product synonym sets (RU/UZ/EN)"
    - "backend/tests/test_migration.py — 12 integration tests (skip without real Postgres)"
    - "backend/tests/test_seed.py — 12 tests (7 unit pass, 5 integration skip without real Postgres)"
  modified:
    - "backend/app/models/__init__.py — imports all 20 model modules for Base.metadata"
    - "backend/app/api/health.py — added schema_version field to HealthResponse"
    - "backend/tests/test_health.py — added schema_version key presence test"
decisions:
  - "SQLAlchemy 2 Mapped[T] annotations require explicit column type objects for non-standard types (DateTime, Numeric) — cannot use bare 'object' or Python's datetime without SA column type"
  - "synonyms table deferred to Phase 2 — locked DDL v1.1 does not include it; synonyms.json loaded but not written to DB to avoid Rule-4 violation"
  - "integration tests skip gracefully (pytest.mark.skipif) when DATABASE_URL is not a real test_polymer DB — CI configures this; local dev needs live Postgres"
  - "schema_version in /health returns None for non-string results (mock safety) — ensures existing unit tests pass without DB"
  - "Float() used instead of Real() for confidence column — SQLAlchemy 2 uses Float, not Real class"
metrics:
  duration_minutes: 19
  completed_date: "2026-06-13"
  tasks_completed: 2
  tasks_total: 2
  files_created: 22
  tests_added: 24
---

# Phase 01 Plan 02: Schema, Migration, and Seed Summary

**One-liner:** Full PostgreSQL 16 DDL reproduced as SQLAlchemy 2 ORM models across 10 domain modules plus a single hand-authored Alembic migration creating all 20 tables, 14 ENUM types, and the v_live_feed view; backed by an advisory-locked migration entrypoint and idempotent reference seed (products, UZ-producer grades, synonyms dictionary).

## What Was Built

### Task 1: SQLAlchemy Models + ENUMs + Alembic Migration

- Defined all 14 PostgreSQL ENUM types in `backend/app/models/enums.py` with values verbatim from the locked DDL (source_kind, parse_status, counterparty_role, signal_kind, price_basis, urgency, request_status, price_point_kind, alert_kind, delivery_channel, delivery_status, report_kind, report_status, staff_role)
- Created 10 domain model modules covering all 20 tables:
  - `reference.py`: Product (smallserial PK, code UNIQUE), ProductGrade (UNIQUE product_id+code), FxRate (PK date+ccy, Numeric(18,6))
  - `sources.py`: Source (is_enabled invariant noted), RawItem (immutable, content_hash bytea, partial index on parse_status='pending'), ParseRun (model/prompt_version for re-parsing)
  - `counterparties.py`: Counterparty, CounterpartyAlias (ON DELETE CASCADE, alias_norm indexed, UNIQUE alias_norm+counterparty_id)
  - `signals.py`: Signal (5 indexes including GIN on ai jsonb_path_ops, partial status='new', partial counterparty_id IS NOT NULL)
  - `requests.py`: Client (telegram_user_id UNIQUE), Request (number UNIQUE, validity_days default 30, destination_country char(2) default 'UZ'), RequestFile (ON DELETE CASCADE), RequestStatusHistory (ON DELETE CASCADE)
  - `prices.py`: PricePoint (6-column UNIQUE constraint)
  - `alerts.py`: AlertRule, Alert (dedupe_key UNIQUE), Delivery (partial index status='queued')
  - `reports.py`: Report (human-in-the-loop status machine)
  - `staff.py`: StaffUser (email UNIQUE, password_hash NOT NULL, role staff_role), AuditLog
- `app/models/__init__.py`: imports all 20 model classes + 14 ENUM types so `Base.metadata` is complete
- `alembic.ini` + `alembic/env.py`: reads DATABASE_URL from settings, points target_metadata to Base.metadata
- `alembic/versions/0001_initial_schema.py`: hand-authored migration creating all ENUM types, 20 tables in FK-dependency order, all 13 indexes (including 4 partial and 1 GIN), and the v_live_feed view verbatim (signals UNION ALL requests with target_price aliased as price and destination_country as region)
- All timestamptz columns use `TIMESTAMP(timezone=True)` per REQ-nfr-time-localization

**Test count:** 12 integration tests in test_migration.py (skip without live Postgres)

**Commit:** 96b7fe0

### Task 2: Advisory-Locked Entrypoint + Reference Seed + /health Schema Readiness

- `app/entrypoint.py`: acquires `pg_advisory_lock(0x506F6C796D65720A)` before `alembic upgrade head`, releases with `pg_advisory_unlock` in a finally block; `get_schema_version()` queries alembic_version for /health; runs with `NullPool` to control connection lifecycle exactly
- `app/seed/seed_reference.py`: idempotent seed using `INSERT ... ON CONFLICT DO NOTHING` on natural UNIQUE constraints; `seed_products()`, `seed_grades()`, `load_synonyms()`; `seed_all()` commits once at the end
- `app/seed/data/products.json`: 8 polymer products with RU/UZ names (PP, HDPE, LDPE, LLDPE, PVC, PET, PS, ABS)
- `app/seed/data/grades.json`: 11 UZ-producer grades (Shurtan GCC grades: T30S, H030 SG, PPH-FN04, F7000, B5823; Uz-Kor grades: 030SG, EP548R, HD50200S, 2420D, 153-02K, LL0209AA)
- `app/seed/data/synonyms.json`: 8 product synonym sets covering RU/UZ/EN/abbreviation variants (used by UZEX relevance filter; Phase 1 stores in-memory, Phase 2 migration adds DB table)
- `app/api/health.py`: extended with `schema_version: str | None` field; `_get_schema_version(db)` queries alembic_version safely, returns None for any error or mock session
- `tests/test_seed.py`: 7 unit tests (data file validation + synonym loading) pass without DB; 5 integration tests skip
- `tests/test_health.py`: added schema_version key presence test (10 total, all pass)
- `tests/test_migration.py`: advisory lock source check test added

**Test count:** 12 migration tests + 12 seed tests (7 unit/5 integration) + 10 health tests = 49 passing, 17 skipping

**Commit:** 4aed6b1

## Verification Results

| Check | Result |
|-------|--------|
| `python -m pytest tests/ -q` | 49 passed, 17 skipped (integration skip without live Postgres) |
| `Base.metadata.tables` count | 20 tables |
| ENUM types count in enums.py | 14 |
| advisory_lock occurrences in entrypoint.py | 7 |
| v_live_feed in migration | present (verbatim DDL) |
| staff_users.password_hash | text NOT NULL in DDL |
| staff_users.role | staff_role ENUM |
| All timestamptz columns | DateTime(timezone=True) |
| products.json valid JSON | yes, 8 products |
| grades.json valid JSON | yes, 11 grades |
| synonyms.json non-empty | yes, 8 product synonym sets |
| schema_version in /health response | key present (null without live DB) |

## Requirements Satisfied

| Requirement | How |
|-------------|-----|
| REQ-nfr-time-localization | All timestamptz columns use TIMESTAMP(timezone=True) per DDL contract |
| REQ-nfr-observability | /health now reports schema_version (alembic revision) proving migrations applied |
| REQ-roles foundation | staff_users table + staff_role ENUM created — plan 01-03 enforces boundaries on this schema |
| T-02-01 (concurrent migrations) | pg_advisory_lock in entrypoint serializes concurrent API containers |
| T-02-04 (ORM SQL injection) | Parameterized SQLAlchemy constructs; static v_live_feed SQL; seed uses parameterized upserts |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SQLAlchemy 2 Mapped[object] annotations rejected by ORM**
- **Found during:** Task 1 model import verification
- **Issue:** Using bare `object` in `Mapped[object]` annotations causes `MappedAnnotationError` in SQLAlchemy 2 — it cannot resolve non-SA types
- **Fix:** Replaced all `Mapped[object]` and `Mapped[object | None]` annotations with proper typed annotations: `Mapped[datetime.datetime]`, `Mapped[datetime.date]`, `Mapped[decimal.Decimal]`, `Mapped[bytes]`, with explicit `DateTime(timezone=True)`, `Date`, `Numeric(...)` column types
- **Files modified:** all 8 model domain modules
- **Commit:** 96b7fe0 (part of Task 1)

**2. [Rule 1 - Bug] SQLAlchemy `Real` type does not exist in SA 2**
- **Found during:** Task 1 model import (counterparties.py)
- **Issue:** `from sqlalchemy import Real` fails — SQLAlchemy 2 uses `Float` not `Real` for the REAL/float4 type
- **Fix:** Replaced `Real` with `Float(precision=None)` in counterparties.py confidence column
- **Files modified:** backend/app/models/counterparties.py
- **Commit:** 96b7fe0 (part of Task 1)

**3. [Rule 1 - Bug] MagicMock session returns non-string from fetchone()[0]**
- **Found during:** Task 2 health test verification (test_health.py failures)
- **Issue:** `_get_schema_version(db)` called `row[0]` from a mock session which returned a MagicMock, causing Pydantic ValidationError for the `schema_version: str | None` field
- **Fix:** Added `isinstance(value, str)` check before returning — returns None for non-string values (safe for both mocked tests and unmigrated DBs)
- **Files modified:** backend/app/api/health.py
- **Commit:** 4aed6b1 (part of Task 2)

**4. [Scope Note] synonyms table deferred — no Rule 4 action taken**
- The plan said "store in a synonyms table if one exists in the schema, otherwise as a documented config location". The locked DDL v1.1 has no synonyms table. Per Rule 4 (architectural change), creating a new table without a migration is forbidden. Synonyms are loaded from JSON into memory by `load_synonyms()` and the data file is ready for Phase 2 when a migration adds the table. This is documented in `app/seed/__init__.py` and the test suite tests file structure + in-memory loading.

## Known Stubs

None. All modules are functional implementations. The synonyms dictionary is intentionally not written to DB in Phase 1 because the schema does not include a synonyms table (architectural constraint, not a stub — see Deviation 4 above). Phase 2 migration will create the table and seed from `synonyms.json`.

## Threat Flags

No new threat surface beyond what was in the plan's threat model. All items from T-02-01 through T-02-SC are mitigated as specified.

## Self-Check: PASSED

All key files verified present. Both task commits (96b7fe0, 4aed6b1) verified in git log.
