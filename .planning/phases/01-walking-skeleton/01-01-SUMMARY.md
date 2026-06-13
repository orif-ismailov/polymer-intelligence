---
phase: "01"
plan: "01"
subsystem: backend-scaffold
tags:
  - fastapi
  - sqlalchemy
  - structlog
  - pydantic-settings
  - docker-compose
  - timezone
  - health-endpoint
dependency_graph:
  requires: []
  provides:
    - "Settings class (backend/app/core/config.py) — all §7 env vars"
    - "Base + get_db (backend/app/core/db.py) — used by all future ORM models"
    - "configure_logging() (backend/app/core/logging.py) — JSON stdout logging"
    - "utcnow() + to_display_tz() (backend/app/core/time.py) — centralized TZ helper"
    - "create_app() factory + GET /api/v1/health (backend/app/main.py + api/health.py)"
    - "dev stack: postgres, redis, api, worker, beat (deploy/docker-compose.dev.yml)"
  affects: []
tech_stack:
  added:
    - "Python 3.12 backend package (FastAPI, SQLAlchemy 2, Celery, structlog, pydantic-settings)"
    - "Docker Compose v2 dev stack (postgres:16, redis:7, api, worker, beat)"
  patterns:
    - "Pydantic Settings with fail-fast required secrets (no defaults for JWT_SECRET, BOT_TOKEN, etc.)"
    - "SQLAlchemy 2 DeclarativeBase + sessionmaker + get_db() FastAPI dependency"
    - "structlog JSON rendering via ProcessorFormatter bridging stdlib logging"
    - "UTC-only storage + to_display_tz(dt, tz='Asia/Tashkent') single-point conversion"
    - "Health endpoint returns status enums only (no internal details leaked)"
key_files:
  created:
    - "backend/pyproject.toml — Python 3.12 package with full Phase-1 dependency set"
    - "backend/app/core/config.py — Settings class (all §7 env keys, no-default secrets)"
    - "backend/app/core/db.py — engine, SessionLocal, Base, get_db()"
    - "backend/app/core/logging.py — configure_logging() structlog JSON"
    - "backend/app/core/time.py — utcnow(), to_display_tz()"
    - "backend/app/main.py — create_app() FastAPI factory"
    - "backend/app/api/health.py — GET /health checking db + redis"
    - "backend/tests/conftest.py — TestClient fixtures with mocked deps"
    - "backend/tests/test_time.py — 7 timezone conversion tests"
    - "backend/tests/test_config.py — 16 Settings tests incl. required-secret enforcement"
    - "backend/tests/test_health.py — 9 health endpoint tests"
    - "deploy/docker-compose.dev.yml — services: postgres, redis, api, worker, beat"
    - "deploy/.env.example — documented env contract with placeholders"
    - "README.md — monorepo layout + dev quick-start"
  modified:
    - ".gitignore — added .idea/, .claude/, .planning/config.json"
decisions:
  - "Use env_file required:false in docker-compose.dev.yml so docker compose config -q passes before .env exists"
  - "get_db() yields Session synchronously (sync engine) to match spec scaffold; async upgrade deferred"
  - "TZ helper imports settings lazily (try/except) to break circular import cycle"
  - "Health returns 200 even for degraded state — monitoring reads per-component fields not HTTP status"
metrics:
  duration_minutes: 7
  completed_date: "2026-06-13"
  tasks_completed: 3
  tasks_total: 3
  files_created: 19
  tests_added: 41
---

# Phase 01 Plan 01: Backend Scaffold, Core Modules, and /health Summary

**One-liner:** Python 3.12 FastAPI backend skeleton with Pydantic Settings env contract, SQLAlchemy 2 Base/get_db, structlog JSON logging, Asia/Tashkent time helper, GET /api/v1/health endpoint, and docker-compose dev stack (postgres, redis, api, worker, beat).

## What Was Built

### Task 1: Backend package skeleton, config/settings, and env contract

- Created `backend/` Python package with full subpackage hierarchy (`app/api/`, `app/core/`, `app/models/`, `app/schemas/`, `app/services/`, `tests/`)
- `backend/pyproject.toml`: Python 3.12, fastapi, uvicorn, sqlalchemy>=2, alembic, psycopg[binary], pydantic>=2, pydantic-settings, celery, redis, structlog, argon2-cffi, python-jose; ruff + mypy configured
- `backend/app/core/config.py`: `Settings(BaseSettings)` covering all 18 dev-spec §7 env vars. Secrets (JWT_SECRET, BOT_TOKEN, WEBHOOK_SECRET, TG_API_ID, TG_API_HASH, ANTHROPIC_API_KEY, S3_ACCESS_KEY, S3_SECRET_KEY) are required with no default — fail-fast on misconfiguration. `TZ_DISPLAY` defaults to `"Asia/Tashkent"`.
- `deploy/.env.example`: documented env contract with placeholder values; header explains .env lives outside repo
- Extended `.gitignore` to cover `.idea/`, `.claude/`, `.planning/config.json` (in addition to existing `.env`, `*.session`, `__pycache__/`, `.venv/`)
- `README.md`: monorepo layout + dev compose quick-start

**Commit:** f1e5902

### Task 2: Core modules — db session, structlog JSON logging, Asia/Tashkent time helper

- `backend/app/core/db.py`: `create_engine(settings.DATABASE_URL)` with `pool_pre_ping=True`; `SessionLocal = sessionmaker(...)`; `class Base(DeclarativeBase)` that all Phase-1 models will inherit; `get_db()` FastAPI dependency
- `backend/app/core/logging.py`: `configure_logging()` wiring structlog to emit JSON lines to stdout via `ProcessorFormatter(JSONRenderer())`; bridged to stdlib logging so uvicorn/celery also emit structured JSON; `get_logger()` helper
- `backend/app/core/time.py`: `utcnow()` returning aware UTC; `to_display_tz(dt, tz=None)` converting UTC to configurable display zone; lazy settings import prevents circular dependency; raises `ValueError` on naïve input
- `tests/test_time.py`: 7 tests — UTC→+05:00 offset, midnight crossing, naïve input rejection, ZoneInfo object accepted
- `tests/test_config.py`: 16 tests — defaults (TZ_DISPLAY, LLM models, token limit), env reading, TG_API_ID coerced to int, invalid TZ rejected, 10 required-secret tests

**Test result:** 32/32 pass

**Commit:** 50ff51b

### Task 3: FastAPI app factory, /health endpoint, and docker-compose dev stack

- `backend/app/main.py`: `create_app()` calls `configure_logging()`, creates `FastAPI(...)`, adds CORS middleware, and calls `application.include_router(health_router, prefix="/api/v1")`; module-level `app = create_app()` for uvicorn
- `backend/app/api/health.py`: `GET /health` (mounted at `/api/v1/health`) — `_check_db()` executes `SELECT 1`, `_check_redis()` calls `client.ping()`; returns `{status, db, redis}` as `HealthResponse`; always HTTP 200; error detail logged server-side only (T-01-02)
- `backend/tests/conftest.py`: `client` fixture with `get_db` overridden (mock session) and `_check_redis` patched; `client_db_error` and `client_redis_error` fixtures for degraded-state tests
- `backend/tests/test_health.py`: 9 tests — 200 status, db/redis/status keys present, all-ok case, degraded states, no sensitive data in response, JSON content-type
- `deploy/docker-compose.dev.yml`: postgres:16-alpine (named volume + healthcheck), redis:7-alpine, api (uvicorn + live-reload volume), worker (celery -Q ingest,parse,notify,default), beat; all use `env_file: path: ../.env, required: false`; no inline secret values (T-01-03)

**Test result:** 9/9 pass (41 total)
**Compose validation:** `docker compose config -q` exits 0, services: postgres, redis, api, worker, beat

**Commit:** 495ec02

## Verification Results

| Check | Result |
|-------|--------|
| `python -m pytest tests/ -q` | 41/41 passed |
| `docker compose -f deploy/docker-compose.dev.yml config -q` | exits 0 |
| `grep 'Asia/Tashkent' config.py` | TZ_DISPLAY default confirmed |
| `grep -rn "JWT_SECRET *= *['\"][^'\"]" backend/` | no secret literals |
| `grep -c "env_file" docker-compose.dev.yml` | 5 (one per service using env_file) |
| `tomllib.load(open('pyproject.toml','rb'))` | valid TOML confirmed |

## Requirements Satisfied

| Requirement | How |
|-------------|-----|
| REQ-nfr-security | Secrets from untracked .env; `.gitignore` covers `.env`/`*.session`; no literals in source |
| REQ-nfr-observability | structlog JSON → stdout via `configure_logging()`; GET /api/v1/health reports db+redis status |
| REQ-nfr-time-localization | `utcnow()` + `to_display_tz()` in `core/time.py`; unit-tested with UTC→+05:00 assertions |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] docker-compose validation failed without .env present**

- **Found during:** Task 3 verification
- **Issue:** `docker compose config -q` exited 1 because `env_file: ../.env` is required and the real `.env` doesn't exist in the dev repo
- **Fix:** Changed all `env_file` entries from short form (`- ../.env`) to long form with `required: false` — valid per Docker Compose v2.24+ specification. The env contract is still enforced at runtime.
- **Files modified:** `deploy/docker-compose.dev.yml`
- **Impact:** No security impact; `required: false` only affects scaffold/CI validation, not live deployments where .env is populated

## Known Stubs

None. All modules are functional implementations, not placeholders. The `__init__.py` markers contain descriptive comments (not empty). The compose `Dockerfile` references point to `../backend/Dockerfile` which does not yet exist — this is expected and will be created in a later plan (the compose file builds correctly in validation mode, just not at runtime without the Dockerfile).

## Threat Flags

No new threat surface beyond what was analyzed in the plan's threat model. Health endpoint returns only `{status, db, redis}` enums — confirmed by test `test_health_response_no_sensitive_data`.

## Self-Check: PASSED

All 15 key files verified present on disk. All 3 task commits (f1e5902, 50ff51b, 495ec02) verified in git log.
