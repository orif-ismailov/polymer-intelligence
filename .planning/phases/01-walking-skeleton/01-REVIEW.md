---
phase: 01-walking-skeleton
reviewed: 2026-06-15T00:00:00Z
depth: standard
files_reviewed: 35
files_reviewed_list:
  - .github/workflows/ci.yml
  - backend/alembic/env.py
  - backend/alembic/versions/0001_initial_schema.py
  - backend/app/api/auth.py
  - backend/app/api/deps.py
  - backend/app/api/health.py
  - backend/app/core/config.py
  - backend/app/core/db.py
  - backend/app/core/security.py
  - backend/app/core/time.py
  - backend/app/entrypoint.py
  - backend/app/main.py
  - backend/app/models/__init__.py
  - backend/app/models/alerts.py
  - backend/app/models/enums.py
  - backend/app/models/reports.py
  - backend/app/models/requests.py
  - backend/app/models/signals.py
  - backend/app/models/sources.py
  - backend/app/models/staff.py
  - backend/app/seed/seed_reference.py
  - backend/app/services/audit_service.py
  - backend/app/services/auth_service.py
  - backend/pyproject.toml
  - backend/tests/conftest.py
  - backend/tests/test_config.py
  - backend/tests/test_jwt.py
  - backend/tests/test_rbac.py
  - backend/tests/test_audit.py
  - backend/tests/test_time.py
  - backend/tests/test_migration.py
  - backend/tests/test_seed.py
  - backend/tests/test_auth_login.py
  - backend/tests/test_password_hash.py
  - deploy/docker-compose.dev.yml
  - deploy/nginx/nginx.dev.conf
findings:
  critical: 0
  warning: 8
  info: 6
  total: 14
status: issues_found
---

# Phase 01: Code Review Report (Lint-Sweep Re-Review)

**Reviewed:** 2026-06-15T00:00:00Z
**Depth:** standard
**Files Reviewed:** 35
**Status:** issues_found

## Summary

This re-review covers the Phase 01 gap-closure changeset (plans 01-08 dev nginx boot, 01-09 S3 env rename, 01-10 ruff/mypy green sweep) and supersedes the prior 01-REVIEW (2026-06-14). It was conducted adversarially with emphasis on lint-sweep regressions (StrEnum conversion, import reordering, exception-suppression refactors), the auth/security stack, the new HTTP-only dev nginx config, and the config validators.

**Prior BLOCKER (CR-01, S3 env-name mismatch) is now RESOLVED.** The CI workflow exports `S3_ENDPOINT: http://localhost:9000` (`ci.yml:79`), matching `Settings.S3_ENDPOINT`, and a new regression guard (`test_config.py::TestCiEnvContract`) parses `ci.yml` to assert the name never drifts back to `S3_ENDPOINT_URL`. No new BLOCKER-class defect was found in this changeset.

**Lint-sweep regression check — clean.** The `str, enum.Enum` → `enum.StrEnum` conversion is safe here: every enum member has `name == value`, so SQLAlchemy's native-enum binding produces identical DB strings, and all auth/serialization code uses explicit `.value`. Verified empirically that `StrEnum` member access, `.value`, and the inherited `str.index` instance method all behave correctly (`PricePointKind.index` shadowing is class-level only). Import reordering introduced no side-effect changes (`app.models.__init__` still imports every model module before `Base.metadata` is read by alembic). The `try/except: pass` → `contextlib.suppress` refactors are behavior-preserving except for the widened swallow noted in WR-08. The suspicious-looking pins (`mypy==2.1.0`, `ruff==0.15.17`) were verified to exist on PyPI and will not break `pip install`.

**Residual auth/robustness findings carried forward** from the prior review still apply to files in this scope: the inactive-account timing residual (WR-03), the `decode_token` claim-interpolation/wrapping issue (WR-04), the dev-stack crash-loop-on-misconfig (WR-05), and the unconditionally-exposed docs (WR-06). These are WARNINGs, not blockers. The newly added `nginx.dev.conf` introduces its own header-inheritance footgun (WR-01) and a wrong-directive `Content-Type` (WR-02).

## Structural Findings (fallow)

No structural pre-pass was provided for this review.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: nginx `location = /` silently drops all server-level security headers

**File:** `deploy/nginx/nginx.dev.conf:58-70`
**Issue:** The four security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Referrer-Policy`) are declared at the `server` level (lines 58-61). nginx `add_header` inheritance is "replace, not merge": a `location` that declares any `add_header` of its own discards all inherited ones. Because `location = /` declares `add_header Content-Type ...` (line 69), the four security headers are NOT emitted on `GET /`. The `/api/` and `/api/v1/auth/login` blocks declare no `add_header`, so they correctly inherit them today — but this is one edit away from silently stripping the headers from the API surface (defeats T-04-01/T-04-03).
**Fix:** Remove the root `add_header` (see WR-02) so the root location inherits the server headers, or re-declare the four headers inside any location that adds its own:
```nginx
location = / {
    default_type text/plain;
    return 200 "dev stack up\n";
}
```

### WR-02: `add_header Content-Type` is the wrong directive for setting the response content type

**File:** `deploy/nginx/nginx.dev.conf:67-70`
**Issue:** Content type is set via `add_header Content-Type text/plain;` instead of `default_type`/`types`. `add_header` is for arbitrary response headers, not the entity `Content-Type`; depending on nginx version this can produce an unexpected or duplicated `Content-Type`. It also follows `return 200` in source order, which is misleading.
**Fix:** Use `default_type text/plain;` and drop the `add_header` (also resolves WR-01 for this block).

### WR-03: Inactive-account timing oracle — `is_active` checked after `verify_password`

**File:** `backend/app/services/auth_service.py:62-68`
**Issue:** `dummy_verify` correctly closes the user-not-found timing gap, but the `is_active` check (line 65) runs after `verify_password` (line 62). For a deactivated account, a correct-password request takes verify-success time while a wrong-password request takes verify-fail time, letting an attacker who holds a valid credential pair for a since-disabled account distinguish "valid password, disabled" from "wrong password" by timing. Much narrower than the now-fixed user-not-found case, hence WARNING.
**Fix:** Document as an accepted residual, or equalize KDF work across both inactive sub-paths.

### WR-04: `decode_token` re-wraps `JWTError` and interpolates an attacker-controlled claim into the exception message

**File:** `backend/app/core/security.py:183-197`
**Issue:** `decode_token` catches `JWTError` and re-raises `JWTError(f"Token validation failed: {exc}")`, discarding the original subclass (callers can no longer distinguish expired from tampered) and embedding parser internals in the message. The type-mismatch path raises `JWTError(f"... got '{token_type}'")` where `token_type` is the attacker-supplied `type` claim. If any caller logs this exception, attacker-controlled content reaches logs (minor log-injection surface).
**Fix:** Re-raise without wrapping and do not interpolate untrusted claim values:
```python
except JWTError:
    raise
...
if token_type != expected_type:
    raise JWTError("Token type mismatch")
```

### WR-05: `restart: unless-stopped` + optional `.env` crash-loops the app services on misconfiguration

**File:** `deploy/docker-compose.dev.yml:53-78, 81-99, 102-120`; `backend/app/core/config.py:120`
**Issue:** `config.py` instantiates `settings = Settings()` at import, and the required secrets (`JWT_SECRET`, `BOT_TOKEN`, `ANTHROPIC_API_KEY`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `TG_API_ID`, `TG_API_HASH`, `WEBHOOK_SECRET`) have no defaults, so import raises `ValidationError` when unset. The compose `env_file: ../.env` is `required: false` and the `environment:` blocks supply only `DATABASE_URL`/`REDIS_URL`. With `restart: unless-stopped`, a missing/incomplete `.env` makes api/worker/beat fail-fast on every boot and restart indefinitely — a tight crash loop whose only signal is repeated tracebacks.
**Fix:** Make `../.env` `required: true` for the dev stack, or use `restart: on-failure:3` on the app services so the loop terminates and surfaces the config error.

### WR-06: `docs_url`/`redoc_url` enabled unconditionally despite the comment claiming production is disabled

**File:** `backend/app/main.py:46-49`
**Issue:** The comment says "Disable auto-generated docs in production (enable via env var if needed)" but the code hard-codes `docs_url="/docs"` and `redoc_url="/redoc"`, so the OpenAPI schema and interactive docs are always exposed, including in production. The schema reveals the full auth surface to unauthenticated clients, and the comment/code mismatch misleads maintainers.
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

### WR-07: `CORS_ALLOWED_ORIGINS` validator fails closed-and-silent on unexpected input

**File:** `backend/app/core/config.py:84-104`
**Issue:** `_parse_cors_origins` returns `[]` for any input that is neither `str` nor `list`. The comment calls this "unreachable," but a misconfigured env value that pydantic-settings decodes into a dict (or other type) falls through to `return []`, which becomes `CORSMiddleware(allow_origins=[])`. An empty allow-list disables all credentialed cross-origin requests with no error and no log — a silent, hard-to-diagnose breakage of the dashboard/webapp. Failing closed-and-silent is worse than failing loud.
**Fix:** Raise instead of returning empty:
```python
if isinstance(v, list):
    return [str(item) for item in v]
raise ValueError(f"CORS_ALLOWED_ORIGINS must be a list or comma-separated string, got {type(v).__name__}")
```

### WR-08: `get_schema_version` `finally` block can reference an unbound `engine` and the suppression masks it

**File:** `backend/app/entrypoint.py:136-154`
**Issue:** If `create_engine(...)` raises (e.g. malformed `DATABASE_URL`), `engine` is never bound; the `finally` then references `engine` and raises `UnboundLocalError`, which is swallowed by `with contextlib.suppress(Exception)`. The function still returns `None`, so the symptom is benign here, but the lint sweep's `try/except: pass` → `contextlib.suppress(Exception)` conversion widened the swallow to include `UnboundLocalError`/`NameError`, hiding both the engine-construction error and any genuine `dispose()` failure.
**Fix:** Initialize `engine = None`, guard the dispose, and narrow the suppression:
```python
engine = None
try:
    engine = create_engine(database_url, poolclass=NullPool)
    ...
finally:
    if engine is not None:
        with contextlib.suppress(SQLAlchemyError):
            engine.dispose()
```

## Info

### IN-01: `PricePointKind.index` member shadows `str.index` at the class level (now masked by `type: ignore`)

**File:** `backend/app/models/enums.py:96`
**Issue:** Under `StrEnum` (a `str` subclass), the member named `index` shadows the inherited `str.index` method on the class object, so `PricePointKind.index` resolves to the member. Verified that `member.index(...)` (instance calls) still resolve to `str.index`, so there is no runtime breakage — the DB value `"index"` is load-bearing and the chosen workaround is `# type: ignore[assignment]`, which suppresses the diagnostic. Acceptable; flagged so the type-ignore is not generalized.
**Fix:** None required (DB contract requires `"index"`); the inline comment is adequate.

### IN-02: StrEnum changes `str(member)` / f-string representation semantics

**File:** `backend/app/models/enums.py:16-155`
**Issue:** With the previous `class X(str, enum.Enum)`, `str(X.member)` / `f"{X.member}"` produced `"X.member"`; with `enum.StrEnum` they now produce the bare value (`"member"`). No current code relies on the old form (auth uses `.value`, `v_live_feed` casts with `::text` in raw SQL), so this is safe today. Flagged so future logging/string-keying code is written with the new semantics in mind.
**Fix:** None required.

### IN-03: User-enumeration assertion in the login test is logically too weak

**File:** `backend/tests/test_auth_login.py:207-209`
**Issue:** `assert "email" not in detail or "password" not in detail` passes as long as the detail omits either word, so a message like "wrong email" would still pass while leaking which field was wrong. The intent is "neither word appears."
**Fix:** `assert "email" not in detail and "password" not in detail`.

### IN-04: Unused `monkeypatch` fixture parameter in auth-login test fixtures

**File:** `backend/tests/test_auth_login.py:46, 84`
**Issue:** `auth_client(monkeypatch)` and `inactive_auth_client(monkeypatch)` request the `monkeypatch` fixture but never use it (`no_user_auth_client` correctly omits it). Dead fixture dependency.
**Fix:** Remove the unused `monkeypatch` parameter from both fixtures.

### IN-05: Demo route handlers declare a bare `-> dict` return type

**File:** `backend/app/main.py:80, 90`
**Issue:** `admin_whoami` and `analyst_whoami` are annotated `-> dict` (implicitly `dict[Any, Any]`). They live outside the `app/services` + `app/schemas` mypy-strict scope, so CI does not flag them, but this is inconsistent with the typed style used elsewhere.
**Fix:** Annotate as `-> dict[str, object]` or define a small Pydantic response model.

### IN-06: `_check_redis` constructs a fresh Redis client on every `/health` call

**File:** `backend/app/api/health.py:63-73`
**Issue:** Each probe builds a new `redis.from_url(...)` client and never closes it — connection churn under frequent monitoring polls (performance is out of v1 scope, flagged as a latent robustness item).
**Fix:** Reuse a lazily-created module-level client and `.close()` after ping, or accept the cost at low poll frequency.

---

_Reviewed: 2026-06-15T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
