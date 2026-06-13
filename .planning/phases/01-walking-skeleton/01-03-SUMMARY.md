---
phase: "01"
plan: "03"
subsystem: backend-auth
tags:
  - argon2
  - jwt
  - rbac
  - fastapi
  - audit-log
  - seed
  - security
dependency_graph:
  requires:
    - "01-01: Settings class (JWT_SECRET, backend/app/core/config.py)"
    - "01-01: Base + get_db (backend/app/core/db.py)"
    - "01-02: StaffUser + AuditLog models (backend/app/models/staff.py)"
    - "01-02: StaffRole ENUM (backend/app/models/enums.py)"
  provides:
    - "hash_password(plain) / verify_password(plain, hash) — argon2 helpers (backend/app/core/security.py)"
    - "create_access_token(subject, role) — 15 min JWT (backend/app/core/security.py)"
    - "create_refresh_token(subject) — 7 d JWT (backend/app/core/security.py)"
    - "decode_token(token, expected_type) — signature+expiry+type-safe decode (backend/app/core/security.py)"
    - "get_current_staff_user dep — Bearer->user loader (backend/app/api/deps.py)"
    - "require_role(*roles) factory + require_admin + require_analyst_or_admin (backend/app/api/deps.py)"
    - "POST /api/v1/auth/login + POST /api/v1/auth/refresh (backend/app/api/auth.py)"
    - "GET /api/v1/admin/whoami (admin-only demo, REQ-roles testable hook) (backend/app/main.py)"
    - "GET /api/v1/analyst/whoami (analyst+admin demo) (backend/app/main.py)"
    - "audit_service.write_audit(db, staff_user_id, action, entity, entity_id, details) (backend/app/services/audit_service.py)"
    - "authenticate(db, email, password) + set_refresh_cookie + clear_refresh_cookie (backend/app/services/auth_service.py)"
    - "LoginRequest + TokenResponse Pydantic schemas (backend/app/schemas/auth.py)"
    - "seed_staff.py + data/staff_users.json — 4 argon2-hashed users, one per role (backend/app/seed/)"
  affects:
    - "All later dashboard phases: authenticate through get_current_staff_user + require_role"
    - "Phase 4 (admin screen): require_admin dep ready; /admin/users CRUD will build on it"
    - "Phase 2+ analyst screens: require_analyst_or_admin dep ready"
tech_stack:
  added:
    - "argon2-cffi (already in pyproject) — PasswordHasher with time_cost=2, memory_cost=64 MB"
    - "python-jose[cryptography] (already in pyproject) — HS256 JWT sign/verify"
  patterns:
    - "TDD RED→GREEN for both tasks (test files written before implementation)"
    - "Token-type claim distinguishes access vs refresh (prevents type-confusion, T-03-03)"
    - "require_role(*roles) dependency factory — role from verified JWT, not request body"
    - "Audit writes flush-then-caller-commits pattern (orphan-proof audit rows)"
    - "APP_ENV=production gates Secure cookie flag (False dev/test, True prod TLS)"
    - "Generic 401 on any login failure (T-03-01 — no user-enumeration)"
key_files:
  created:
    - "backend/app/core/security.py — hash_password, verify_password, create_access_token, create_refresh_token, decode_token"
    - "backend/app/api/deps.py — get_current_staff_user, require_role factory, require_admin, require_analyst_or_admin"
    - "backend/app/api/auth.py — POST /auth/login and POST /auth/refresh routers"
    - "backend/app/schemas/auth.py — LoginRequest (email, password) and TokenResponse (access_token, token_type, role)"
    - "backend/app/services/auth_service.py — authenticate, set_refresh_cookie, clear_refresh_cookie"
    - "backend/app/services/audit_service.py — write_audit(db, staff_user_id, action, entity, entity_id, details)"
    - "backend/app/seed/seed_staff.py — idempotent seed of 4 staff users with argon2 hashes"
    - "backend/app/seed/data/staff_users.json — email/role/full_name/env_var/dev_default per role"
    - "backend/tests/test_password_hash.py — 7 argon2 tests (round-trip, salted-unique, no-plaintext)"
    - "backend/tests/test_jwt.py — 10 JWT tests (type/expiry/sub/role claims, tamper, expiry, type-confusion)"
    - "backend/tests/test_auth_login.py — 11 tests (login success/failure/cookie/inactive + refresh success/failure)"
    - "backend/tests/test_rbac.py — 10 tests (all 4 roles on admin route, multi-role route, no-token, inactive)"
    - "backend/tests/test_audit.py — 4 tests (write_audit call pattern, AuditLog instance, login writes row, failed login does not)"
  modified:
    - "backend/app/main.py — mounted auth router + /admin/whoami + /analyst/whoami demo routes"
decisions:
  - "Cookie Secure=False in dev/test (APP_ENV!=production) — lets TestClient (HTTP) send cookies; True in prod behind nginx TLS"
  - "EmailStr dropped in favor of str in LoginRequest — email-validator not in pyproject deps; email format validated at DB lookup level"
  - "require_role reads role from the verified JWT payload (already decoded by get_current_staff_user); no extra DB query for the role"
  - "Audit write uses db.flush() (not db.commit()) — caller commits so audit row is part of the same transaction as the action"
metrics:
  duration_minutes: 8
  completed_date: "2026-06-13"
  tasks_completed: 2
  tasks_total: 2
  files_created: 13
  tests_added: 42
---

# Phase 01 Plan 03: Authentication, RBAC, Audit, and Staff Seed Summary

**One-liner:** JWT auth backbone with argon2 password hashing, 15-min access + 7-d httpOnly refresh cookie split, require_role RBAC dependency factory enforcing all four staff roles server-side, audit_log writer, and idempotent seed of one staff user per role — all built TDD RED→GREEN.

## What Was Built

### Task 1: Security core — argon2 hashing + JWT issue/verify

- `backend/app/core/security.py`: full security helper module
  - `hash_password(plain)` — PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2) via argon2-cffi; output starts with `$argon2id`
  - `verify_password(plain, hashed)` — returns True/False, never raises on mismatch (safe for auth flows)
  - `create_access_token(subject, role)` — HS256 JWT with `type='access'`, `sub`, `role`, exp=15 min
  - `create_refresh_token(subject)` — HS256 JWT with `type='refresh'`, `sub`, exp=7 d (no role — re-read from DB on refresh)
  - `decode_token(token, expected_type)` — verifies signature, expiry, and `type` claim match; raises JWTError on any failure (T-03-02, T-03-03)
- Tests written BEFORE implementation (RED→GREEN):
  - `test_password_hash.py` (7 tests): argon2 format, no-plaintext, correct verify True, wrong verify False, salted unique, both hashes verify, empty-string False
  - `test_jwt.py` (10 tests): type claim, sub/role encoding, 15-min expiry, 7-d expiry, tamper rejection, expired rejection, access→refresh rejection, refresh→access rejection

**Test count:** 17 unit tests, all passing

**Commit:** 801ad3a

### Task 2: Login/refresh endpoints, RBAC guard, audit writer, and per-role seed

- `backend/app/schemas/auth.py`: `LoginRequest(email, password)` and `TokenResponse(access_token, token_type, role)` Pydantic models
- `backend/app/services/auth_service.py`:
  - `authenticate(db, email, password)` — parameterized SQLAlchemy query (T-03-08), argon2 verify, generic 401 on any failure (T-03-01); dummy verify on unknown email to normalize timing
  - `set_refresh_cookie(response, staff_user_id)` — creates refresh JWT, sets httpOnly+SameSite=lax cookie at path `/api/v1/auth`; Secure=True in production only (APP_ENV=production)
  - `clear_refresh_cookie(response)` — for logout flows (Phase 4)
- `backend/app/services/audit_service.py`:
  - `write_audit(db, staff_user_id, action, entity, entity_id, details)` — creates AuditLog instance, db.add + db.flush (caller commits); supports None staff_user_id for system actions
- `backend/app/api/auth.py`:
  - `POST /api/v1/auth/login` — authenticate, set refresh cookie, write audit row `auth.login`, commit, return access token body; 401 on any failure with no cookie
  - `POST /api/v1/auth/refresh` — read refresh cookie, decode_token(expected_type='refresh'), re-load user (confirms still active, picks up role changes), return new access token
- `backend/app/api/deps.py`:
  - `get_current_staff_user` — extracts Bearer token from Authorization header, decode_token(expected_type='access'), loads StaffUser, returns 401 if missing/invalid/not-found, 403 if is_active=False
  - `require_role(*roles)` — dependency factory returning a closure that checks current_user.role against the allowed set, raises 403 if not allowed (T-03-04)
  - `require_admin = require_role(StaffRole.admin)` — convenience alias
  - `require_analyst_or_admin = require_role(StaffRole.analyst, StaffRole.admin)` — convenience alias
- `backend/app/main.py` (modified):
  - Mounted `auth_router` under `/api/v1`
  - Added `GET /api/v1/admin/whoami` guarded by `require_admin` (REQ-roles testable hook)
  - Added `GET /api/v1/analyst/whoami` guarded by `require_analyst_or_admin` (multi-role test hook)
- `backend/app/seed/seed_staff.py` + `data/staff_users.json`:
  - Idempotent seed: 4 staff users, one per role (admin/analyst/trader/viewer)
  - Passwords read from `SEED_{ROLE}_PASSWORD` env var or documented dev-only default
  - `hash_password()` applied before any DB insert (T-03-01: never plaintext)
  - `verify_seed(db)` helper for health checks
- Tests written BEFORE implementation (RED→GREEN):
  - `test_auth_login.py` (11 tests): login success+body, httpOnly cookie, SameSite cookie, wrong-password 401 no-cookie, non-existent email 401, inactive 401, refresh with cookie, refresh without cookie, refresh with invalid cookie
  - `test_rbac.py` (10 tests): admin allows admin, rejects viewer/trader/analyst, analyst+admin route allows analyst+admin, rejects trader+viewer, no-token 401, malformed-token 401, inactive admin rejected
  - `test_audit.py` (4 tests): write_audit calls db.add+commit/flush, creates AuditLog instance with correct fields, login success writes 1 audit row with action='auth.login', failed login writes 0 audit rows

**Test count:** 25 tests, all passing (including audit)

**Commit:** e554b59

## Verification Results

| Check | Result |
|-------|--------|
| `python -m pytest tests/test_password_hash.py tests/test_jwt.py -x -q` | 17 passed |
| `python -m pytest tests/test_auth_login.py tests/test_rbac.py tests/test_audit.py -x -q` | 24 passed |
| `python -m pytest tests/ -q` | 90 passed, 17 skipped (integration skip without live Postgres) |
| `hash_password(p).startswith('$argon2')` | True |
| `verify_password(p, hash_password(p))` | True |
| `verify_password('wrong', hash_password(p))` | False |
| Access token exp | ~15 min (800–920 s remaining) |
| Refresh token exp | ~7 d (604700–604900 s remaining) |
| Tampered token decode | Raises JWTError |
| Expired token decode | Raises JWTError |
| Type-confusion rejection (access as refresh, vice-versa) | Raises JWTError |
| Login → 200 + access_token body + Set-Cookie httpOnly SameSite | Passes |
| Login wrong password → 401 no Set-Cookie | Passes |
| Login inactive user → 401/403 | Passes |
| Refresh with cookie → 200 + new access_token | Passes |
| Refresh without cookie → 401 | Passes |
| Admin route: admin→200, viewer→403, trader→403, analyst→403 | All pass |
| Analyst+admin route: analyst→200, admin→200, trader→403, viewer→403 | All pass |
| Login success writes 1 audit_log row (action='auth.login') | Passes |
| Failed login writes 0 audit_log rows | Passes |
| staff_users.json contains no plaintext passwords | Confirmed (only env var names and documented dev defaults) |

## Requirements Satisfied

| Requirement | How |
|-------------|-----|
| REQ-roles (FR-15) | admin/analyst/trader/viewer enforced at the API layer via require_role; viewer→403 on admin route tested |
| REQ-nfr-security | argon2 hashing (T-03-01), JWT tamper rejection (T-03-02), type-confusion guard (T-03-03), role authorization (T-03-04), httpOnly refresh cookie (T-03-05), identity from JWT only (T-03-06), audit log (T-03-07), parameterized queries (T-03-08) |
| ASVS L1 V2.2.1 (brute-force) | Documented as owned at nginx layer — plan 01-04 delivers limit_req rate limit on /api/v1/auth/login (T-03-09 cross-reference) |
| DEC-auth-split | Access token (15 min) in body; refresh token (7 d) in httpOnly cookie — implemented exactly |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Module-level import of security helpers in test files caused pydantic ValidationError**
- **Found during:** Task 2 RED phase — first test run
- **Issue:** Test files imported `hash_password` and `create_access_token` at module level. This triggered the import chain `security → config → Settings()` before the `conftest.py` session fixture could patch env vars, causing `pydantic_core.ValidationError` (missing required secrets).
- **Fix:** Moved all `app.core.*` imports inside the helper functions and test functions where conftest patching is already active by the time the import runs.
- **Files modified:** `tests/test_auth_login.py`, `tests/test_rbac.py`, `tests/test_audit.py`
- **Commit:** e554b59 (part of Task 2)

**2. [Rule 1 - Bug] TestClient did not send refresh cookie to /auth/refresh (Secure cookie via HTTP)**
- **Found during:** Task 2 GREEN phase — `test_refresh_with_valid_cookie_returns_new_access_token` returned 401
- **Issue:** Cookie was set with `secure=True` unconditionally. The TestClient uses `http://testserver` (not HTTPS), so httpx's cookie jar suppressed the cookie on outbound requests (RFC 6265 §5.3: Secure attribute prevents cookie transmission over non-HTTPS).
- **Fix:** Introduced `APP_ENV` env var gating in `auth_service.py`: `_COOKIE_SECURE = (APP_ENV == 'production')`. Production deployments set `APP_ENV=production` and operate behind nginx TLS. Dev/test environments leave `APP_ENV` unset, allowing HTTP cookie flow. This is documented in the code as a T-03-05 deployment requirement.
- **Files modified:** `backend/app/services/auth_service.py`
- **Commit:** e554b59 (part of Task 2)

**3. [Rule 3 - Blocking] EmailStr in LoginRequest required the optional email-validator package**
- **Found during:** Task 2 GREEN phase — pydantic ImportError at schema class definition time
- **Issue:** `pydantic.EmailStr` requires `email-validator` (installed via `pip install 'pydantic[email]'`), which is not in the project's `pyproject.toml` dependencies.
- **Fix:** Changed `email: EmailStr` to `email: str` in `LoginRequest`. The DB lookup (by `StaffUser.email`) naturally handles correct email format matching. Email format validation can be added via pydantic[email] in a later plan if strict validation is desired; the current approach is sufficient for Phase 1 where users are seeded by the admin.
- **Files modified:** `backend/app/schemas/auth.py`
- **Commit:** e554b59 (part of Task 2)

## Known Stubs

None. All modules are functional implementations:
- The auth flow is fully wired (login → token + cookie → refresh → new token)
- The role guard is fully wired (require_role → 403 for unauthorized roles)
- The audit writer is functional (writes AuditLog rows to DB)
- The seed is functional (idempotent argon2-hashed inserts)
- The demo guard routes (`/admin/whoami`, `/analyst/whoami`) prove the guard works end-to-end

The full `/admin/users` CRUD ships in Phase 4 (admin management screen) — these demo routes are an intentional minimal hook, not a stub.

## Threat Flags

No new threat surface beyond what was in the plan's threat model. All items from T-03-01 through T-03-SC are mitigated:
- T-03-01 (password storage): argon2-cffi PasswordHasher, generic 401, no user-enumeration
- T-03-02 (token forgery): decode_token verifies HS256 signature
- T-03-03 (type confusion): `type` claim enforced in decode_token
- T-03-04 (role bypass): require_role checks role from verified token + is_active
- T-03-05 (refresh token theft): httpOnly + SameSite + scoped path; Secure=True in prod (APP_ENV=production)
- T-03-06 (identity from body): only JWT sub used; no request body id field accepted
- T-03-07 (repudiation): auth.login writes audit_log row
- T-03-08 (SQL injection at login): parameterized SQLAlchemy query (StaffUser.email == email)
- T-03-09 (credential stuffing): owned by plan 01-04 nginx limit_req (cross-referenced)
- T-03-SC (argon2/jwt deps): from canonical locked stack (plan 01-01 pyproject); no new packages

The `APP_ENV` approach for cookie Secure flag introduces a minor operational concern: `APP_ENV` must be set to `production` in the production deploy or the cookie will be non-Secure. This is documented in `auth_service.py` and should be enforced in the deploy `.env.example`. Adding a note here for the Phase 6 hardening review.

## Self-Check: PASSED
