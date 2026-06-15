---
phase: 01-walking-skeleton
plan: "09"
subsystem: infra
tags: [ci, pydantic-settings, s3, minio, env-contract, regression-test]

# Dependency graph
requires:
  - phase: 01-walking-skeleton
    plan: "07"
    provides: "Settings with case_sensitive=True and S3_ENDPOINT field"
provides:
  - "CI workflow exports S3_ENDPOINT matching the pydantic Settings field name"
  - "Regression test locking CI env name to Settings.S3_ENDPOINT field (silent drift prevention)"
affects: [Phase 2 S3/MinIO client construction, any CI job that sets S3 endpoint]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CI env key names must exactly match pydantic Settings field names (case_sensitive=True)"
    - "Text-based parsing for CI contract tests when PyYAML is not a dev dependency"

key-files:
  created:
    - "backend/tests/test_config.py (TestCiEnvContract class — 3 new tests)"
  modified:
    - ".github/workflows/ci.yml (S3_ENDPOINT_URL → S3_ENDPOINT on line 79)"
    - "backend/tests/test_config.py (TestCiEnvContract class appended)"

key-decisions:
  - "Keep S3_ENDPOINT: str = '' default in config.py (Phase 1 has no S3 feature flag; making it required breaks the 100-passing test suite — CR-01 'make it required' deferred)"
  - "Use text-based regex parsing in regression test instead of PyYAML (PyYAML not in backend [dev] extras)"

patterns-established:
  - "CI ↔ Settings env-name contract test: parse CI YAML via text search, assert key present + URL non-empty + field in model_fields"

requirements-completed: ["REQ-nfr-security", "REQ-nfr-observability"]

# Metrics
duration: 5min
completed: 2026-06-15
---

# Phase 01 Plan 09: S3 CI Env Name Contract (Gap 3 / CR-01) Summary

**CI workflow env key `S3_ENDPOINT_URL` renamed to `S3_ENDPOINT` to match the case-sensitive pydantic Settings field, plus a regression test that locks the CI env name to the Settings field so the silent drift cannot recur.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-15T09:00:00Z
- **Completed:** 2026-06-15T09:05:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Fixed REVIEW CR-01 (major): renamed `S3_ENDPOINT_URL` → `S3_ENDPOINT` in the backend job's pytest env block in `.github/workflows/ci.yml`; `settings.S3_ENDPOINT` now receives `http://localhost:9000` in CI instead of silently falling back to `""` due to case-sensitive env name mismatch
- Added `TestCiEnvContract` class (3 tests) to `backend/tests/test_config.py` that parses ci.yml text and asserts the env contract — any future rename of either the CI key or the Settings field without updating the other fails CI
- Full backend test suite went from 100 to 103 passed (17 skipped), 0 failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Rename ci.yml S3_ENDPOINT_URL → S3_ENDPOINT** - `6f1a406` (fix)
2. **Task 2: Add regression test for CI S3 env name contract** - `4b047f1` (test)

## Files Created/Modified

- `.github/workflows/ci.yml` — Line 79: `S3_ENDPOINT_URL: http://localhost:9000` → `S3_ENDPOINT: http://localhost:9000`
- `backend/tests/test_config.py` — `TestCiEnvContract` class added with 3 regression tests

## Decisions Made

- **Keep `S3_ENDPOINT: str = ""` default in config.py**: CR-01 suggested making it required, but that would break the existing 100-passing test suite (fixtures don't set S3_ENDPOINT). Fail-fast required-field validation deferred to the phase that constructs the S3/MinIO client (Phase 2/3).
- **Text-based parsing for regression test**: PyYAML is not in backend `[dev]` extras, so the test uses `pathlib.Path.read_text()` + `re.search()` to check env key presence. Equivalent correctness without adding a new dependency.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] PyYAML not installed — switched to text-based CI parsing**
- **Found during:** Task 2 (regression test)
- **Issue:** `import yaml` in the test raised `ModuleNotFoundError: No module named 'yaml'`; PyYAML is not in `backend/pyproject.toml [dev]` extras
- **Fix:** Replaced yaml.safe_load-based env dict extraction with `Path.read_text()` + `re.search()` — functionally equivalent (checks `S3_ENDPOINT:` present and `S3_ENDPOINT_URL` absent by text scan); plan explicitly anticipated this fallback ("if PyYAML is not in [dev], fall back to a line-based assertion")
- **Files modified:** `backend/tests/test_config.py`
- **Verification:** `103 passed, 17 skipped` — all 3 new tests pass
- **Committed in:** `4b047f1` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking import error)
**Impact on plan:** Fix is within spec (plan pre-authorized text-based fallback). No scope creep.

## Issues Encountered

None beyond the PyYAML fallback above.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes. Changes are confined to CI env config and a regression test.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- UAT Gap 3 / REVIEW CR-01 is closed; all three files now agree on `S3_ENDPOINT`: `config.py`, `deploy/.env.example`, and `.github/workflows/ci.yml`
- Phase 2 can construct the S3/MinIO client from `settings.S3_ENDPOINT` and the value will be correctly populated in CI
- The regression test `TestCiEnvContract` will catch any future env-name drift before it ships

---
*Phase: 01-walking-skeleton*
*Completed: 2026-06-15*
