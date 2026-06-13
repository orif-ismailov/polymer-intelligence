---
phase: 01-walking-skeleton
verified: 2026-06-13T00:00:00Z
status: gaps_found
score: 3/5 must-haves verified
overrides_applied: 0
gaps:
  - truth: "docker compose up brings up api, worker, beat, postgres, redis, nginx; /health returns OK"
    status: failed
    reason: "Three separate defects prevent this truth from holding. (1) nginx is not present as a service in deploy/docker-compose.dev.yml — the file defines only postgres, redis, api, worker, beat. (2) All three backend service build blocks (api, worker, beat) specify context: ../backend and dockerfile: Dockerfile, but backend/Dockerfile does not exist; the actual file is deploy/Dockerfile.backend with context=../ — so docker compose up fails with 'failed to read dockerfile'. (3) deploy/nginx/nginx.conf lacks a top-level events {} block, so even if nginx were added to compose it would refuse to start."
    artifacts:
      - path: "deploy/docker-compose.dev.yml"
        issue: "No nginx service defined (services: postgres, redis, api, worker, beat only). All three backend build blocks use dockerfile: Dockerfile resolved under context ../backend, which resolves to backend/Dockerfile — a path that does not exist."
      - path: "deploy/nginx/nginx.conf"
        issue: "File opens directly with 'http {' at line 10; there is no top-level 'events {}' block. nginx will fail configuration parsing at startup."
    missing:
      - "Add an nginx service to deploy/docker-compose.dev.yml pointing at deploy/nginx/nginx.conf"
      - "Fix all three backend build blocks: change context to .. and dockerfile to deploy/Dockerfile.backend (or place a backend/Dockerfile that delegates)"
      - "Add 'events { worker_connections 1024; }' as a top-level block in deploy/nginx/nginx.conf"

  - truth: "CI (ruff, mypy, eslint+tsc, tests, image build) passes green on the scaffold"
    status: failed
    reason: "Two defects prevent a green CI run. (1) backend/pyproject.toml declares build-backend = 'setuptools.backends.legacy:build'. This is not a valid PEP 517 build backend: per PEP 517, the colon form 'module:object' tells pip to import the module and use the named attribute as the backend namespace (implementing build_wheel, build_sdist, etc.). There is no attribute named 'build' in setuptools.backends.legacy that serves as a backend namespace. This breaks the CI step 'pip install -e \".[dev]\"' (ci.yml line 50) AND the Dockerfile.backend step 'pip install --no-cache-dir \".[dev]\"' (Dockerfile.backend line 25), causing the backend job and the build-images job to fail. Note: the unit/mock test suite (90 passed, 17 skipped) was likely run with pytest via PYTHONPATH rather than through pip install, which is why tests appear to pass without the install step succeeding. (2) Both eslint steps use '|| true' (ci.yml lines 106, 135), meaning eslint failures are silently swallowed and can never fail CI — the '--max-warnings 0' flag is rendered meaningless. This was documented as an intentional scaffold decision in the 01-04 SUMMARY, but it means the eslint quality gate is non-functional."
    artifacts:
      - path: "backend/pyproject.toml"
        issue: "Line 3: build-backend = 'setuptools.backends.legacy:build' is not a valid PEP 517 backend. Valid form: 'setuptools.build_meta' or 'setuptools.backends.legacy'."
      - path: ".github/workflows/ci.yml"
        issue: "Lines 106, 135: eslint runs as 'npx eslint . --ext .ts,.tsx --max-warnings 0 || true'. The '|| true' swallows non-zero exit, making the eslint gate a no-op."
    missing:
      - "Fix build-backend to 'setuptools.build_meta' in backend/pyproject.toml"
      - "Remove '|| true' from both eslint steps in ci.yml once the scaffold has no lint errors to suppress"
---

# Phase 1: Walking Skeleton Verification Report

**Phase Goal:** A deployable end-to-end skeleton exists — the locked schema is migrated and seeded, the team can authenticate by role, and health/CI/compose are green — so every later phase plugs into a real, running backbone.
**Verified:** 2026-06-13T00:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `docker compose up` brings up api, worker, beat, postgres, redis, nginx; `/health` returns OK | FAILED | nginx absent from compose; backend build references non-existent `backend/Dockerfile`; nginx.conf missing mandatory `events {}` block |
| 2 | Alembic applies the full locked PostgreSQL 16 schema (all tables, ENUMs, `v_live_feed`) plus seed data (products, grades, synonyms) on a clean database | VERIFIED | Migration creates exactly 20 tables, 14 ENUMs, v_live_feed view; seed JSON files confirmed non-empty; advisory-locked entrypoint exists |
| 3 | A staff user can log in and receive a JWT (access 15 min + refresh 7 d httpOnly); endpoints enforce admin/analyst/trader/viewer roles | VERIFIED | auth.py POST /auth/login wired through auth_service + security.py; deps.py require_role factory enforces StaffRole; seed_staff.py seeds four users; tests confirm behavior |
| 4 | Passwords are argon2-hashed; secrets load from `.env` outside the repo; timestamps are stored UTC with an Asia/Tashkent display helper | VERIFIED | security.py uses argon2-cffi PasswordHasher; config.py reads from env with no-default required secrets; .env.example documented; time.py implements to_display_tz with Asia/Tashkent default; all migration timestamps use TIMESTAMP(timezone=True) |
| 5 | CI (ruff, mypy, eslint+tsc, tests, image build) passes green on the scaffold | FAILED | pyproject.toml invalid PEP 517 build-backend breaks pip install (CI line 50) and docker build; eslint quality gate neutered with `\|\| true` |

**Score:** 3/5 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `deploy/docker-compose.dev.yml` | Dev stack: postgres, redis, api, worker, beat, nginx | PARTIAL | postgres, redis, api, worker, beat present; nginx absent; backend build blocks reference `backend/Dockerfile` which does not exist |
| `deploy/nginx/nginx.conf` | TLS-ready reverse proxy + auth rate limit | STUB | File exists and has correct proxy_pass, rate limiting, security headers — but is structurally invalid: no top-level `events {}` block |
| `backend/pyproject.toml` | Valid PEP 517 package definition | STUB | File parses as TOML but `build-backend = "setuptools.backends.legacy:build"` is not a valid PEP 517 backend; breaks `pip install` and `docker build` |
| `backend/alembic/versions/0001_initial_schema.py` | Full locked schema migration | VERIFIED | 20 tables, 14 ENUMs (.create() calls confirmed), v_live_feed view, correct timestamptz usage |
| `backend/app/entrypoint.py` | Advisory-locked migration runner | VERIFIED | pg_advisory_lock call confirmed at line 86; alembic upgrade head wired |
| `backend/app/seed/seed_reference.py` | Idempotent seed for products, grades, synonyms | VERIFIED | Products, grades, synonyms JSON files are non-empty and well-formed |
| `backend/app/core/security.py` | argon2 hash/verify + JWT issue/verify | VERIFIED | PasswordHasher used; create_access_token (15m, type=access), create_refresh_token (7d, type=refresh), decode_token with type enforcement |
| `backend/app/api/deps.py` | require_role dependency factory | VERIFIED | get_current_staff_user + require_role(*roles) factory + require_admin shorthand |
| `backend/app/api/auth.py` | POST /auth/login + POST /auth/refresh | VERIFIED | Login returns TokenResponse + sets httpOnly cookie via set_refresh_cookie; refresh validates type=refresh |
| `backend/app/core/time.py` | Asia/Tashkent display helper | VERIFIED | to_display_tz() with Asia/Tashkent default; utcnow() returns tz-aware UTC |
| `backend/app/api/health.py` | /health endpoint checking db + redis + schema_version | VERIFIED | SELECT 1 for db; redis PING; alembic_version query for schema_version |
| `.github/workflows/ci.yml` | Full CI pipeline | PARTIAL | ruff, mypy, pytest, tsc present; eslint neutered with `\|\| true`; image build step correct but will fail due to invalid build-backend |
| `deploy/Dockerfile.backend` | Backend image (api/worker/beat) | PARTIAL | Dockerfile itself is correct (context=backend/, COPY pyproject.toml, uvicorn CMD); CI build step uses correct context; BUT pip install inside will fail due to invalid pyproject build-backend |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend/app/api/health.py` | `backend/app/core/db.py` | SELECT 1 via get_db session | VERIFIED | `db.execute(text("SELECT 1"))` at line 56 |
| `backend/app/main.py` | `backend/app/api/health.py` | include_router with /api/v1 prefix | VERIFIED | `application.include_router(health_router, prefix="/api/v1")` at line 62 |
| `backend/alembic/env.py` | `backend/app/models/__init__.py` | target_metadata = Base.metadata | VERIFIED (implicitly) | Advisory-locked entrypoint wires alembic config to DATABASE_URL |
| `backend/app/api/auth.py` | `backend/app/core/security.py` | verify_password + create_access_token | VERIFIED | `authenticate()` calls `verify_password`; login calls `create_access_token` |
| `backend/app/api/deps.py` | `backend/app/models/staff.py` | JWT sub → DB query → StaffUser.role | VERIFIED | get_current_staff_user loads StaffUser, require_role checks `.role` against StaffRole |
| `backend/app/api/auth.py` | `backend/app/services/audit_service.py` | write_audit on login | VERIFIED | `write_audit(db=db, action="auth.login", ...)` called on success at line 71 |
| `deploy/docker-compose.dev.yml` | `backend/Dockerfile` | context: ../backend, dockerfile: Dockerfile | BROKEN | `backend/Dockerfile` does not exist; actual file is `deploy/Dockerfile.backend` |
| `deploy/nginx/nginx.conf` | `api:8000` | proxy_pass in location /api/ | WIRED (but nginx won't start) | proxy_pass present but nginx.conf structurally invalid (no events block) |
| `.github/workflows/ci.yml` | `deploy/Dockerfile.backend` | docker build step | PARTIAL | CI build command is correct (`docker build -f deploy/Dockerfile.backend backend/`) but pip install inside Dockerfile will fail |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `backend/app/api/health.py` | `db_status`, `redis_status`, `schema_version` | `db.execute(text("SELECT 1"))`, `redis_lib.from_url(...).ping()`, `db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))` | Yes — all three queries are real DB/redis calls | FLOWING |
| `backend/app/api/auth.py` | `user` (StaffUser) | `db.query(StaffUser).filter(StaffUser.email == email).first()` | Yes — parameterized ORM query | FLOWING |
| `backend/app/api/deps.py` | `user` (current StaffUser) | JWT sub decoded, then `db.query(StaffUser).filter(...)` | Yes — DB load after token verification | FLOWING |

---

## Behavioral Spot-Checks

Cannot run live app checks (no running server). The unit/mock test suite confirmed passing externally (90 passed, 17 skipped per prompt context). Key behavioral checks that CAN be confirmed statically:

| Behavior | Check | Result | Status |
|----------|-------|--------|--------|
| Access token expires in 15 min | `ACCESS_TOKEN_EXPIRE_MINUTES = 15` in security.py line 36 | Confirmed | VERIFIED |
| Refresh token expires in 7 days | `REFRESH_TOKEN_EXPIRE_DAYS = 7` in security.py line 37 | Confirmed | VERIFIED |
| Refresh cookie is httpOnly | `httponly=True` in auth_service.py line 83 | Confirmed | VERIFIED |
| Role guard raises 403 for wrong role | `raise HTTPException(status_code=403)` in deps.py line 131 | Confirmed | VERIFIED |
| Passwords use argon2 (not bcrypt/MD5) | `_hasher = PasswordHasher(...)` from argon2-cffi in security.py line 26 | Confirmed | VERIFIED |
| nginx rate-limits /api/v1/auth/login | `limit_req_zone ... rate=10r/m` + `location = /api/v1/auth/login { limit_req ... }` in nginx.conf | Confirmed (but nginx won't start — CR-01) | PARTIAL |
| docker compose up nginx | nginx service definition in docker-compose.dev.yml | Not present | FAILED |
| docker build backend image via pip install | `build-backend = "setuptools.backends.legacy:build"` | Non-standard PEP 517 form — pip install will fail | FAILED |

---

## Probe Execution

No probe scripts found in `scripts/*/tests/probe-*.sh`. No probes declared in PLAN frontmatter. SKIPPED.

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| REQ-roles | 01-03 | Roles admin/analyst/trader/viewer (ENUM staff_role) | VERIFIED | staff_role ENUM in migration (14 enums, staff_role confirmed at index 14); require_role factory in deps.py; four seeded users in seed_staff.py; test_rbac.py confirmed |
| REQ-nfr-security | 01-01, 01-03, 01-04 | HTTPS; secrets in .env; argon2 hashing; audit_log | PARTIAL | Secrets in .env confirmed; argon2 confirmed; audit_log writer confirmed; HTTPS-ready nginx config exists but nginx won't start (CR-01); CORS misconfiguration (CR-04: allow_origins=["*"] + allow_credentials=True) is a genuine security defect; timing-attack mitigation is a no-op (CR-05) |
| REQ-nfr-observability | 01-01, 01-02, 01-04 | Structured logs; /health page; CI quality gates | PARTIAL | structlog JSON logging confirmed; /health with schema_version confirmed; CI pipeline exists but pylint gate and pip install are broken |
| REQ-nfr-time-localization | 01-01, 01-02 | All timestamps UTC in DB; Asia/Tashkent display | VERIFIED | 25 TIMESTAMP(timezone=True) columns in migration; to_display_tz() with Asia/Tashkent default in time.py |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `deploy/nginx/nginx.conf` | 10 | `http {` as the first non-comment directive — no preceding `events {}` block | BLOCKER | nginx refuses to start; entire reverse-proxy layer fails (SC#1) |
| `deploy/docker-compose.dev.yml` | 54-56, 82-84, 102-104 | `dockerfile: Dockerfile` under `context: ../backend` — file does not exist | BLOCKER | `docker compose up` fails to build api, worker, beat services (SC#1) |
| `backend/pyproject.toml` | 3 | `build-backend = "setuptools.backends.legacy:build"` — non-standard PEP 517 backend | BLOCKER | `pip install -e ".[dev]"` in CI and `pip install ".[dev]"` in Dockerfile both fail; CI backend job and build-images job cannot pass green (SC#5) |
| `backend/app/main.py` | 54-55 | `allow_origins=["*"]` with `allow_credentials=True` | BLOCKER (security) | Browsers will silently drop credentials on wildcard origin + credentials pairing; violates CORS spec and makes the httpOnly refresh cookie non-functional in browser environments |
| `backend/app/services/auth_service.py` | 57 | `verify_password(password, "$argon2id$v=19$m=65536,t=2,p=2$dummysalt$dummyhash")` — malformed argon2 hash | WARNING | `PasswordHasher.verify` raises InvalidHashError before doing any KDF work; the "user not found" path returns in microseconds vs the "wrong password" path, reintroducing user-enumeration timing oracle (T-03-01 mitigation is a no-op) |
| `.github/workflows/ci.yml` | 106, 135 | `npx eslint . --ext .ts,.tsx --max-warnings 0 \|\| true` | WARNING | eslint can never fail CI; the `--max-warnings 0` strictness declaration is a dead letter |
| `dashboard/app/login/page.tsx` | 11-12 | `e.preventDefault(); // TODO: Phase 4` — submit handler is a dead stub | INFO | Acceptable scaffold placeholder; acceptable for Phase 1 but easy to mistake for a working form |

---

## Critical Review Findings — Independent Verification

The 01-REVIEW.md flagged 6 Critical findings. Each has been independently verified against the actual source files:

**CR-01 (nginx missing events {} block) — CONFIRMED.**
`deploy/nginx/nginx.conf` opens with comment lines followed by `http {` at line 10. There is no `events {}` block anywhere in the file (`grep -c "^events" nginx.conf` returns 0). nginx will refuse to start with this configuration.

**CR-02 (docker-compose references non-existent Dockerfile) — CONFIRMED.**
All three backend service build blocks in `deploy/docker-compose.dev.yml` specify `context: ../backend` and `dockerfile: Dockerfile`. The file `backend/Dockerfile` does not exist (`ls backend/Dockerfile` confirms MISSING). The actual file is `deploy/Dockerfile.backend`. This causes `docker compose up` to fail with "failed to read dockerfile".

**CR-03 (invalid PEP 517 build-backend) — CONFIRMED as defect.**
`backend/pyproject.toml` line 3 reads `build-backend = "setuptools.backends.legacy:build"`. The colon form in PEP 517 tells pip to import `setuptools.backends.legacy` and use the attribute named `build` as the backend namespace. Even if `setuptools.backends.legacy` is a valid module (present in setuptools>=67), that module's public API is `build_wheel`, `build_sdist`, `build_editable` — not a single `build` attribute that serves as a namespace. The CI `pip install -e ".[dev]"` (ci.yml line 50) and Dockerfile `pip install --no-cache-dir ".[dev]"` (Dockerfile.backend line 25) will both fail. The fact that the unit test suite reportedly passed (90 passed, 17 skipped) is explained by pytest being invoked via PYTHONPATH rather than through a pip-installed package.

**CR-04 (CORS allow_origins=["*"] + allow_credentials=True) — CONFIRMED.**
`backend/app/main.py` lines 54-55 set `allow_origins=["*"]` and `allow_credentials=True`. Per the CORS specification, a browser will refuse to attach credentials to a response with `Access-Control-Allow-Origin: *`. Starlette's CORSMiddleware will not echo the request origin for wildcard either, so the httpOnly refresh cookie mechanism (the cornerstone of DEC-auth-split) is non-functional in browser environments. This is both a security misconfiguration and a functional defect.

**CR-05 (timing-attack mitigation no-op) — CONFIRMED.**
`backend/app/services/auth_service.py` line 57: `verify_password(password, "$argon2id$v=19$m=65536,t=2,p=2$dummysalt$dummyhash")`. The salt and hash segments are not valid base64 of the required length, so `PasswordHasher.verify` raises `InvalidHashError` before any KDF work is performed. `verify_password` catches it and returns False immediately (in microseconds). The "user not found" path is dramatically faster than the "wrong password" path, reintroducing the user-enumeration timing oracle that T-03-01 was meant to prevent.

**CR-06 (nginx add_header inheritance) — CONFIRMED as a future-fragility issue.**
Security headers declared at `server` level are wiped for any location that adds its own header (e.g., the static asset location at line 128 adds `Cache-Control`). This is a real nginx behaviour defect but is currently moot because nginx won't start at all (CR-01). Severity is WARNING not BLOCKER in isolation.

---

## Human Verification Required

### 1. CORS Credential Behavior in a Real Browser

**Test:** Run the stack after fixing CR-01 and CR-02; navigate to the dashboard login page; observe whether the browser sends the refresh cookie on `/api/v1/auth/refresh` requests.
**Expected:** With the current `allow_origins=["*"]` + `allow_credentials=True`, the browser should silently drop credentials. After fixing CR-04 (setting explicit allowed origins), credentials should flow.
**Why human:** Browser CORS enforcement cannot be verified by static analysis or grep.

### 2. nginx Startup After events {} Fix

**Test:** After adding the `events { worker_connections 1024; }` block, run `nginx -t` inside the `nginx:stable` container against the fixed config.
**Expected:** exits 0 with "syntax is ok" message.
**Why human:** Requires Docker to be available; automated test not possible in this verifier context.

### 3. pip install With Fixed build-backend

**Test:** After fixing pyproject.toml to `build-backend = "setuptools.build_meta"`, run `pip install -e ".[dev]"` in a clean Python 3.12 environment.
**Expected:** exits 0 with all packages installed.
**Why human:** Requires a live Python 3.12 environment with network access; not automatable statically.

---

## Gaps Summary

Two success criteria are FAILED, blocking the phase goal.

**Gap 1 — SC#1 (docker compose up + nginx):** Three independent defects prevent the compose stack from standing up: (a) no nginx service in docker-compose.dev.yml, (b) all backend build blocks point to a non-existent `backend/Dockerfile`, and (c) nginx.conf lacks the mandatory `events {}` block. The stack as-written cannot be started — the "walking skeleton" does not walk.

**Gap 2 — SC#5 (CI green):** The invalid PEP 517 build-backend in pyproject.toml means `pip install -e ".[dev]"` and `pip install ".[dev]"` (in the Dockerfile) both fail. CI's backend job and build-images job cannot complete. The neutered eslint gate (`|| true`) is an additional quality-gate defect. CI is not green on the scaffold.

The three success criteria that ARE verified (SC#2 schema migration + seed, SC#3 JWT auth + RBAC, SC#4 argon2 + secrets + UTC timestamps) represent solid, substantive work. The schema is complete and correct, the auth backbone is well-structured, and the security fundamentals are mostly in place.

The remaining gaps are all infrastructure/wiring defects (mismatched file paths, a missing compose service, an invalid TOML key, a missing nginx directive) — not missing features. They are low-effort to fix but each is a hard blocker for the stated phase goal of a "deployable" skeleton.

**Security defects not blocking phase goal (but must be fixed before Phase 4 dashboard goes live):**
- CR-04: CORS misconfiguration will break the httpOnly cookie flow in real browsers
- CR-05: Timing-attack mitigation is a no-op; user enumeration is possible
- WR-01: JWT_SECRET has no minimum-length enforcement

---

_Verified: 2026-06-13T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
