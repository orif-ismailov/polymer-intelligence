---
phase: 01-walking-skeleton
plan: "07"
subsystem: auth-security
tags: [security, cors, argon2, jwt, timing-attack, gap-closure]
dependency_graph:
  requires: ["01-01", "01-03"]
  provides: ["CORS_ALLOWED_ORIGINS setting", "JWT_SECRET validator", "dummy_verify", "settings-driven CORS"]
  affects: ["backend/app/core/config.py", "backend/app/core/security.py", "backend/app/services/auth_service.py", "backend/app/main.py"]
tech_stack:
  added: []
  patterns: ["TDD RED/GREEN per task", "pydantic-settings Union[list[str], str] for env comma-list parsing", "argon2 precomputed dummy hash for timing equalization"]
key_files:
  created: []
  modified:
    - backend/app/core/config.py
    - backend/app/core/security.py
    - backend/app/services/auth_service.py
    - backend/app/main.py
    - backend/tests/test_config.py
    - backend/tests/test_auth_login.py
decisions:
  - "Union[list[str], str] field type for CORS_ALLOWED_ORIGINS so pydantic-settings passes raw comma-separated env string to field_validator (list[str] alone triggers JSON decode failure)"
  - "_DUMMY_HASH computed at import time (not per-request) so argon2 KDF overhead is paid once; dummy_verify pays it every login attempt for unknown users"
  - "allow_methods and allow_headers explicit lists (not wildcard) when allow_credentials=True — required by CORS spec and Starlette behavior"
metrics:
  duration: "9 minutes"
  completed_date: "2026-06-14"
  tasks_completed: 2
  files_modified: 6
---

# Phase 01 Plan 07: Security Hardening Gap Closure Summary

**One-liner:** Closed three auth security defects — settings-driven CORS (CR-04), real argon2 dummy_verify timing equalization (CR-05/T-03-01), and JWT_SECRET minimum-length validator (WR-01/T-03-02).

## What Was Built

Closed the three defects blocking REQ-nfr-security from full verification:

**CR-04 / T-03-05 — CORS misconfiguration:**
- Added `CORS_ALLOWED_ORIGINS: Union[list[str], str]` to `Settings` with default `["http://localhost:3000"]`
- Field validator `_parse_cors_origins(mode="before")` splits comma-separated env strings into a list
- `main.py` now imports `settings` and uses `allow_origins=settings.CORS_ALLOWED_ORIGINS`
- `allow_methods` and `allow_headers` are explicit lists — wildcard eliminated when `allow_credentials=True`

**CR-05 / T-03-01 — Timing-attack mitigation was a no-op:**
- Added `_DUMMY_HASH = _hasher.hash("timing-attack-mitigation-dummy")` computed once at import
- Added `dummy_verify(plain: str) -> None` that calls `_hasher.verify(_DUMMY_HASH, plain)` and swallows `VerifyMismatchError`
- `auth_service.py` user-not-found branch now calls `dummy_verify(password)` — real KDF work performed
- Eliminated the malformed hash string `"$argon2id$...dummysalt$dummyhash"` which caused `InvalidHashError` immediately (zero KDF work)

**WR-01 / T-03-02 — JWT_SECRET had no minimum-length enforcement:**
- Added `_jwt_secret_min_length` field validator on `JWT_SECRET` — raises `ValueError("JWT_SECRET must be at least 32 characters")` when secret is < 32 chars
- CI placeholder `ci-jwt-secret-placeholder-32chars!!` (38 chars) satisfies the constraint

## Tests

Task 1 (4 new tests in `test_config.py`):
- `TestJwtSecretValidator::test_short_jwt_secret_raises_validation_error` — 31-char secret fails
- `TestJwtSecretValidator::test_jwt_secret_exactly_32_chars_succeeds` — 32-char secret passes
- `TestJwtSecretValidator::test_jwt_secret_longer_than_32_chars_succeeds` — CI placeholder passes
- `TestCorsAllowedOriginsValidator::test_cors_allowed_origins_default_is_non_wildcard` — default != ["*"]
- `TestCorsAllowedOriginsValidator::test_cors_allowed_origins_parses_comma_separated_env` — comma parsing

Task 2 (5 new tests in `test_auth_login.py`):
- `test_dummy_verify_does_not_raise` — dummy_verify with any input doesn't raise
- `test_dummy_verify_does_not_raise_invalid_hash_error` — confirms real hash (not malformed)
- `test_unknown_user_path_calls_dummy_verify` — unknown-user branch wires dummy_verify
- `test_valid_login_still_works_regression` — valid credentials still succeed
- `test_wrong_password_returns_401_regression` — wrong password still returns 401

All 41 tests pass (`tests/test_config.py` + `tests/test_auth_login.py`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] pydantic-settings JSON-decodes list[str] env fields before field_validator runs**

- **Found during:** Task 1 GREEN phase
- **Issue:** When `CORS_ALLOWED_ORIGINS: list[str]` is declared, pydantic-settings v2's `EnvSettingsSource.prepare_field_value` calls `json.loads()` on the raw env string before the `field_validator(mode="before")` gets a chance to process it. A comma-separated string like `"http://localhost:3000,https://dashboard.example.com"` is not valid JSON, causing `SettingsError`.
- **Fix:** Changed field declaration to `Union[list[str], str]`. This causes pydantic-settings' `_field_is_complex` to return `allow_parse_failure=True` (Union types allow JSON parse failure), so the raw string is passed through to the `field_validator(mode="before")` which splits it. The validator always returns `list[str]`, so the field at runtime is always a list.
- **Files modified:** `backend/app/core/config.py`
- **Commit:** 971738f

None of the other code changes deviated from the plan.

## TDD Gate Compliance

Task 1:
- RED commit: 22a2ac8 (`test(01-07): add failing tests for JWT_SECRET length validator and CORS_ALLOWED_ORIGINS setting`)
- GREEN commit: 971738f (`feat(01-07): add CORS_ALLOWED_ORIGINS setting and JWT_SECRET length validator in config.py`)

Task 2:
- RED commit: 1250358 (`test(01-07): add failing tests for dummy_verify, user-not-found timing, and regression`)
- GREEN commit: 1cdd866 (`feat(01-07): real argon2 dummy_verify (CR-05/T-03-01), settings-driven CORS (CR-04/T-03-05)`)

Both RED gates confirmed failing before GREEN implementation; both GREEN gates confirmed all tests passing.

## Commits

| Hash | Message |
|------|---------|
| 22a2ac8 | test(01-07): add failing tests for JWT_SECRET length validator and CORS_ALLOWED_ORIGINS setting |
| 971738f | feat(01-07): add CORS_ALLOWED_ORIGINS setting and JWT_SECRET length validator in config.py |
| 1250358 | test(01-07): add failing tests for dummy_verify, user-not-found timing, and regression |
| 1cdd866 | feat(01-07): real argon2 dummy_verify (CR-05/T-03-01), settings-driven CORS (CR-04/T-03-05) |

## Known Stubs

None. All security controls are fully wired.

## Threat Flags

No new threat surface introduced. All modifications close existing T-03-01, T-03-02, T-03-05 threats as planned.

## Self-Check: PASSED

All 7 files verified present on disk. All 4 task commits verified in git log.
