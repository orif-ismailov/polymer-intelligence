---
phase: 01-walking-skeleton
plan: "06"
subsystem: infra
tags: [ci, github-actions, eslint, pyproject, pip, pep517, setuptools]

# Dependency graph
requires:
  - phase: 01-04
    provides: "CI workflow scaffold with backend/dashboard/webapp jobs; eslint 9 flat config for dashboard (commit 799b5bf)"
  - phase: 01-01
    provides: "backend/pyproject.toml with project deps and dev extras"
provides:
  - "Valid PEP 517 build backend (setuptools.build_meta) in backend/pyproject.toml"
  - "Enforced eslint --max-warnings 0 gates for both dashboard (eslint 9) and webapp (eslint 8) — no || true suppression"
  - "Synced webapp/package-lock.json so npm ci succeeds in CI"
affects: [all future phases using CI, backend pip install, deploy/Dockerfile.backend]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "eslint 9 flat config (dashboard): npx eslint --max-warnings 0 with no --ext flag"
    - "eslint 8 (webapp): npx eslint . --ext .ts,.tsx --max-warnings 0"

key-files:
  created: []
  modified:
    - backend/pyproject.toml
    - .github/workflows/ci.yml
    - webapp/package-lock.json

key-decisions:
  - "Dashboard eslint CI command uses no --ext flag (eslint 9 flat config rejects it; file matching comes from eslint.config.mjs)"
  - "Webapp eslint CI command retains --ext .ts,.tsx (eslint 8 still requires it)"
  - "webapp/package-lock.json synced (@emnapi packages) as a Rule 3 auto-fix so npm ci succeeds in CI"

patterns-established:
  - "eslint gates must not be suppressed with || true in CI"

requirements-completed: ["REQ-nfr-observability", "REQ-nfr-security"]

# Metrics
duration: 3min
completed: 2026-06-14
---

# Phase 01 Plan 06: CI Gap-Closure (PEP 517 + eslint gates) Summary

**Valid setuptools.build_meta backend and enforced eslint --max-warnings 0 gates (no || true) with both scaffolds confirmed lint-clean**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-14T08:43:24Z
- **Completed:** 2026-06-14T08:46:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Fixed `backend/pyproject.toml` to use `setuptools.build_meta` (valid PEP 517 backend), unblocking `pip install -e ".[dev]"` in CI and `pip install ".[dev]"` in the Dockerfile
- Removed `|| true` from both eslint CI steps so lint failures now break the build (closes T-CI-01); dashboard uses eslint 9 flat config form (`npx eslint --max-warnings 0`), webapp retains eslint 8 form (`npx eslint . --ext .ts,.tsx --max-warnings 0`)
- Both scaffolds confirmed lint-clean locally (exit 0, zero warnings) under the now-enforced gates
- Synced `webapp/package-lock.json` so `npm ci` succeeds in the webapp CI job

## Task Commits

1. **Task 1: Fix the PEP 517 build-backend in pyproject.toml** - `9eab0d5` (fix)
2. **Task 2: Remove || true from both eslint steps and confirm scaffolds lint clean** - `96d8980` (fix)

## Files Created/Modified

- `backend/pyproject.toml` — Line 3: `build-backend = "setuptools.build_meta"` (was `setuptools.backends.legacy:build`)
- `.github/workflows/ci.yml` — Dashboard eslint step: `npx eslint --max-warnings 0`; webapp eslint step: `npx eslint . --ext .ts,.tsx --max-warnings 0` (both `|| true` removed)
- `webapp/package-lock.json` — Synced @emnapi package versions so `npm ci` succeeds

## Decisions Made

- Dashboard eslint CI command drops `--ext` because eslint 9 flat config rejects that flag; file matching is driven by `dashboard/eslint.config.mjs`. Using the original `--ext .ts,.tsx` form from the scaffold would error in CI.
- Webapp eslint CI command retains `--ext .ts,.tsx` because webapp is on eslint 8 which still requires explicit extension targeting.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Synced webapp/package-lock.json**
- **Found during:** Task 2 (confirming scaffolds lint clean locally)
- **Issue:** `npm ci` failed with lock file mismatch (`@emnapi/wasi-threads@1.2.1` vs `@emnapi/wasi-threads@1.2.2`, missing entries). The same failure would block the webapp CI job that runs `npm ci` before eslint.
- **Fix:** Ran `npm install` in the webapp directory to update the lockfile; then ran `npx eslint . --ext .ts,.tsx --max-warnings 0` to confirm lint-clean (exit 0).
- **Files modified:** `webapp/package-lock.json`
- **Verification:** `npm ci` now succeeds; eslint exits 0 with zero warnings
- **Committed in:** `96d8980` (Task 2 commit, alongside ci.yml changes)

---

**Total deviations:** 1 auto-fixed (Rule 3 - blocking)
**Impact on plan:** Auto-fix necessary for CI correctness. No scope creep.

## Issues Encountered

None beyond the lockfile sync handled as a Rule 3 deviation above.

## Known Stubs

None — this plan makes no UI or data changes; no stub patterns introduced.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Both threats in the register are now mitigated:
- T-CI-01 (eslint gate neutered by `|| true`): mitigated — `|| true` removed from both eslint steps
- T-CI-02 (backend pip install blocked by invalid PEP 517 backend): mitigated — `setuptools.build_meta` is now the declared backend

## Next Phase Readiness

- SC#5 is closed: pyproject.toml uses a valid PEP 517 backend and both eslint gates enforce `--max-warnings 0` with no suppression
- CI can now pass green end-to-end (ruff, mypy, eslint+tsc, tests, image build) — the quality backbone is trustworthy for all later phases
- No blockers for Phase 01 plan 07

---
*Phase: 01-walking-skeleton*
*Completed: 2026-06-14*
