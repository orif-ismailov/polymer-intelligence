---
phase: 01-walking-skeleton
reviewed: 2026-06-14T00:00:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - .github/workflows/ci.yml
  - backend/Dockerfile
  - backend/app/core/config.py
  - backend/app/core/security.py
  - backend/app/main.py
  - backend/app/services/auth_service.py
  - backend/pyproject.toml
  - backend/tests/test_auth_login.py
  - backend/tests/test_config.py
  - dashboard/eslint.config.mjs
  - dashboard/next-env.d.ts
  - dashboard/package.json
  - dashboard/tsconfig.json
  - deploy/docker-compose.dev.yml
  - deploy/nginx/nginx.conf
  - webapp/package.json
findings:
  critical: 1
  warning: 7
  info: 5
  total: 13
status: issues_found
---

# Phase 01: Code Review Report (Gap-Closure Re-Review)

**Reviewed:** 2026-06-14T00:00:00Z
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

This re-review covers the Phase 01 gap-closure changeset that was written to fix the
prior review's findings (CR-01..CR-06, WR-01, WR-04): docker/nginx stand-up (01-05), CI
greening (01-06), security hardening (01-07: CORS non-wildcard, argon2 `dummy_verify`
timing mitigation, JWT secret length validator), and the Next.js/Vite dependency bump.

**Prior-finding resolution (verified):**
- **CR-01 (nginx missing `events {}`)** — FIXED. `deploy/nginx/nginx.conf:11-13` now has
  the mandatory `events {}` block.
- **CR-02 (compose Dockerfile path)** — FIXED. `backend/Dockerfile` now exists and
  compose builds `context: ../backend, dockerfile: Dockerfile`.
- **CR-03 (invalid build backend)** — FIXED. `pyproject.toml:3` now uses
  `setuptools.build_meta`.
- **CR-04 (CORS wildcard + credentials)** — FIXED. `main.py:59-65` drives
  `allow_origins` from `settings.CORS_ALLOWED_ORIGINS` (non-wildcard default, comma-split
  validator).
- **CR-05 (no-op dummy hash)** — FIXED. `security.py:42` precomputes a real argon2 hash;
  `dummy_verify` performs full KDF work; wired in `auth_service.py:61` and covered by
  tests.
- **CR-06 (nginx header drop on static assets)** — FIXED. Security headers re-declared in
  the static-asset block (`nginx.conf:142-146`).
- **WR-01 (JWT secret strength)** — FIXED. `config.py:73-84` rejects secrets < 32 chars.
- **WR-04 (S3 env name drift)** — **NOT FIXED, and now BLOCKER-class.** CI still exports
  `S3_ENDPOINT_URL` while config reads `S3_ENDPOINT` (see CR-01 below). The prior review
  rated this a WARNING because the field had a harmless default; on closer analysis the
  silent-misconfiguration risk for a required storage endpoint warrants escalation.

**New issues introduced by the gap-closure work:** the CI pipeline gained a dashboard
`tsc` step that depends on a never-generated `.next/types` directory (WR-01 below), a
`build-images` job that builds a Dockerfile the new `backend/Dockerfile` header itself
labels "legacy" (WR-02), and the docs-disabled comment in `main.py` is still contradicted
by the code (WR-06). The security-hardening logic itself is sound.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: S3 endpoint env-var name mismatch silently misconfigures storage

**File:** `backend/app/core/config.py:62`, `.github/workflows/ci.yml:79`, `deploy/.env.example:36`
**Issue:** `Settings` declares the S3 endpoint field as `S3_ENDPOINT` (default `""`), and
`deploy/.env.example` sets `S3_ENDPOINT=http://minio:9000`. But the CI workflow exports
`S3_ENDPOINT_URL: http://localhost:9000` (ci.yml line 79). Because `model_config` uses
`extra="ignore"` with `case_sensitive=True`, the `S3_ENDPOINT_URL` variable is silently
discarded and `S3_ENDPOINT` falls back to its empty-string default. There is no validator
requiring it to be non-empty. Any code that later builds an S3/MinIO client from
`settings.S3_ENDPOINT` will receive `""` and either fail at runtime or connect to an
unintended default endpoint — a silent storage-misconfiguration (potential data-loss /
data-leak) that does not fail fast at startup. The name is inconsistent across three
files, guaranteeing the bug recurs. This was flagged as WR-04 in the prior review and
left unfixed; escalating to BLOCKER because the failure mode is silent and affects a
required production dependency.
**Fix:** Pick one canonical name and enforce non-empty. Align CI to the contract:
```yaml
# .github/workflows/ci.yml
S3_ENDPOINT: http://localhost:9000
```
and make the field required so a missing/misnamed value fails fast:
```python
# config.py — remove the "" default
S3_ENDPOINT: str
```

## Warnings

### WR-01: Dashboard `tsc --noEmit` in CI depends on a `.next/types` directory that is never generated

**File:** `dashboard/next-env.d.ts:3`, `dashboard/tsconfig.json:36`, `.github/workflows/ci.yml:108-109`
**Issue:** `next-env.d.ts` does `import "./.next/types/routes.d.ts";` and `tsconfig.json`
`include` lists `.next/types/**/*.ts` and `.next/dev/types/**/*.ts`. These directories are
produced by `next build` / `next dev` / `next typegen`, not by `npm ci`. The dashboard CI
job runs `npm ci` then `npx tsc --noEmit` with no intervening build, so
`./.next/types/routes.d.ts` will not exist and `tsc` will raise
`TS2307: Cannot find module './.next/types/routes.d.ts'`. The dashboard type-check job
will fail on a clean checkout, contradicting the "CI green" goal of plan 01-06. If it
currently passes, it is only because a stale/committed `.next` directory is present, which
is itself a problem (generated artifacts in VCS).
**Fix:** Generate Next types before type-checking:
```yaml
- name: Generate Next types
  run: npx next build --no-lint   # or: npx next typegen
- name: Type-check (tsc --noEmit)
  run: npx tsc --noEmit
```

### WR-02: `build-images` CI job builds a Dockerfile the repo itself labels "legacy"

**File:** `.github/workflows/ci.yml:154`, `backend/Dockerfile:4-6`
**Issue:** The `build-images` job runs
`docker build -f deploy/Dockerfile.backend -t pi-backend:ci backend/`. The new active
`backend/Dockerfile` header (lines 4–6) explicitly calls `deploy/Dockerfile.backend` a
"legacy file" that is "behaviourally equivalent" and must be "kept in sync." CI therefore
validates a *different* image than the one `docker-compose.dev.yml` actually builds
(`context: ../backend, dockerfile: Dockerfile`). Any security or dependency change made to
`backend/Dockerfile` will not be reflected in the CI-built image, defeating the purpose of
the build gate. (The dashboard step's `deploy/Dockerfile.dashboard` was out of scope and
not verified.)
**Fix:** Build the same file compose uses and delete the duplicate:
```yaml
- name: Build backend image
  run: docker build -f backend/Dockerfile -t pi-backend:ci backend/
```

### WR-03: Inactive-account timing oracle: `is_active` checked after `verify_password`

**File:** `backend/app/services/auth_service.py:64-70`
**Issue:** The new `dummy_verify` correctly closes the user-not-found timing gap. But the
`is_active` check (line 67) runs *after* `verify_password` (line 64). For a deactivated
account, a request with the *correct* password takes verify-success time while a request
with a *wrong* password takes verify-fail time. An attacker who already holds (or guesses)
a valid credential pair for a since-deactivated account can distinguish "valid password,
account disabled" from "wrong password" by timing — a narrow residual enumeration oracle
on disabled accounts. This is much smaller than the primary user-not-found case (now
fixed), hence WARNING.
**Fix:** Document this as an accepted residual, or equalize work so both inactive-account
sub-paths consume identical KDF time regardless of password correctness.

### WR-04: `decode_token` re-wraps `JWTError`, losing the subclass and interpolating an attacker-controlled claim

**File:** `backend/app/core/security.py:189-197`
**Issue:** `decode_token` catches `JWTError` and re-raises
`JWTError(f"Token validation failed: {exc}")`, discarding the original subclass so callers
cannot distinguish expired (`ExpiredSignatureError`) from tampered tokens — both collapse
to a generic 401 (acceptable for auth, but lossy). More notably, the token-type mismatch
path raises `JWTError(f"... got '{token_type}'")` where `token_type` is the
attacker-supplied `type` claim, interpolated into an exception message. If any caller ever
logs this exception message, attacker-controlled content lands in logs (minor log-injection
surface) and the embedded `{exc}` may leak token-parsing internals.
**Fix:** Re-raise without wrapping and do not interpolate untrusted claim values:
```python
except JWTError:
    raise  # preserve subclass; do not embed token internals
...
if token_type != expected_type:
    raise JWTError("Token type mismatch")
```

### WR-05: `restart: unless-stopped` + optional `.env` crash-loops the app services on misconfiguration

**File:** `deploy/docker-compose.dev.yml:57-71, 81-99, 102-120`, `backend/app/core/config.py:117`
**Issue:** `config.py` instantiates `settings = Settings()` at import, and required
secrets (`JWT_SECRET`, `BOT_TOKEN`, `ANTHROPIC_API_KEY`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`,
`TG_API_ID`, `TG_API_HASH`, `WEBHOOK_SECRET`) have no defaults — import raises
`ValidationError` when unset. The compose `env_file: ../.env` is `required: false` and the
`environment:` blocks supply only `DATABASE_URL`/`REDIS_URL`. With
`restart: unless-stopped`, a missing/incomplete `.env` causes api/worker/beat to fail-fast
on every boot and restart indefinitely, producing a tight crash loop whose only signal is
repeated tracebacks. The (good) fail-fast design is undermined by the restart policy.
**Fix:** Make `../.env` `required: true` for the dev stack so compose errors clearly, or
use `restart: on-failure:3` on the app services so the loop terminates and surfaces the
config error.

### WR-06: `docs_url`/`redoc_url` enabled unconditionally despite the comment claiming production is disabled

**File:** `backend/app/main.py:46-49`
**Issue:** The comment says "Disable auto-generated docs in production (enable via env var
if needed)" but the code hard-codes `docs_url="/docs"` and `redoc_url="/redoc"`, so the
OpenAPI schema and interactive docs are always exposed, including in production. The schema
reveals the full auth surface (`/api/v1/auth/login`, role-guarded demo routes) to
unauthenticated clients. The comment/code mismatch will mislead maintainers into believing
docs are gated. (Flagged as IN-01 in the prior review and still unaddressed.)
**Fix:**
```python
import os
_prod = os.environ.get("APP_ENV", "development").lower() == "production"
application = FastAPI(
    ...,
    docs_url=None if _prod else "/docs",
    redoc_url=None if _prod else "/redoc",
    openapi_url=None if _prod else "/openapi.json",
)
```

### WR-07: nginx security-header inheritance is a latent regression footgun

**File:** `deploy/nginx/nginx.conf:79-86, 117-148`
**Issue:** The CR-06 fix correctly re-declares all five security headers inside the
static-asset block. But the structural risk remains: nginx `add_header` is non-additive, so
any future `add_header` placed in `/webapp/`, `/dashboard/`, `/api/`, or
`/api/v1/auth/login` will silently drop the inherited server-level security headers for
that location. The code comment documents this only at the asset block, so the next
maintainer adding (say) a cache header to the `/webapp/` index response will silently strip
HSTS/CSP/X-Frame-Options from the SPA entry document. Today it is correct; it is one edit
away from a security regression.
**Fix:** Centralize the five headers in `include snippets/security-headers.conf;` and
reference it from every `location` that needs them, so inheritance cannot be silently lost.

## Info

### IN-01: `monkeypatch` fixture parameter requested but unused

**File:** `backend/tests/test_auth_login.py:46, 85`
**Issue:** `auth_client(monkeypatch)` and `inactive_auth_client(monkeypatch)` request the
`monkeypatch` fixture but never use it (`no_user_auth_client` correctly omits it). Dead
fixture dependency.
**Fix:** Remove the unused `monkeypatch` parameter from both fixtures.

### IN-02: User-enumeration assertion is logically too weak

**File:** `backend/tests/test_auth_login.py:210-212`
**Issue:** `assert "email" not in detail or "password" not in detail` passes as long as the
detail omits *either* word. A message like "wrong email" (contains "email", not "password")
would still pass while leaking which field was wrong. The intent is "neither word appears."
**Fix:** `assert "email" not in detail and "password" not in detail`.

### IN-03: Backend Dockerfile installs full `.[dev]` tooling into the runtime image

**File:** `backend/Dockerfile:29`
**Issue:** `pip install --no-cache-dir ".[dev]"` pulls pytest, ruff, mypy, etc. into the
production runtime image (the compose target for api/worker/beat), enlarging image size and
attack surface. Carried over from prior WR-08, now in the new `backend/Dockerfile`.
**Fix:** Install only runtime deps in the final image (`pip install .`); use a multi-stage
build for dev tooling.

### IN-04: `S3_ENDPOINT`/`SENTRY_DSN` use empty-string sentinels with no validation

**File:** `backend/app/core/config.py:62, 71`
**Issue:** Both fields use `""` as an "unset" sentinel. For `SENTRY_DSN` (empty = disabled)
this is fine; for `S3_ENDPOINT` empty is indistinguishable from misconfigured (see CR-01).
**Fix:** Make `S3_ENDPOINT` required or add a validator rejecting empty when S3 is in use.

### IN-05: CI placeholder secrets duplicated across workflow and tests; 32-char length is a load-bearing magic constant

**File:** `.github/workflows/ci.yml:70-79`, `backend/tests/test_config.py:25`
**Issue:** Placeholder secrets are duplicated between `ci.yml` and the test modules. The
`JWT_SECRET` placeholder's length is load-bearing — the new validator rejects < 32 chars —
so shortening the literal would break CI non-obviously.
**Fix:** Share a single `.env.ci` between the workflow and tests, or annotate the
length-dependency where the literals are defined.

---

_Reviewed: 2026-06-14T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
