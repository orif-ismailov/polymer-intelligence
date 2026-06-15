---
phase: 01-walking-skeleton
verified: 2026-06-15T15:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 1
overrides:
  - must_have: "docker compose up brings up api, worker, beat, postgres, redis, nginx; /health returns OK — worker+beat full Celery operation"
    reason: "ROADMAP.md SC#1 formally amended 2026-06-15 (commit b004e0e): worker+beat containers are defined and intentionally idle/crash until app.tasks.celery_app is built in Phase 2. In-scope SC#1 surface for Phase 1 is api/postgres/redis/nginx + /health, all confirmed live. Full worker+beat operation is a Phase 2 success criterion."
    accepted_by: "Orif"
    accepted_at: "2026-06-15T14:16:48Z"
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:
    - "SC#1 worker/beat: formally deferred via ROADMAP.md SC#1 amendment + STATE.md Deferred Items entry (commit b004e0e). In-scope api/postgres/redis/nginx+/health surface remains live-confirmed."
    - "SC#2: api compose command now runs python -m app.entrypoint && python -m app.seed.seed_reference && python -m app.seed.seed_staff before uvicorn (commit 33d508d). sa.Real() AttributeError fixed to sa.REAL(). Lifespan hook added (RUN_MIGRATIONS_ON_STARTUP, default false). Live-verified: /health returned schema_version='0001', 22 tables, v_live_feed view, products=8, grades=11, staff_users=4."
    - "SC#5 dashboard tsc: npx next typegen step added before tsc --noEmit in dashboard CI job (commit 56859a0). Generates .next/types/routes.d.ts (path next-env.d.ts imports) without requiring a full build. Locally validated: next typegen exits 0, tsc --noEmit exits 0, eslint --max-warnings 0 exits 0."
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Run the full CI pipeline — push to main or develop and observe all 5 GitHub Actions jobs: backend, dashboard, webapp, build-images."
    expected: "Backend: ruff check (0 violations), mypy app/services (0 errors), mypy app/schemas (0 errors), pytest 105 passed 17 skipped. Dashboard: eslint --max-warnings 0 passes; npx next typegen generates .next/types/routes.d.ts; tsc --noEmit exits 0. Webapp: eslint + tsc pass. build-images: deploy/Dockerfile.backend and deploy/Dockerfile.dashboard build successfully."
    why_human: "Requires a live CI runner. The next typegen fix (SC#5) has only been validated locally. A clean GitHub Actions checkout must confirm typegen generates the routes file and tsc then passes without TS2307."
  - test: "Browser CORS and httpOnly cookie flow — with stack up (api at http://localhost), load the dashboard dev server and submit valid staff credentials. Observe DevTools Network tab on /api/v1/auth/refresh."
    expected: "Browser attaches the httpOnly refresh cookie; response 200 + access token. No CORS errors in console."
    why_human: "Browser CORS enforcement and httpOnly cookie attachment cannot be verified programmatically."
---

# Phase 1: Walking Skeleton Verification Report (Re-verification #3)

**Phase Goal:** A deployable end-to-end skeleton exists — the locked schema is migrated and seeded, the team can authenticate by role, and health/CI/compose are green — so every later phase plugs into a real, running backbone.
**Verified:** 2026-06-15T15:00:00Z
**Status:** human_needed
**Re-verification:** Yes — re-verification #3 after second round of gap fixes (commits 33d508d, 56859a0, b004e0e)

---

## Executive Summary

All three gaps from re-verification #2 are now closed. SC#1 worker/beat is formally deferred via an accepted ROADMAP.md amendment (the in-scope surface of api/postgres/redis/nginx + /health remains live-confirmed). SC#2 is fixed and live-verified: the api container command now auto-applies migrations + seed before uvicorn, the latent `sa.Real()` crash was fixed to `sa.REAL()`, and a FastAPI lifespan hook (RUN_MIGRATIONS_ON_STARTUP, default false) was added with 2 unit tests. SC#5 dashboard tsc is fixed: `npx next typegen` was added before `tsc --noEmit` in the dashboard CI job, generating the `.next/types/routes.d.ts` file that next-env.d.ts imports, validated locally.

All 5 success criteria are now met at the code level. The remaining human verification items are: (1) live CI run to confirm the next typegen fix holds on a clean GitHub Actions checkout, and (2) browser CORS/cookie flow. These are standard end-of-phase human checks, not blockers.

Score advances from 3/5 to **5/5** with the SC#1 worker/beat deferral recorded as an accepted override.

---

## Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `docker compose up` brings up api, postgres, redis, nginx; `/health` returns OK | VERIFIED (override) | Live-confirmed by orchestrator: HTTP 200 `{"status":"ok","db":"ok","redis":"ok","schema_version":"0001"}` after SC#2 fix. ROADMAP.md SC#1 formally amended (commit b004e0e) — worker+beat Celery operation deferred to Phase 2 where app.tasks.celery_app is built. STATE.md Deferred Items records the deferral. Override accepted by Orif 2026-06-15. |
| 2 | Alembic applies the full locked PostgreSQL 16 schema (all tables, ENUMs, `v_live_feed`) plus seed data on a clean database | VERIFIED | Commit 33d508d: api compose command runs `python -m app.entrypoint && python -m app.seed.seed_reference && python -m app.seed.seed_staff` before uvicorn (docker-compose.dev.yml line 79). `sa.Real()` AttributeError fixed to `sa.REAL()` in 0001_initial_schema.py line 269. Lifespan hook added to main.py (RUN_MIGRATIONS_ON_STARTUP flag, default false). 2 unit tests added (test_startup_migrations.py). LIVE-VERIFIED: `docker compose down -v && up` → /health returned `schema_version:"0001"`, 22 tables, v_live_feed present, products=8, grades=11, staff_users=4. |
| 3 | A staff user can log in and receive a JWT (access 15 min + refresh 7 d httpOnly); endpoints enforce admin/analyst/trader/viewer roles | VERIFIED | Unchanged from prior verification. auth.py: POST /auth/login + POST /auth/refresh. security.py: create_access_token (15 min), create_refresh_token (7 days, httpOnly cookie). deps.py: require_role factory; require_admin, require_analyst_or_admin shortcuts. StaffRole ENUM: admin/analyst/trader/viewer. pytest: 105 passed, 17 skipped. |
| 4 | Passwords are argon2-hashed; secrets load from `.env` outside the repo; timestamps are stored UTC with an Asia/Tashkent display helper | VERIFIED | Unchanged from prior verification. security.py: `_hasher = PasswordHasher(...)`, `_DUMMY_HASH = _hasher.hash("timing-attack-mitigation-dummy")`. config.py: 8 required secrets with no defaults, JWT_SECRET ≥32-char validator, RUN_MIGRATIONS_ON_STARTUP: bool = False added. Migration: 25 TIMESTAMP(timezone=True) columns. time.py: `to_display_tz()` with `_DEFAULT_TZ = "Asia/Tashkent"`. |
| 5 | CI (ruff, mypy, eslint+tsc, tests, image build) passes green on the scaffold | VERIFIED (locally; live CI run human-needed) | Commit 56859a0: `npx next typegen` step added before `npx tsc --noEmit` in dashboard job (ci.yml lines 112–116). Step comment explains .next/ is gitignored and typegen regenerates routes.d.ts without a full build. Locally validated: next typegen exits 0, tsc --noEmit exits 0, eslint --max-warnings 0 exits 0. Backend: ruff check . → 0 violations (confirmed), mypy app/services → 0 errors, mypy app/schemas → 0 errors, pytest → 105 passed 17 skipped (confirmed live). |

**Score:** 5/5 truths verified (SC#1 with accepted deferral override; SC#5 locally confirmed, live CI run is human-needed)

---

## Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Worker and beat containers full Celery operation (app.tasks.celery_app) | Phase 2 | ROADMAP.md SC#1 amended 2026-06-15 (commit b004e0e). STATE.md Deferred Items: "SC#1 worker+beat Celery startup — needs app.tasks.celery_app (built in Phase 2; beat schedule drives UZEX fetch there)". Phase 2 SC#2: "UZEX offers/quotations/concluded-deals are fetched on the beat schedule" requires beat to be operational. |

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `deploy/docker-compose.dev.yml` | api command auto-migrates+seeds before uvicorn; nginx+api+postgres+redis all start | VERIFIED | Line 79: `sh -c "python -m app.entrypoint && python -m app.seed.seed_reference && python -m app.seed.seed_staff && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"`. nginx, api, postgres, redis all configured and live-confirmed. Worker+beat defined but idle per SC#1 amendment. |
| `backend/alembic/versions/0001_initial_schema.py` | 20 tables, 14 ENUMs, v_live_feed; sa.REAL() (not sa.Real()) | VERIFIED | Line 269: `sa.Column("confidence", sa.REAL(), ...)` — AttributeError-causing `sa.Real()` fixed. v_live_feed CREATE VIEW at lines 731–741. 20 op.create_table calls. 14 ENUM types. Downgrade fully reverses. |
| `backend/app/main.py` | lifespan hook with RUN_MIGRATIONS_ON_STARTUP guard | VERIFIED | Lines 33–49: `@asynccontextmanager async def lifespan()` checks `settings.RUN_MIGRATIONS_ON_STARTUP`; imports and calls `run_migrations()` when true; yields without migration when false. Passed into `FastAPI(lifespan=lifespan)` at line 74. |
| `backend/app/core/config.py` | RUN_MIGRATIONS_ON_STARTUP: bool = False | VERIFIED | Line 77: `RUN_MIGRATIONS_ON_STARTUP: bool = False`. Docstring explains: default false so test suite never attempts migration; dev compose sets true. |
| `backend/tests/test_startup_migrations.py` | 2 unit tests for lifespan migration hook | VERIFIED | test_lifespan_skips_migrations_when_flag_false: patches flag to False, asserts run_migrations NOT called. test_lifespan_runs_migrations_when_flag_true: patches flag to True + run_migrations mock returning "0001", asserts called_once. Both pass in 105-test suite. |
| `.github/workflows/ci.yml` | next typegen step before tsc in dashboard job | VERIFIED | Lines 112–116: "Generate Next.js route types" step runs `npx next typegen` before "Type-check (tsc --noEmit)". Comment explains .next/ gitignored and TS2307 risk. No `|| true` anywhere (0 matches). S3_ENDPOINT at line 79. |
| `dashboard/next-env.d.ts` | imports ./.next/types/routes.d.ts | VERIFIED | Line 3: `import "./.next/types/routes.d.ts";` — this is the path generated by `npx next typegen` (not the gitignored `.next/dev/types/routes.d.ts` dev path). |
| `deploy/nginx/nginx.dev.conf` | HTTP-only dev config, proxy to api:8000 | VERIFIED | Unchanged from prior verification. listen 80, no ssl_certificate /etc/letsencrypt, proxy_pass http://api:8000, limit_req_zone on /api/v1/auth/login. |
| `backend/Dockerfile` | FROM python:3.12-slim, pip install, appuser, HEALTHCHECK | VERIFIED | Unchanged from prior verification. |
| `backend/pyproject.toml` | ruff==0.15.17, mypy==2.1.0 exact-pinned | VERIFIED | Unchanged from prior verification. |
| `backend/app/core/security.py` | argon2 hash, _DUMMY_HASH, dummy_verify, JWT | VERIFIED | Unchanged from prior verification. |
| `backend/app/core/time.py` | to_display_tz() with Asia/Tashkent | VERIFIED | Unchanged from prior verification. |
| `backend/app/api/deps.py` | require_role factory for 4 roles | VERIFIED | Unchanged from prior verification. |
| `backend/app/api/auth.py` | POST /auth/login, POST /auth/refresh | VERIFIED | Unchanged from prior verification. |
| `backend/app/api/health.py` | /health with schema_version | VERIFIED | Live returns `schema_version:"0001"` after SC#2 fix (previously null). |
| `backend/app/seed/data/*.json` | Non-empty seed files | VERIFIED | Unchanged from prior verification. |
| `backend/app/entrypoint.py` | Advisory-locked migration runner | VERIFIED | Now called from compose api command (pre-uvicorn) AND available via lifespan hook (RUN_MIGRATIONS_ON_STARTUP=true). |
| `backend/app/models/enums.py` | 14 StrEnum classes | VERIFIED | Unchanged from prior verification. |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `deploy/docker-compose.dev.yml` api `command` | `backend/app/entrypoint.py` | `python -m app.entrypoint` pre-uvicorn shell command | VERIFIED | Line 79: sh -c runs entrypoint before uvicorn. SC#2 wiring now present as compose-level pre-start step (not lifespan, per dev decision: --reload + live-mount caused watcher restart mid-migration). |
| `deploy/docker-compose.dev.yml` api `command` | `backend/app/seed/seed_reference.py` + `seed_staff.py` | `python -m app.seed.seed_reference && python -m app.seed.seed_staff` | VERIFIED | Line 79: both seed modules invoked idempotently (ON CONFLICT DO NOTHING pattern) before uvicorn. |
| `backend/app/main.py` `lifespan` | `backend/app/entrypoint.py` `run_migrations` | `if settings.RUN_MIGRATIONS_ON_STARTUP` conditional import + call | VERIFIED | Lines 44–48: conditional import of run_migrations inside lifespan body; returns revision for logging. Gated by flag defaulting false. |
| `backend/app/core/config.py` | `backend/app/main.py` | `settings.RUN_MIGRATIONS_ON_STARTUP` in lifespan | VERIFIED | config.py line 77 defines the field; main.py line 44 reads it. |
| `.github/workflows/ci.yml` dashboard job | `npx next typegen` | step before tsc | VERIFIED | ci.yml lines 112–113: "Generate Next.js route types" step precedes "Type-check (tsc --noEmit)" step in dashboard job. |
| `deploy/docker-compose.dev.yml` | `deploy/nginx/nginx.dev.conf` | nginx service volume mount | VERIFIED | `./nginx/nginx.dev.conf:/etc/nginx/nginx.conf:ro` at line 141. |
| `deploy/nginx/nginx.dev.conf` | `api:8000` | proxy_pass in location /api/ | VERIFIED | `proxy_pass http://api:8000;` confirmed. |
| `backend/app/main.py` | `backend/app/core/config.py` | `settings.CORS_ALLOWED_ORIGINS` in CORSMiddleware | VERIFIED | Unchanged from prior verification. |
| `backend/app/services/auth_service.py` | `backend/app/core/security.py` | `dummy_verify` on user-not-found path | VERIFIED | Unchanged from prior verification. |
| `.github/workflows/ci.yml` | `backend/pyproject.toml` | pip install -e ".[dev]" installs ruff==0.15.17, mypy==2.1.0 | VERIFIED | Unchanged from prior verification. |
| `.github/workflows/ci.yml` | `deploy/Dockerfile.backend` | build-images job `docker build -f deploy/Dockerfile.backend` | VERIFIED (note WR-02) | CI validates deploy/Dockerfile.backend; compose uses backend/Dockerfile. Both exist. |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `backend/app/api/health.py` | db_status, redis_status, schema_version | db.execute(text("SELECT 1")), redis ping, alembic_version query | Yes — real DB/redis calls; schema_version now "0001" after SC#2 fix (previously null) | FLOWING |
| `backend/app/api/auth.py` | user (StaffUser) | `db.query(StaffUser).filter(StaffUser.email == email).first()` | Yes — parameterized ORM query; 4 seeded staff users confirmed live | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| api compose command contains migrate+seed before uvicorn | grep "command:" deploy/docker-compose.dev.yml | Line 79: `sh -c "python -m app.entrypoint && python -m app.seed.seed_reference && python -m app.seed.seed_staff && uvicorn ..."` | PASS |
| sa.REAL() (not sa.Real()) in migration | grep "sa\.REAL\|sa\.Real" 0001_initial_schema.py | Line 269: `sa.REAL()` — AttributeError-causing `sa.Real()` absent | PASS |
| lifespan hook in main.py reads RUN_MIGRATIONS_ON_STARTUP | grep "RUN_MIGRATIONS_ON_STARTUP" backend/app/main.py | Lines 44 and 47 — conditional migration call | PASS |
| RUN_MIGRATIONS_ON_STARTUP: bool = False in config.py | grep "RUN_MIGRATIONS_ON_STARTUP" backend/app/core/config.py | Line 77: `RUN_MIGRATIONS_ON_STARTUP: bool = False` | PASS |
| next typegen step precedes tsc in dashboard CI job | grep -n "typegen\|tsc" ci.yml | Lines 112–116: typegen at 112–113, tsc at 115–116 | PASS |
| dashboard next-env.d.ts imports .next/types/routes.d.ts | cat dashboard/next-env.d.ts | Line 3: `import "./.next/types/routes.d.ts";` (not gitignored dev path) | PASS |
| ROADMAP SC#1 amended to remove worker/beat requirement | grep "worker.*beat" ROADMAP.md SC#1 | "worker + beat containers are defined and start, but their Celery app app.tasks.celery_app is built in Phase 2" | PASS |
| STATE.md Deferred Items records SC#1 worker/beat | grep "SC#1 worker" STATE.md | Line 113: "SC#1 worker+beat Celery startup — needs app.tasks.celery_app (built in Phase 2; ...)" | PASS |
| pytest 105 passed 17 skipped | .venv/bin/python -m pytest tests/ -q | 105 passed, 17 skipped, 1 warning in 2.25s | PASS |
| ruff check . exits 0 | .venv/bin/ruff check . | "All checks passed!" | PASS |
| mypy app/services exits 0 | .venv/bin/mypy app/services --ignore-missing-imports | "Success: no issues found in 3 source files" | PASS |
| mypy app/schemas exits 0 | .venv/bin/mypy app/schemas --ignore-missing-imports | "Success: no issues found in 2 source files" | PASS |
| No || true in ci.yml | grep -c '|| true' ci.yml | 0 | PASS |
| S3_ENDPOINT (not S3_ENDPOINT_URL) in ci.yml | grep -n "S3_ENDPOINT" ci.yml | Line 79: `S3_ENDPOINT: http://localhost:9000` | PASS |
| No debt markers (TBD/FIXME/XXX) in modified files | grep across all 6 modified files | 0 matches | PASS |

---

## Probe Execution

No probe scripts found in `scripts/*/tests/probe-*.sh`. No probes declared in PLAN frontmatter. SKIPPED.

---

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| REQ-roles | 01-01, 01-03 | Roles admin/analyst/trader/viewer (ENUM staff_role) | VERIFIED | StaffRole.admin/analyst/trader/viewer in enums.py (StrEnum). require_role factory in deps.py. 4 seeded staff users (live-confirmed: staff_users=4). pytest 105 passed including test_rbac.py. |
| REQ-nfr-security | 01-01, 01-03, 01-04, 01-07 | HTTPS; secrets in .env; argon2 hashing; audit_log | VERIFIED (conditional) | argon2 confirmed. _DUMMY_HASH real KDF. CORS non-wildcard. JWT_SECRET ≥32 chars enforced. 8 required secrets with no defaults. HSTS in nginx.conf (prod); dev intentionally HTTP-only. Browser CORS/cookie flow deferred to human check. |
| REQ-nfr-observability | 01-01, 01-02, 01-04, 01-06 | Structured logs; /health page; CI quality gates | VERIFIED | structlog JSON confirmed. /health returns `{"status":"ok","db":"ok","redis":"ok","schema_version":"0001"}` (live). CI ruff/mypy/pytest confirmed locally; dashboard tsc fix in place; live CI run is human-needed. |
| REQ-nfr-time-localization | 01-01, 01-02 | All timestamps UTC in DB; Asia/Tashkent display | VERIFIED | 25 TIMESTAMP(timezone=True) columns in migration (confirmed). to_display_tz() with _DEFAULT_TZ = "Asia/Tashkent" in time.py. |

**Orphaned requirement IDs:** None. All four Phase 1 requirements are accounted for.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `deploy/docker-compose.dev.yml` | 105, 126 | worker and beat reference `app.tasks.celery_app` which does not exist | INFO | Formally accepted deferral per ROADMAP.md SC#1 amendment and STATE.md Deferred Items. Worker/beat will idle/crash-loop until Phase 2 builds app.tasks. Not a Phase 1 blocker. |
| `.github/workflows/ci.yml` | 161 | `build-images` job builds `deploy/Dockerfile.backend` while compose builds `backend/Dockerfile` | WARNING (WR-02) | CI validates a different image than compose runs. Both Dockerfiles exist and are behaviourally equivalent, but a change to backend/Dockerfile is not caught by the CI image-build gate. |
| `backend/app/main.py` | 72–73 | `docs_url="/docs"` and `redoc_url="/redoc"` unconditional | INFO (WR-06) | OpenAPI schema always exposed including in production. Not a Phase 1 blocker; should be gated via env var before production deployment. |

No `TBD`, `FIXME`, or `XXX` markers in any file modified by this round of fixes (commits 33d508d, 56859a0, b004e0e). Zero matches confirmed.

---

## Human Verification Required

### 1. Full CI Pipeline — Live Run (All 5 Jobs)

**Test:** Push a commit to main or develop. Observe all 5 GitHub Actions jobs: backend, dashboard, webapp, build-images.
**Expected:** Backend job: ruff check 0 violations, mypy app/services 0 errors, mypy app/schemas 0 errors, pytest 105 passed 17 skipped — all confirmed locally. Dashboard job: eslint --max-warnings 0 passes; `npx next typegen` generates `.next/types/routes.d.ts`; `tsc --noEmit` exits 0. Webapp job: eslint + tsc pass. build-images: deploy/Dockerfile.backend and deploy/Dockerfile.dashboard build successfully.
**Why human:** Requires a live CI runner. The `next typegen` fix (SC#5 WR-01) has only been validated locally. A clean GitHub Actions checkout must confirm typegen generates the routes file and tsc passes without TS2307. All backend gates are locally confirmed.

### 2. Browser CORS and httpOnly Cookie Flow

**Test:** With the dev stack running (api at http://localhost), load the dashboard dev server at http://localhost:3000. Submit valid staff credentials. Open DevTools → Network → observe the /api/v1/auth/refresh response.
**Expected:** Browser attaches the httpOnly refresh cookie; response 200 + access token. No CORS errors in console.
**Why human:** Browser CORS enforcement and httpOnly cookie attachment cannot be verified programmatically. Confirms REQ-nfr-security browser-level behavior.

---

## Gaps Summary

No open gaps remain. All three gaps from re-verification #2 are closed:

- **SC#1 (worker/beat):** Formally deferred via ROADMAP.md SC#1 amendment (commit b004e0e) and STATE.md Deferred Items. In-scope Phase 1 surface (api/postgres/redis/nginx + /health) is live-confirmed. Override accepted.
- **SC#2 (migration not auto-applied):** Fixed (commit 33d508d). Compose api pre-start command now runs entrypoint + seed before uvicorn. sa.Real() crash fixed to sa.REAL(). Lifespan hook added. Live-verified: schema_version="0001", 22 tables, v_live_feed, seed data present on clean stack.
- **SC#5 (dashboard tsc fails on clean CI):** Fixed (commit 56859a0). `npx next typegen` step added before tsc in dashboard CI job. Locally validated: typegen exits 0, tsc exits 0, eslint exits 0.

Phase goal is achieved at the code level. Two standard human verification items remain (live CI run + browser cookie flow) before phase can be marked fully complete.

---

## Outstanding Open Issues (Not Phase-1 Goal Blockers, Must Fix Before Production)

| Finding | File | Must Fix Before |
|---------|------|-----------------|
| WR-02: CI build-images builds deploy/Dockerfile.backend; compose builds backend/Dockerfile | `.github/workflows/ci.yml` | Phase 2 (any infra change to backend image) |
| WR-03: is_active checked after verify_password — timing oracle on deactivated accounts | `backend/app/services/auth_service.py:64-70` | Phase 4 (dashboard auth with real users) |
| WR-04: decode_token interpolates attacker-controlled claim into exception message | `backend/app/core/security.py:189-197` | Phase 4 |
| WR-05: restart: unless-stopped + env_file required: false causes crash-loop on missing .env | `deploy/docker-compose.dev.yml` | Before ops deployment |
| WR-06: docs_url/redoc_url always exposed | `backend/app/main.py:72-73` | Before production |

---

_Verified: 2026-06-15T15:00:00Z_
_Verifier: Claude (gsd-verifier)_
_Mode: Re-verification #3 (after second round of gap fixes: commits 33d508d, 56859a0, b004e0e)_
