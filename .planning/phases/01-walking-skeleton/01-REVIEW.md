---
phase: 01-walking-skeleton
reviewed: 2026-06-13T00:00:00Z
depth: standard
files_reviewed: 71
files_reviewed_list:
  - .github/workflows/ci.yml
  - backend/alembic.ini
  - backend/alembic/env.py
  - backend/alembic/versions/0001_initial_schema.py
  - backend/app/api/auth.py
  - backend/app/api/deps.py
  - backend/app/api/health.py
  - backend/app/core/config.py
  - backend/app/core/db.py
  - backend/app/core/logging.py
  - backend/app/core/security.py
  - backend/app/core/time.py
  - backend/app/entrypoint.py
  - backend/app/main.py
  - backend/app/models/__init__.py
  - backend/app/models/enums.py
  - backend/app/models/staff.py
  - backend/app/schemas/auth.py
  - backend/app/seed/__init__.py
  - backend/app/seed/data/staff_users.json
  - backend/app/seed/seed_reference.py
  - backend/app/seed/seed_staff.py
  - backend/app/services/audit_service.py
  - backend/app/services/auth_service.py
  - backend/pyproject.toml
  - backend/tests/conftest.py
  - backend/tests/test_auth_login.py
  - backend/tests/test_config.py
  - backend/tests/test_jwt.py
  - dashboard/app/login/page.tsx
  - dashboard/next.config.mjs
  - deploy/Dockerfile.backend
  - deploy/Dockerfile.dashboard
  - deploy/docker-compose.dev.yml
  - deploy/nginx/nginx.conf
  - webapp/src/App.tsx
findings:
  critical: 6
  warning: 8
  info: 4
  total: 18
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-06-13
**Depth:** standard
**Files Reviewed:** 71 (key source files traced; remaining model/test files read for context)
**Status:** issues_found

## Summary

The auth core (argon2 hashing, JWT issue/verify, token-type enforcement, RBAC dependency factory, audit-on-commit) is well structured and the type-confusion mitigations (T-03-03) are correctly implemented and tested. The migration captures the locked schema faithfully and the advisory-locked entrypoint follows the documented protocol.

However, this "walking skeleton" does not actually walk: several pieces of infrastructure are mis-wired badly enough that the stack will not build or run. The nginx config is missing the mandatory top-level `events {}` block (nginx refuses to start), the dev compose file points at a Dockerfile path that does not exist, and the backend `pyproject.toml` declares an invalid PEP 517 build backend that breaks `pip install` (and therefore the Docker image build and CI). There is also a genuine security misconfiguration: `CORS allow_origins=["*"]` with `allow_credentials=True`, plus a timing-attack mitigation that silently no-ops because its dummy argon2 hash is malformed.

## Critical Issues

### CR-01: nginx config missing mandatory `events {}` block — nginx will not start

**File:** `deploy/nginx/nginx.conf:10-139`
**Issue:** The file defines only an `http { ... }` block. A top-level nginx configuration **must** contain an `events { ... }` block; without it nginx fails configuration parsing at startup (`"events" directive is not allowed here` / `no "events" section in configuration`). The reverse proxy — the component that delivers the rate-limiting and security headers this phase is supposed to ship — never comes up.
**Fix:**
```nginx
# Add at the very top of the file, as a sibling of http {}
worker_processes auto;

events {
    worker_connections 1024;
}

http {
    # ... existing config ...
}
```

### CR-02: docker-compose references a non-existent Dockerfile path — backend build fails

**File:** `deploy/docker-compose.dev.yml:54-56` (also `82-84`, `102-104`)
**Issue:** Every backend service uses:
```yaml
build:
  context: ../backend
  dockerfile: Dockerfile
```
`dockerfile:` is resolved relative to `context:` (`../backend`), so this looks for `backend/Dockerfile`, which does not exist — the actual file is `deploy/Dockerfile.backend`. `docker compose up` fails with "failed to read dockerfile". The dev stack cannot be built.
**Fix:** Point at the real file via a context that contains it, e.g.:
```yaml
build:
  context: ..
  dockerfile: deploy/Dockerfile.backend
```
(adjust the `COPY` paths in `Dockerfile.backend`, which currently assume the build context is `backend/`), or add a `backend/Dockerfile`. Apply to `api`, `worker`, and `beat`.

### CR-03: Invalid PEP 517 build backend — `pip install` / image build / CI all break

**File:** `backend/pyproject.toml:3`
**Issue:** `build-backend = "setuptools.backends.legacy:build"` is not a real backend. The valid setuptools backend is `setuptools.build_meta` (or `setuptools.build_meta:__legacy__`). With this value, `pip install -e ".[dev]"` (CI step, line 50 of ci.yml) and `pip install ".[dev]"` (Dockerfile.backend:25) raise `Backend ... is not a callable` / import error, so the backend never installs anywhere.
**Fix:**
```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"
```

### CR-04: CORS `allow_origins=["*"]` with `allow_credentials=True`

**File:** `backend/app/main.py:52-58`
**Issue:** Combining a wildcard origin with `allow_credentials=True` is both a security misconfiguration and non-functional: per the CORS spec a server may not return `Access-Control-Allow-Origin: *` together with `Access-Control-Allow-Credentials: true`, and Starlette will not echo credentials for `*`. Since the auth design relies on a credentialed `httpOnly` refresh cookie (DEC-auth-split), this either silently drops credentials or, if "fixed" by reflecting the origin, allows any site to drive credentialed requests against the API. The inline comment ("tighten this in production") defers a control that should ship locked-down by default.
**Fix:** Drive the allowed origins from config and never pair `*` with credentials:
```python
application.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,  # explicit list, e.g. ["https://dashboard.example.com"]
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

### CR-05: Timing-attack mitigation is a no-op — malformed dummy argon2 hash

**File:** `backend/app/services/auth_service.py:55-58`; `backend/app/core/security.py:68-71`
**Issue:** When the user does not exist, the code calls `verify_password(password, "$argon2id$v=19$m=65536,t=2,p=2$dummysalt$dummyhash")` "to consume similar argon2 time." That string is not a valid argon2 encoded hash (the salt/hash segments are not valid base64 of the right length), so `PasswordHasher.verify` raises `InvalidHashError` **before** doing any KDF work. `verify_password` catches it and returns `False` immediately. The result: the "user not found" path is dramatically faster than the "wrong password" path, reintroducing exactly the user-enumeration timing oracle the code claims to prevent (T-03-01).
**Fix:** Generate a real dummy hash once at import and verify against it (the verify still fails, but performs full argon2 work):
```python
# security.py
_DUMMY_HASH = _hasher.hash("timing-attack-mitigation-dummy")

def dummy_verify(plain: str) -> None:
    try:
        _hasher.verify(_DUMMY_HASH, plain)
    except Exception:
        pass
```
```python
# auth_service.py
if user is None:
    dummy_verify(password)
    return None
```

### CR-06: nginx `add_header` directives silently dropped in the rate-limited / proxy locations

**File:** `deploy/nginx/nginx.conf:71-78` vs `83-132`
**Issue:** The security headers (`X-Content-Type-Options`, `X-Frame-Options`, CSP, HSTS, Referrer-Policy) are declared at the `server` level. nginx's `add_header` is **not additive**: as soon as *any* `add_header` appears in a more specific block, the inherited set is discarded for that block. While no location here adds its own header today, the `try_files`/static `location ~* \.(js|css...)$` block at lines 128-131 *does* add `Cache-Control`, which wipes all five security headers for every hashed static asset response. More importantly, this fragile pattern means the headers are easy to lose on any future per-location header. Combined with CR-01 it is currently moot, but it is a real defect once nginx starts.
**Fix:** Either repeat the security headers in each location that adds its own header, or move them so inheritance holds. Most robust: keep them at `server` level AND re-add inside the static asset block:
```nginx
location ~* \.(js|css|woff2?|png|svg|ico)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Content-Security-Policy "frame-ancestors 'none'" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
```

## Warnings

### WR-01: `JWT_SECRET` (and other secrets) have no minimum-length / strength validation

**File:** `backend/app/core/config.py:47`
**Issue:** `JWT_SECRET: str` accepts any non-empty value. A short or low-entropy secret makes HS256 tokens brute-forceable, defeating T-03-02. The CI placeholder is 32 chars but nothing enforces this in production. The module docstring claims secrets "fail fast at startup", but only *presence* is checked, not adequacy.
**Fix:** Add a validator requiring a reasonable minimum length:
```python
@field_validator("JWT_SECRET")
@classmethod
def _jwt_secret_strong(cls, v: str) -> str:
    if len(v) < 32:
        raise ValueError("JWT_SECRET must be at least 32 characters")
    return v
```

### WR-02: Refresh cookie `path=/api/v1/auth` does not match the route nginx/app actually serve

**File:** `backend/app/services/auth_service.py:87`, `91-103`; `backend/app/api/auth.py:33,62-63`
**Issue:** The router is mounted at `prefix="/api/v1"` + `APIRouter(prefix="/auth")`, so endpoints live under `/api/v1/auth/login` and `/api/v1/auth/refresh` — the cookie path `/api/v1/auth` matches those. However, `set_refresh_cookie` and `clear_refresh_cookie` must use **identical** attributes for the browser to clear the cookie; `delete_cookie` here re-passes `httponly`/`secure`/`samesite` which `Response.delete_cookie` ignores in some Starlette versions, and the `max_age` mismatch can leave the cookie un-cleared. Verify the path constant stays in sync if the prefix ever changes (it is duplicated as a literal, not derived).
**Fix:** Derive the cookie path from a single constant shared with the router prefix, and ensure `delete_cookie` uses the same `path`, `samesite`, and `secure` as `set_cookie`. Add an integration test that logs in then confirms `delete_cookie` produces a `Max-Age=0` Set-Cookie for the same path.

### WR-03: `eslint` step neutered with `|| true` — lint failures cannot fail CI

**File:** `.github/workflows/ci.yml:106,135`
**Issue:** Both frontend lint steps run `npx eslint . --ext .ts,.tsx --max-warnings 0 || true`. The `|| true` swallows any non-zero exit, so eslint can never break the build despite `--max-warnings 0` implying strictness. This is a quality gate that does nothing.
**Fix:** Remove `|| true` so lint failures fail the job:
```yaml
- name: Lint (eslint)
  run: npx eslint . --ext .ts,.tsx --max-warnings 0
```

### WR-04: CI env var name mismatch — `S3_ENDPOINT_URL` vs `S3_ENDPOINT`

**File:** `.github/workflows/ci.yml:79` vs `backend/app/core/config.py:50`
**Issue:** CI sets `S3_ENDPOINT_URL` but `Settings` reads `S3_ENDPOINT`. With `case_sensitive=True` and `extra="ignore"`, the CI value is ignored and `S3_ENDPOINT` falls back to its `""` default. Harmless today (default exists), but it signals the env contract and CI have drifted; the same class of typo on a *required* secret would fail the whole suite confusingly.
**Fix:** Rename the CI var to `S3_ENDPOINT` to match the contract in `deploy/.env.example` / `config.py`.

### WR-05: `decode_token` does not constrain accepted algorithms beyond a single-element list / no `aud`/`iss`

**File:** `backend/app/core/security.py:149-154`
**Issue:** `jwt.decode(..., algorithms=[_ALGORITHM])` correctly pins HS256 (good — prevents `alg=none` and RS/HS confusion). However there is no audience or issuer validation, and `iat` is set but never verified. For a single-service deployment this is acceptable, but the refresh and access tokens are otherwise indistinguishable except by the custom `type` claim; relying solely on a non-standard claim is fragile. Consider also rejecting tokens whose `sub` is missing at decode time rather than only at the caller.
**Fix:** Add `audience`/`issuer` claims at encode time and validate them at decode, or at minimum document the single-audience assumption. Low risk but worth hardening before more services share the secret.

### WR-06: Seed dev-default passwords shipped in tracked source

**File:** `backend/app/seed/data/staff_users.json:6,13,20,27`; `backend/app/seed/seed_staff.py:79`
**Issue:** The four `password_dev_default` values (`admin_dev_password_change_in_prod`, etc.) are committed and used verbatim when the `SEED_*` env vars are unset. If a deployment runs the seed without setting the env vars (easy to forget), it provisions an **admin** account with a publicly known password. The code comments warn against this but nothing enforces it.
**Fix:** Refuse to use a dev default outside development:
```python
plain_password = os.environ.get(password_env)
if plain_password is None:
    if os.environ.get("APP_ENV", "development").lower() == "production":
        raise RuntimeError(f"{password_env} must be set in production")
    plain_password = dev_default
```

### WR-07: `get_schema_version` references `engine` in `finally` before it may be bound

**File:** `backend/app/entrypoint.py:135-154`
**Issue:** If `create_engine(...)` (line 136) raises, the `except Exception` block returns `None`, then the `finally` block (line 151) executes `engine.dispose()` where `engine` was never assigned, raising `NameError` — which is itself swallowed by the inner `try/except`, but the control flow is muddled and the real error is masked. The function returning `None` on a transient DB error is also reported by `/health` as "not migrated" (schema_version null), which is misleading.
**Fix:** Initialize `engine = None` before the `try`, and guard `if engine is not None: engine.dispose()`. Consider distinguishing "table absent" (null) from "connection error" in the health payload.

### WR-08: Dockerfile installs full `.[dev]` (test/lint deps) into the production image

**File:** `deploy/Dockerfile.backend:25`
**Issue:** `pip install --no-cache-dir ".[dev]"` pulls pytest, mypy, ruff, etc. into the runtime image, enlarging the attack surface and image size for a production container. The image is also the runtime for `worker`/`beat`.
**Fix:** Install only runtime deps in the production stage: `pip install --no-cache-dir .` (use a separate build/test stage or target for dev tooling).

## Info

### IN-01: Auto-generated API docs enabled unconditionally

**File:** `backend/app/main.py:46-47`
**Issue:** `docs_url="/docs"` and `redoc_url="/redoc"` are always on; the comment says "Disable in production (enable via env var if needed)" but the code does the opposite. Exposes the full schema publicly.
**Fix:** Gate on env: `docs_url="/docs" if settings.APP_ENV != "production" else None`.

### IN-02: `LoginRequest.email` is `str`, lookup is case-sensitive

**File:** `backend/app/schemas/auth.py:24`; `backend/app/services/auth_service.py:51-53`
**Issue:** Email is matched with `StaffUser.email == email` (case- and whitespace-sensitive). A user who types `Admin@Polymer.uz` cannot log in even though the account exists. Seed stores lowercase only by convention.
**Fix:** Normalize on input (`email.strip().lower()`) in the schema/validator and store normalized, so login is robust.

### IN-03: `dashboard/login` submit handler is a dead stub

**File:** `dashboard/app/login/page.tsx:10-13`
**Issue:** `handleSubmit` only calls `preventDefault()` with a `TODO`; the form does nothing. Acceptable for a Phase-1 scaffold but the page presents a functional-looking login that silently no-ops — easy to mistake for a bug later.
**Fix:** None required for the scaffold; track the TODO in the Phase-4 plan.

### IN-04: `_REFRESH_COOKIE` computed at import time via function call

**File:** `backend/app/api/auth.py:35`
**Issue:** `_REFRESH_COOKIE = get_refresh_cookie_name()` is evaluated at module import and baked into the `Cookie(alias=...)` default. Fine today, but it couples the route definition to import-time state; if the cookie name ever becomes config-driven it will silently use the import-time value.
**Fix:** Low priority — acceptable as-is; note the coupling.

---

_Reviewed: 2026-06-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
