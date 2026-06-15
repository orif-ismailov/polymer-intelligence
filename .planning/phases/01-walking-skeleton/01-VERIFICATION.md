---
phase: 01-walking-skeleton
verified: 2026-06-15T12:00:00Z
status: gaps_found
score: 3/5 must-haves verified (2 deferred to Phase 2, 1 WARNING carried forward)
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 5/5 (config-level)
  gaps_closed:
    - "nginx starts in the dev compose with no [emerg] — nginx.dev.conf (HTTP-only, no dashboard upstream, no letsencrypt) confirmed live: HTTP 200 on /api/v1/health through proxy"
    - "ruff check . exits 0 (124 violations resolved, tools pinned ruff==0.15.17 / mypy==2.1.0)"
    - "mypy app/services and mypy app/schemas exit 0 with strictness intact"
    - "pytest 103 passed, 17 skipped (no regressions from plan 01-10 edits)"
    - "CI S3 env var mismatch (CR-01): ci.yml renamed S3_ENDPOINT_URL → S3_ENDPOINT; regression test added"
  gaps_remaining:
    - "SC#1: worker and beat containers crash-loop (ModuleNotFoundError: No module named 'app.tasks') — deferred to Phase 2"
    - "SC#2: migration entrypoint (run_migrations) is not called from main.py startup; schema_version: null in live /health confirms migrations are not auto-applied on compose up"
    - "SC#5: dashboard tsc will fail on clean CI checkout — .next/dev/types/routes.d.ts is gitignored but imported by next-env.d.ts; no next build step precedes tsc in ci.yml (human-needed for live CI run)"
  regressions: []
gaps:
  - truth: "docker compose up brings up api, worker, beat, postgres, redis, nginx; /health returns OK"
    status: partial
    reason: "nginx + api + postgres + redis come up cleanly and /health returns HTTP 200 (confirmed live by orchestrator). Worker and beat crash-loop immediately with ModuleNotFoundError: No module named 'app.tasks'. The module does not exist in the repo — Celery tasks are Phase 2/3 work. SC#1 as written requires all six services to come up. Worker/beat are scaffolded in compose but reference a non-existent module."
    artifacts:
      - path: "deploy/docker-compose.dev.yml"
        issue: "worker and beat commands reference app.tasks.celery_app (lines 97, 118) which does not exist in backend/app/"
      - path: "backend/app/"
        issue: "No tasks/ directory or tasks.py module exists — app.tasks is Phase 2 deliverable"
    missing:
      - "Create a minimal backend/app/tasks/__init__.py and backend/app/tasks/celery_app.py stub so celery can import the app without crashing at boot (tasks need not run yet — just import cleanly so worker/beat containers start instead of crash-looping)"
      - "OR: accept that worker/beat starting is a Phase 2 goal and update the ROADMAP SC#1 to remove them from the Phase 1 compose requirement"
  - truth: "Alembic applies the full locked PostgreSQL 16 schema (all tables, ENUMs, v_live_feed) plus seed data on a clean database"
    status: partial
    reason: "The migration (0001_initial_schema.py: 20 tables, 14 ENUMs, v_live_feed view) is complete and correct. Seed data files are non-empty (products.json 58 lines, grades.json 68 lines, synonyms.json 77 lines). The advisory-locked entrypoint (app/entrypoint.py) runs correctly when invoked. HOWEVER: run_migrations() is NOT called from main.py at startup — there is no lifespan hook or on_event in main.py that imports or calls entrypoint.py. The live /health response returned schema_version: null, confirming migrations were not auto-applied when the api container started. The dev-spec intent was auto-migration at api startup (entrypoint.py docstring: 'Called from the api container entrypoint/startup (e.g., from main.py lifespan)') but the wiring is absent."
    artifacts:
      - path: "backend/app/main.py"
        issue: "No import of app.entrypoint, no lifespan context manager, no on_event('startup') hook that calls run_migrations(). Startup: create_app() → configure_logging() → FastAPI() → CORS middleware → routers. Migration not in the startup path."
      - path: "backend/app/entrypoint.py"
        issue: "run_migrations() only called from __main__ guard (line 161). Not wired to FastAPI startup. Correctly says 'Called from main.py lifespan' in docstring, but the wiring was never added."
    missing:
      - "Add a FastAPI lifespan context manager to main.py that calls run_migrations() on startup (the advisory lock in entrypoint.py handles concurrent api containers safely). This is the dev-spec contract that makes SC#2 'Alembic applies... on a clean database' true automatically."
      - "Alternatively: add a compose entrypoint script (e.g. deploy/scripts/migrate-then-serve.sh) that runs python -m app.entrypoint before uvicorn, and set it as the api command in docker-compose.dev.yml"
deferred:
  - truth: "docker compose up brings up worker and beat (the app.tasks module portion of SC#1)"
    addressed_in: "Phase 2"
    evidence: "Phase 2 Success Criteria #2: 'UZEX offers/quotations/concluded-deals are fetched on the beat schedule (15 min trading hours, hourly otherwise)' — requires beat to be operational, which requires app.tasks.celery_app to exist. Phase 2 goal: 'Immutable raw pipeline, SourceAdapter registry, UZEX collectors → signals'. The app.tasks module is the Celery application that enables worker and beat; it is explicitly Phase 2 infrastructure."
human_verification:
  - test: "Run the full CI pipeline (push to main or develop and observe GitHub Actions jobs: backend, dashboard, webapp, build-images)"
    expected: "Backend job: ruff, mypy, pytest all pass green (locally confirmed). Dashboard job: eslint passes; tsc --noEmit is the risk — .next/dev/types/routes.d.ts is gitignored and imported by next-env.d.ts line 3; if absent on CI, tsc raises TS2307. Fix if needed: add 'npx next build --no-lint' step before tsc in the dashboard job. Webapp job: eslint + tsc pass. build-images: Dockerfile.backend and Dockerfile.dashboard build successfully."
    why_human: "Requires CI runner; WR-01 (dashboard tsc on clean checkout) is the primary risk. All backend gates confirmed locally but CI environment may differ."
  - test: "After stack is up with .env populated, run alembic upgrade head (or python -m app.entrypoint from backend/) and then curl /api/v1/health"
    expected: "schema_version changes from null to '0001'; seed data present in products and product_grades tables"
    why_human: "Migration is not auto-applied at startup (gap); manual step required to verify SC#2 end-to-end. Human must confirm the migration actually runs cleanly and schema_version becomes non-null."
  - test: "Verify browser CORS + httpOnly cookie flow at http://localhost from dashboard UI"
    expected: "Browser attaches refresh cookie on /api/v1/auth/refresh; 200 + access token; no CORS errors in console"
    why_human: "Browser CORS enforcement and httpOnly cookie behavior require a real browser session"
---

# Phase 1: Walking Skeleton Verification Report (Re-verification #2)

**Phase Goal:** A deployable end-to-end skeleton exists — the locked schema is migrated and seeded, the team can authenticate by role, and health/CI/compose are green — so every later phase plugs into a real, running backbone.
**Verified:** 2026-06-15T12:00:00Z
**Status:** gaps_found
**Re-verification:** Yes — after gap-closure plans 01-08, 01-09, 01-10; following live UAT that found 3 issues

---

## Executive Summary

Plans 01-08, 01-09, and 01-10 successfully closed the three UAT-diagnosed gaps: nginx now boots in dev (SC#1 nginx/api/postgres/redis confirmed live — HTTP 200 on /health), ruff/mypy gates are green with pinned tools (SC#5 backend gates confirmed locally), and the S3 env name mismatch is fixed. However, goal-backward verification against the ACTUAL running stack reveals two genuine gaps that survive after gap closure:

1. **SC#1 (PARTIAL):** Worker and beat crash-loop (`ModuleNotFoundError: No module named 'app.tasks'`). The module does not exist — Celery tasks are Phase 2. The SC literally requires all six services. Four of six come up; worker and beat do not. (Deferrable to Phase 2 per Step 9b.)

2. **SC#2 (PARTIAL):** Migration entrypoint is not wired to api startup. The live `/health` returned `schema_version: null`, proving migrations are not auto-applied on `docker compose up`. The dev-spec intent (entrypoint.py docstring) was a lifespan hook in main.py — but that hook was never added. Schema and seed data are correct; the automatic application path is the gap.

SC#3, SC#4, and the backend portion of SC#5 are fully verified. The dashboard tsc gate requires a live CI run (WR-01 risk remains).

---

## Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `docker compose up` brings up api, worker, beat, postgres, redis, nginx; `/health` returns OK | PARTIAL (BLOCKER) | Live: nginx + api + postgres + redis Up, /health HTTP 200 `{"status":"ok","db":"ok","redis":"ok","schema_version":null}` (orchestrator confirmed). Worker and beat crash-loop: `ModuleNotFoundError: No module named 'app.tasks'`. `app.tasks` does not exist in backend/app/. Deferred: Phase 2 SC#2 requires beat schedule to operate (app.tasks is Phase 2 infrastructure). |
| 2 | Alembic applies the full locked PostgreSQL 16 schema (all tables, ENUMs, `v_live_feed`) plus seed data on a clean database | PARTIAL (WARNING) | Migration file: 20 tables (grep count), 14 ENUMs (enum.StrEnum in enums.py confirmed), v_live_feed view (line 727–746 of migration). Seed JSON files non-empty (products 58 lines, grades 68 lines, synonyms 77 lines). Advisory-locked entrypoint exists and works. GAP: `run_migrations()` not called from main.py startup — no lifespan hook. Live `/health` returned `schema_version: null` confirming migrations were not auto-applied. |
| 3 | A staff user can log in and receive a JWT (access 15 min + refresh 7 d httpOnly); endpoints enforce admin/analyst/trader/viewer roles | VERIFIED | auth.py: POST /auth/login + POST /auth/refresh. security.py: create_access_token (15 min), create_refresh_token (7 days, httpOnly cookie). deps.py: require_role factory; require_admin, require_analyst_or_admin shortcuts. StaffRole ENUM: admin/analyst/trader/viewer. test_rbac.py: 103 passed, 17 skipped. |
| 4 | Passwords are argon2-hashed; secrets load from `.env` outside the repo; timestamps are stored UTC with an Asia/Tashkent display helper | VERIFIED | security.py: `_hasher = PasswordHasher(...)` (argon2-cffi); `_DUMMY_HASH = _hasher.hash("timing-attack-mitigation-dummy")` at module level; `dummy_verify()` calls `_hasher.verify(_DUMMY_HASH, plain)` (real KDF, no timing oracle). config.py: 8 required secrets with no defaults (JWT_SECRET, BOT_TOKEN, etc.); JWT_SECRET validator rejects <32 chars. Migration: 25 `TIMESTAMP(timezone=True)` columns. time.py: `to_display_tz()` with `_DEFAULT_TZ = "Asia/Tashkent"`. CORS: `allow_origins=settings.CORS_ALLOWED_ORIGINS` (non-wildcard, default `["http://localhost:3000"]`). |
| 5 | CI (ruff, mypy, eslint+tsc, tests, image build) passes green on the scaffold | VERIFIED (backend confirmed; dashboard tsc human-needed) | ruff check . → "All checks passed!" (0 violations, confirmed live from venv). mypy app/services → "Success: no issues found in 3 source files" (confirmed live). mypy app/schemas → "Success: no issues found in 2 source files" (confirmed live). pytest → 103 passed, 17 skipped, 0 failures (confirmed live). ruff==0.15.17 / mypy==2.1.0 exact-pinned. No `|| true` in ci.yml (grep → 0). S3_ENDPOINT (not S3_ENDPOINT_URL) in ci.yml line 79. Dashboard tsc risk: .next/dev/types/routes.d.ts is gitignored but imported by next-env.d.ts line 3; absent on clean CI checkout → TS2307. Live CI run required. |

**Score:** 3/5 truths fully verified (SC#3 VERIFIED, SC#4 VERIFIED, SC#5 backend-confirmed; SC#1 PARTIAL-blocker, SC#2 PARTIAL-warning)

---

## Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | `docker compose up` brings up worker and beat (app.tasks module required) | Phase 2 | Phase 2 SC#2: "UZEX offers/quotations/concluded-deals are fetched on the beat schedule" requires beat to be operational, which requires `app.tasks.celery_app` to exist. Phase 2 goal: "Immutable raw pipeline, SourceAdapter registry, UZEX collectors → signals." |

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `deploy/nginx/nginx.dev.conf` | HTTP-only dev config, no dashboard upstream, no letsencrypt | VERIFIED | Created by commit 9912950. listen 80, no listen 443 ssl, no ssl_certificate /etc/letsencrypt, no /dashboard/ location, limit_req_zone + auth-login burst, 4 security headers, proxy_pass http://api:8000. |
| `deploy/docker-compose.dev.yml` | nginx mounts nginx.dev.conf, 80:80, 6 services | VERIFIED (4/6 start) | nginx service at lines 127–135: `image: nginx:stable`, ports `80:80`, volume `./nginx/nginx.dev.conf:/etc/nginx/nginx.conf:ro`. Worker (line 97) and beat (line 118) reference `app.tasks.celery_app` (does not exist). |
| `backend/Dockerfile` | FROM python:3.12-slim, pip install, appuser, HEALTHCHECK | VERIFIED | Exists. FROM python:3.12-slim, apt-get libpq5/libffi8/curl, pip install ".[dev]", appuser uid 1001, CMD ["uvicorn", "app.main:app", ...], HEALTHCHECK curl /api/v1/health. |
| `backend/pyproject.toml` | Valid PEP 517, ruff/mypy exact-pinned | VERIFIED | build-backend = "setuptools.build_meta" (line 3). ruff==0.15.17 and mypy==2.1.0 exact-pinned in [dev] (lines 43–44). `python3 -c "import tomllib; tomllib.load(...)"` passes. |
| `.github/workflows/ci.yml` | No `|| true`, S3_ENDPOINT (not URL), enforced gates | VERIFIED | grep `|| true` → 0 matches. Line 79: `S3_ENDPOINT: http://localhost:9000`. ruff check, mypy, pytest, eslint (both), tsc (both), build-images all present without suppression. |
| `backend/app/core/security.py` | argon2 hash, _DUMMY_HASH, dummy_verify, JWT | VERIFIED | _hasher = PasswordHasher(...), _DUMMY_HASH = _hasher.hash("timing-attack-mitigation-dummy"), dummy_verify(plain) calls _hasher.verify and suppresses VerifyMismatchError via contextlib.suppress. |
| `backend/app/core/config.py` | CORS_ALLOWED_ORIGINS setting, JWT_SECRET validator | VERIFIED | CORS_ALLOWED_ORIGINS: `list[str] | str = ["http://localhost:3000"]` (non-wildcard). JWT_SECRET field_validator rejects <32 chars. 8 required secrets with no defaults. |
| `backend/app/core/time.py` | to_display_tz() with Asia/Tashkent | VERIFIED | _DEFAULT_TZ = "Asia/Tashkent". to_display_tz(dt, tz=None) accepts str or tzinfo. |
| `backend/app/api/deps.py` | require_role factory for 4 roles | VERIFIED | require_role(*roles: StaffRole) factory at line 105. require_admin, require_analyst_or_admin shortcuts. |
| `backend/app/api/auth.py` | POST /auth/login, POST /auth/refresh | VERIFIED | Both endpoints present. httpOnly cookie on refresh. |
| `backend/app/api/health.py` | /health with schema_version | VERIFIED | Returns `{"status": "ok|error", "db": "ok|error", "redis": "ok|error", "schema_version": str|null}`. schema_version null confirmed live (migration not auto-applied). |
| `backend/alembic/versions/0001_initial_schema.py` | 20 tables, 14 ENUMs, v_live_feed | VERIFIED | 20 `op.create_table` calls. 14 `enum.StrEnum` classes in enums.py (all converted from UP042). v_live_feed CREATE VIEW at lines 731–745. |
| `backend/app/seed/data/*.json` | Non-empty seed files | VERIFIED | products.json (58 lines), grades.json (68 lines), synonyms.json (77 lines), staff_users.json. |
| `backend/app/entrypoint.py` | Advisory-locked migration runner | VERIFIED (not auto-wired) | run_migrations() with pg_advisory_lock exists and is correct. NOT called from main.py startup. Only called from `if __name__ == "__main__"`. |
| `backend/app/models/enums.py` | 14 StrEnum classes for PostgreSQL ENUMs | VERIFIED | All 14 converted to enum.StrEnum (UP042). PricePointKind.index has `# type: ignore[assignment]` to handle str.index() shadowing. |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `deploy/docker-compose.dev.yml` | `deploy/nginx/nginx.dev.conf` | nginx service volume mount | VERIFIED | `./nginx/nginx.dev.conf:/etc/nginx/nginx.conf:ro` at line 133 |
| `deploy/nginx/nginx.dev.conf` | `api:8000` | proxy_pass in location /api/ | VERIFIED | `proxy_pass http://api:8000;` at line 91 |
| `deploy/docker-compose.dev.yml` | `backend/Dockerfile` | context ../backend + dockerfile Dockerfile (3 services) | VERIFIED | api, worker, beat all use `context: ../backend, dockerfile: Dockerfile`; backend/Dockerfile exists |
| `backend/app/main.py` | `backend/app/core/config.py` | `settings.CORS_ALLOWED_ORIGINS` in CORSMiddleware | VERIFIED | `allow_origins=settings.CORS_ALLOWED_ORIGINS` at line 61 |
| `backend/app/services/auth_service.py` | `backend/app/core/security.py` | `dummy_verify` on user-not-found path | VERIFIED | dummy_verify called on unknown user email path; no dummysalt/dummyhash literal anywhere |
| `backend/app/main.py` | `backend/app/entrypoint.py` | lifespan startup hook calling run_migrations | NOT WIRED | No lifespan hook, no import of entrypoint, no on_event startup in main.py. Migration not auto-applied. |
| `.github/workflows/ci.yml` | `backend/pyproject.toml` | pip install -e ".[dev]" installs pinned ruff==0.15.17, mypy==2.1.0 | VERIFIED | build-backend = "setuptools.build_meta" valid; ruff==0.15.17 / mypy==2.1.0 exact-pinned in [dev] |
| `.github/workflows/ci.yml` | `deploy/Dockerfile.backend` | build-images job `docker build -f deploy/Dockerfile.backend ... backend/` | VERIFIED (exists) | WARNING (WR-02): CI builds deploy/Dockerfile.backend but compose uses backend/Dockerfile — different files; not caught by CI build gate |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `backend/app/api/health.py` | db_status, redis_status, schema_version | db.execute(text("SELECT 1")), redis_lib.from_url(...).ping(), alembic_version query | Yes — real DB/redis calls (schema_version: null is accurate; means not migrated) | FLOWING |
| `backend/app/api/auth.py` | user (StaffUser) | `db.query(StaffUser).filter(StaffUser.email == email).first()` | Yes — parameterized ORM query | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| nginx.dev.conf has listen 80, no letsencrypt, proxy to api | grep checks on nginx.dev.conf | listen 80 present; no ssl_certificate /etc/letsencrypt; proxy_pass http://api:8000 present; no /dashboard/ location | PASS |
| backend/Dockerfile exists and has correct FROM | test -f backend/Dockerfile && grep FROM | EXISTS; FROM python:3.12-slim | PASS |
| ruff check . → 0 violations | cd backend && .venv/bin/ruff check . | "All checks passed!" | PASS |
| mypy app/services → 0 errors | cd backend && .venv/bin/mypy app/services --ignore-missing-imports | "Success: no issues found in 3 source files" | PASS |
| mypy app/schemas → 0 errors | cd backend && .venv/bin/mypy app/schemas --ignore-missing-imports | "Success: no issues found in 2 source files" | PASS |
| pytest → 103 passed, 17 skipped | cd backend && .venv/bin/python -m pytest tests -q | 103 passed, 17 skipped, 1 warning in 4.67s | PASS |
| No || true in ci.yml | grep -c '|| true' .github/workflows/ci.yml | 0 | PASS |
| S3_ENDPOINT (not URL) in ci.yml | grep -n "S3_ENDPOINT" ci.yml | Line 79: `S3_ENDPOINT: http://localhost:9000` | PASS |
| ruff==0.15.17 / mypy==2.1.0 pinned | grep -E 'ruff==|mypy==' pyproject.toml | ruff==0.15.17 and mypy==2.1.0 (lines 43–44) | PASS |
| argon2 dummy_verify uses real KDF | grep '_DUMMY_HASH = _hasher.hash' security.py | `_DUMMY_HASH = _hasher.hash("timing-attack-mitigation-dummy")` at line 44 | PASS |
| app.tasks module exists (worker/beat need it) | find backend/app -name tasks | NOT FOUND — no tasks/ directory or tasks.py | FAIL |
| run_migrations wired to main.py startup | grep lifespan/run_migrations main.py | No lifespan hook, no run_migrations import in main.py | FAIL |
| schema_version non-null after compose up | Live orchestrator /health output | `schema_version: null` — migrations not auto-applied | FAIL |
| worker container starts | Live orchestrator observation | crash-loop: ModuleNotFoundError: No module named 'app.tasks' | FAIL |
| beat container starts | Live orchestrator observation | crash-loop: ModuleNotFoundError: No module named 'app.tasks' | FAIL |
| dashboard .next/dev/types/routes.d.ts committed to git | git ls-files dashboard/.next | NOT_IN_GIT — gitignored; absent on clean CI checkout; tsc will fail with TS2307 | RISK |

---

## Probe Execution

No probe scripts found in `scripts/*/tests/probe-*.sh`. No probes declared in PLAN frontmatter. SKIPPED.

---

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| REQ-roles | 01-01, 01-03 | Roles admin/analyst/trader/viewer (ENUM staff_role) | VERIFIED | StaffRole.admin/analyst/trader/viewer in enums.py (StrEnum). require_role factory in deps.py. 4 seeded staff users. test_rbac.py: 103 passed. |
| REQ-nfr-security | 01-01, 01-03, 01-04, 01-07 | HTTPS; secrets in .env; argon2 hashing; audit_log | VERIFIED (conditional) | argon2 confirmed. _DUMMY_HASH real KDF. CORS non-wildcard. JWT_SECRET ≥32 chars enforced. Secrets: 8 required fields with no defaults. HSTS in nginx.conf (prod); dev intentionally HTTP-only. Browser CORS/cookie flow deferred to human. |
| REQ-nfr-observability | 01-01, 01-02, 01-04, 01-06 | Structured logs; /health page; CI quality gates | PARTIALLY VERIFIED | structlog JSON confirmed. /health endpoint present and returns DB/redis status. CI ruff/mypy/pytest green locally. Dashboard tsc risk (WR-01). |
| REQ-nfr-time-localization | 01-01, 01-02 | All timestamps UTC in DB; Asia/Tashkent display | VERIFIED | 25 TIMESTAMP(timezone=True) columns in migration (confirmed). to_display_tz() with _DEFAULT_TZ = "Asia/Tashkent" in time.py. |

**Orphaned requirement IDs:** None. All four Phase 1 requirements are accounted for.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `deploy/docker-compose.dev.yml` | 97, 118 | worker and beat reference `app.tasks.celery_app` which does not exist | BLOCKER (SC#1) | Both containers crash-loop immediately on `docker compose up`. Phase 2 will introduce app.tasks, but until then SC#1 is not fully met. |
| `backend/app/main.py` | — | No lifespan hook calling run_migrations(); migration not auto-applied at api startup | WARNING (SC#2) | schema_version: null on live /health; migrations must be run manually (python -m app.entrypoint). Entrypoint.py docstring says it should be called from main.py lifespan. |
| `dashboard/next-env.d.ts` | 3 | `import "./.next/dev/types/routes.d.ts"` — .next/ is gitignored; file absent on clean CI checkout | WARNING (SC#5) | Dashboard tsc --noEmit will fail with TS2307 on CI until `next build` is run first. Fix: add `npx next build --no-lint` or `npx next typegen` step before `npx tsc --noEmit` in the dashboard CI job. |
| `.github/workflows/ci.yml` | 154 | `build-images` job builds `deploy/Dockerfile.backend` while compose builds `backend/Dockerfile` | WARNING (WR-02) | CI validates a different image than compose runs. Both Dockerfiles exist and are behaviourally equivalent per the comment in backend/Dockerfile, but a change to backend/Dockerfile is not caught by the CI image-build gate. |
| `backend/app/main.py` | 47–48 | `docs_url="/docs"` and `redoc_url="/redoc"` unconditional | INFO (WR-06) | OpenAPI schema always exposed including in production. Not a Phase 1 blocker; should be gated via env var before production deployment. |

No `TBD`, `FIXME`, or `XXX` markers in any file modified by plans 01-08, 01-09, or 01-10.

---

## Human Verification Required

### 1. Full CI Pipeline — Live Run (All 5 Jobs)

**Test:** Push a commit to main or develop. Observe all 5 GitHub Actions jobs: backend, dashboard, webapp, build-images.
**Expected:** Backend job green (ruff/mypy/pytest confirmed locally). Dashboard job: eslint should pass; tsc --noEmit is the risk — `.next/dev/types/routes.d.ts` is gitignored and imported by `next-env.d.ts` line 3. If dashboard tsc fails with TS2307, fix: add `npx next build --no-lint` step before `npx tsc --noEmit` in the dashboard job. Webapp job: eslint + tsc expected to pass. build-images: both Dockerfiles exist and should build.
**Why human:** Requires CI runner. Dashboard tsc (WR-01) is the primary known risk.

### 2. Migration on Clean Database

**Test:** Bring up the dev stack with a fresh postgres volume (or `docker compose down -v && docker compose up`). Separately run `docker compose exec api python -m app.entrypoint` (or add the lifespan hook first). Observe `/api/v1/health` before and after.
**Expected:** Before running entrypoint: `schema_version: null`. After: `schema_version: "0001"`. Seed data in products table.
**Why human:** Migration is not auto-applied at startup (SC#2 gap). This manually verifies the migration infrastructure works end-to-end even though the wiring to main.py startup is missing.

### 3. Browser CORS and httpOnly Cookie Flow

**Test:** With stack up (api at http://localhost), load http://localhost:3000 (dashboard dev server). Submit valid staff credentials. Open DevTools → Network → observe /api/v1/auth/refresh.
**Expected:** Browser attaches the httpOnly refresh cookie; response 200 + access token. No CORS errors in console.
**Why human:** Browser CORS enforcement and httpOnly cookie attachment cannot be verified programmatically.

---

## Gaps Summary

**2 genuine gaps blocking full SC achievement** after the three gap-closure plans (01-08, 01-09, 01-10):

### Gap 1 (SC#1 — PARTIAL): worker and beat crash-loop

Worker and beat containers crash immediately with `ModuleNotFoundError: No module named 'app.tasks'`. The module doesn't exist — Celery tasks are Phase 2. The ROADMAP SC#1 as written requires all six services including worker and beat. Four of six come up cleanly (nginx, api, postgres, redis — all live-confirmed by orchestrator). **This gap is deferrable to Phase 2** under Step 9b: Phase 2 SC#2 explicitly requires the beat schedule to operate, which requires app.tasks to exist. The gap's root cause (app.tasks missing) is the same root cause Phase 2 must resolve.

**Fix options:** (a) Create a minimal `backend/app/tasks/__init__.py` and `backend/app/tasks/celery_app.py` stub so Celery can import the app and containers start (tasks don't need to work yet — just import cleanly), OR (b) update the ROADMAP SC#1 to remove worker/beat from the Phase 1 requirement, noting they become operational in Phase 2.

### Gap 2 (SC#2 — WARNING): migration not auto-applied at api startup

The migration infrastructure is complete and correct (20 tables, 14 ENUMs, v_live_feed, seed JSON files). The advisory-locked `run_migrations()` in `entrypoint.py` works correctly when invoked. But it is NOT called from `main.py` at startup — there is no lifespan context manager or `on_event('startup')` hook. The live health response returned `schema_version: null`, proving migrations did not auto-apply on compose up. The entrypoint.py docstring explicitly states it should be "called from the api container entrypoint/startup (e.g., from main.py lifespan)" — this wiring was planned but never implemented.

**Fix:** Add a FastAPI lifespan context manager to `main.py` that calls `run_migrations()` on startup. The advisory lock in entrypoint.py already handles concurrent container startup safely (T-02-01 mitigation).

---

## Outstanding Open Issues (Not Phase-1 Goal Blockers, Must Fix Before Production)

| Finding | File | Must Fix Before |
|---------|------|-----------------|
| WR-01: Dashboard tsc fails on clean checkout — .next/dev/types absent | `.github/workflows/ci.yml`, `dashboard/next-env.d.ts` | First CI job push |
| WR-02: CI build-images builds deploy/Dockerfile.backend; compose builds backend/Dockerfile | `.github/workflows/ci.yml` | Phase 2 (any infra change to backend image) |
| WR-03: is_active checked after verify_password — timing oracle on deactivated accounts | `backend/app/services/auth_service.py:64-70` | Phase 4 (dashboard auth with real users) |
| WR-04: decode_token interpolates attacker-controlled claim into exception message | `backend/app/core/security.py:189-197` | Phase 4 |
| WR-05: restart: unless-stopped + env_file required: false causes crash-loop on missing .env | `deploy/docker-compose.dev.yml` | Before ops deployment |
| WR-06: docs_url/redoc_url always exposed | `backend/app/main.py:47-48` | Before production |

---

_Verified: 2026-06-15T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
_Mode: Re-verification #2 (after UAT gap-closure plans 01-08, 01-09, 01-10)_
