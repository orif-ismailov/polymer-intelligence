---
phase: 06-acceptance-handover
plan: 02
subsystem: infra
tags: [postgres, pg_dump, pg_restore, backup, restore, disaster-recovery, docker, alembic, bash]

# Dependency graph
requires:
  - phase: 02-ingest-core-uzex
    provides: "pg_backup.sh (pg_dump custom format + retention) and docs/runbook-backup-restore.md"
  - phase: 02-ingest-core-uzex
    provides: "app.entrypoint advisory-locked alembic upgrade head"
provides:
  - "tests/restore/test_restore_local.sh — executable D-04 restore drill (dump → fresh PG16 → restore → migrate → verify → time-gate ≤2h)"
  - "Validated/refined docs/runbook-backup-restore.md (§9 handover deliverable) with the gaps a real restore surfaced fixed"
  - "Recorded measured restore wall-clock (4s on dev dataset) under the TZ §6.1.5 ≤2h budget"
affects: [06-ACCEPTANCE, HANDOVER, deployment-guide, deploy-day-restore-rerun]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Disposable PG16 restore target: distinct container name + host port + tmpfs data dir so the dev postgres_data volume can never be touched (T-06-04)"
    - "Dump handled via mktemp + umask 077 + EXIT/INT/TERM trap cleanup, no world-readable dump left behind (T-06-03)"
    - "pg_restore --jobs requires a seekable file: docker cp the dump in, restore from the in-container path (parallel restore cannot read stdin)"
    - "Migration step snapshots the running api container env into a --env-file and mounts current backend source so alembic resolves the dump's recorded revision even with a stale baked image"

key-files:
  created:
    - "tests/restore/test_restore_local.sh"
  modified:
    - "docs/runbook-backup-restore.md"

key-decisions:
  - "DEC-06-02-disposable-fresh-container: a fresh tmpfs postgres:16-alpine container is the 'clean server' for proving the restore procedure; the dev volume is a read-only source and is never dropped"
  - "DEC-06-02-pin-superuser-pi_user: runbook drop/create uses -U pi_user -d postgres because no separate 'postgres' role exists in this deployment"
  - "DEC-06-02-restore-from-file-not-pipe: pg_restore --jobs=4 reads a copied-in file path, never stdin"
  - "DEC-06-02-migrate-with-current-source: Step-4 alembic run mounts current backend source so it has migrations >= the dump's alembic_version (0004), independent of image age"

patterns-established:
  - "Restore drill pattern: time-boxed dump→fresh-container→restore→migrate→verify(rows/ENUMs/view) with a hard ≤2h budget assertion"
  - "Runbook-as-tested: every gap a real execution surfaces is fixed in the runbook in the same plan (the runbook is the §9 deliverable the customer follows)"

requirements-completed: []

# Metrics
duration: ~25 min
completed: 2026-06-22
---

# Phase 6 Plan 02: Restore test (D-04 / TZ §6.1.5) Summary

**Executable restore drill that pg_dumps the live DB, restores it onto a fresh disposable PostgreSQL 16 container via the runbook, verifies schema/rows/14-ENUMs/`v_live_feed`, and asserts the wall-clock under the ≤2h budget — run live in 4 s, with the three procedural gaps it surfaced fixed in the handover runbook.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-06-22
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- Authored `tests/restore/test_restore_local.sh`: records a start epoch, `pg_dump --format=custom --compress=6` of the running dev DB, captures source row counts, spins a **fresh disposable `postgres:16-alpine`** container (distinct name/port `55432`/tmpfs — never the dev volume), restores via the runbook §3 commands (`DROP/CREATE DATABASE` + `pg_restore --jobs=4`), applies `alembic upgrade head` via `app.entrypoint`, verifies per-table row equality + the 14 locked ENUMs + `v_live_feed`, prints elapsed and asserts `< 7200s`, then tears everything down.
- **Executed the drill live and end-to-end** against the running dev stack: dump (71 KB) → fresh PG16 → restore → migrate to revision `0004` → verify (signals 45, raw_items 0, sources 3 all match source; 14 ENUMs present; `v_live_feed` 51 rows) → **elapsed 4 s, PASS** (well under the 2h budget). Disposable container + dump cleaned up on exit; dev stack untouched.
- Fixed the three real procedural gaps the live run surfaced in `docs/runbook-backup-restore.md` (superuser role, file-vs-pipe restore, migration/image staleness) and recorded the validated measured wall-clock in §5.

## Task Commits

1. **Task 1: Author tests/restore/test_restore_local.sh** — `3661535` (test)
2. **Task 2: Execute the drill and fix runbook gaps** — `b05400e` (fix)

## Files Created/Modified
- `tests/restore/test_restore_local.sh` — NEW executable restore drill (dump → fresh PG16 → restore via runbook → verify rows/ENUMs/view → assert ≤2h budget). Bash 3.2-portable; security-hardened dump handling (mktemp/umask 077/trap); disposable tmpfs restore target.
- `docs/runbook-backup-restore.md` — MODIFIED: §2/§3 Step 2 corrected to `-U pi_user -d postgres`; §3 Step 3 documents the `--jobs` file-not-pipe requirement + `docker cp` pattern + `--no-owner --no-privileges`; §3 Step 4 adds the migration-vs-dump-revision (image staleness) caveat; §5 records the validated 2026-06-22 drill (4 s, PASS) and references the drill script.

## Verification — live vs by inspection

| Check | How verified |
|-------|--------------|
| Dump → fresh PG16 → `pg_restore` restores cleanly | **LIVE** — Docker running, dev stack healthy, fresh `postgres:16-alpine` container restored from a real `pg_dump` |
| Row-count equality (signals/raw_items/sources) | **LIVE** — restored counts (45/0/3) asserted equal to source |
| 14 locked ENUMs present | **LIVE** — `SELECT count(*) ... typcategory='E'` returned 14 in the restored DB |
| `v_live_feed` view restored & queryable | **LIVE** — `SELECT COUNT(*) FROM v_live_feed` returned 51 in the restored DB |
| `alembic upgrade head` reaches `0004` | **LIVE** — entrypoint applied migrations, "Current revision: 0004" |
| Wall-clock under ≤2h budget | **LIVE** — measured 4 s vs 7200 s budget, assertion passed |
| Disposable container never touches dev volume | **LIVE** — tmpfs/distinct-port container; post-run check showed no leftover containers/dumps and dev DB intact (45 signals) |
| `bash -n` + all Task-1 acceptance greps | **LIVE** — syntax clean, all required tokens present |
| Backend suite not regressed | **LIVE** — `python -m pytest -q` → 752 passed, 65 skipped, 0 failed |
| Production VPS hardware timing | **NOT done here (by design)** — recorded as a deploy-day row for `06-ACCEPTANCE.md` (06-06); a fresh container proves the *procedure*, the VPS rerun confirms hardware timing |

## Decisions Made
- A fresh tmpfs `postgres:16-alpine` container is the "clean server" for proving the procedure; the dev volume is a read-only source and is never dropped (sidesteps the runbook's destructive DROP-on-dev steps while still exercising the exact restore commands).
- Restore reads a copied-in file (not stdin) because `pg_restore --jobs` cannot do parallel restore from a pipe.
- The Step-4 migration mounts current backend source so it has the migrations matching the dump's `alembic_version`, independent of the baked image's age.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Bash 3.2 portability — removed `declare -A`**
- **Found during:** Task 2 (first drill execution)
- **Issue:** The script used `declare -A SRC_COUNTS` (associative array). macOS dev default is Bash 3.2, which lacks associative arrays → `declare: -A: invalid option`, aborting the drill.
- **Fix:** Replaced the associative array with plain shell vars (`SRC_SIGNALS_COUNT`, `SRC_RAWITEMS_COUNT`, `SRC_SOURCES_COUNT`) and a `verify_count()` helper. Same behavior, portable to Bash 3.2 and Linux Bash.
- **Files modified:** tests/restore/test_restore_local.sh
- **Verification:** `bash -n` clean; full drill ran to completion afterward.
- **Committed in:** `b05400e`

**2. [Rule 1 - Bug] pg_restore --jobs cannot read from stdin**
- **Found during:** Task 2 (drill execution)
- **Issue:** `pg_restore ... --jobs=4 < dump` errored "parallel restore from standard input is not supported" — parallel restore needs a seekable file.
- **Fix:** `docker cp` the dump into the disposable container and run `pg_restore` against that in-container path (matches runbook §3, which passes a file path). Same gap fixed in the runbook with a `docker cp` example + an explicit caveat callout.
- **Files modified:** tests/restore/test_restore_local.sh, docs/runbook-backup-restore.md
- **Verification:** Restore step succeeded on the re-run.
- **Committed in:** `b05400e`

**3. [Rule 2 - Missing Critical] Migration step lacked app secrets / current migrations**
- **Found during:** Task 2 (drill execution)
- **Issue:** A bare `docker run deploy-api python -m app.entrypoint` (a) failed constructing pydantic `Settings()` because the standalone container had no `.env` (REDIS_URL, ANTHROPIC_API_KEY, JWT_SECRET, … all required), and then (b) failed with "Can't locate revision identified by '0004'" because the baked `deploy-api` image is stale (only has migrations `0001`/`0002`) while the dump records `0004`.
- **Fix:** Snapshot the running api container's env into a temp `--env-file` (umask 077, removed on exit; keeps secret values off the command line) overriding only `DATABASE_URL`, and bind-mount the current backend source over `/app` so alembic has all migrations through `0004`. Mirrors how dev compose mounts the source. Documented both pitfalls in runbook §3 Step 4.
- **Files modified:** tests/restore/test_restore_local.sh, docs/runbook-backup-restore.md
- **Verification:** "Migrations applied. Current revision: 0004"; full drill PASS.
- **Committed in:** `b05400e`

**4. [Rule 1 - Bug] Runbook §2/§3 Step 2 referenced a non-existent `postgres` role**
- **Found during:** Task 2 (environment inspection + drill)
- **Issue:** Runbook used `psql -U postgres`, but the deployment's bootstrap superuser is `pi_user` (the `POSTGRES_USER`); there is no `postgres` role (`role "postgres" does not exist`).
- **Fix:** Runbook now uses `-U pi_user -d postgres` for the DROP/CREATE, with a note that you must connect to the maintenance `postgres` DB to drop the active database. The drill already used `pi_user` consistently.
- **Files modified:** docs/runbook-backup-restore.md
- **Verification:** Drill DROP/CREATE succeeded against the disposable server as `pi_user`.
- **Committed in:** `b05400e`

---

**Total deviations:** 4 auto-fixed (2 bug [Rule 1], 1 missing-critical [Rule 2], 1 blocking [Rule 3]).
**Impact on plan:** All four are exactly the procedural gaps this plan exists to surface and close — they harden both the drill and the §9 handover runbook. No scope creep; the plan's two files are the only files touched.

## Issues Encountered
- Host has no `pg_dump`/`pg_restore`/`psql` binaries (uv-managed backend env, no local PG client tools). Handled by running all pg tooling inside containers (the `postgres:16-alpine` image ships the client tools) rather than on the host — the drill is fully self-contained on Docker alone.
- The "production VPS hardware timing" rerun is intentionally NOT executed here; a fresh container proves the *procedure* (Phase-6 SC#2 / TZ §6.1.5 at the procedure level), and the hardware-timing rerun is a deploy-day row in `06-ACCEPTANCE.md`.

## Known Stubs
None — the drill exercises real `pg_dump`/`pg_restore`/`alembic` against a real fresh PG16 container with seeded synthetic data; no placeholder/mock data paths.

## User Setup Required
None — no external service configuration required. The drill uses Docker + the documented dev `devpassword` only; no production data or real secrets.

## Next Phase Readiness
- TZ §6.1.5 restore procedure is **proven end-to-end at the procedure level** on a clean PG16 server within the ≤2h budget, with the wall-clock recorded (4 s) and the runbook validated/refined — satisfies Phase-6 SC#2 at the procedure level.
- `docs/runbook-backup-restore.md` is ready to be cited as a §9 deliverable in `HANDOVER.md` and referenced from `06-ACCEPTANCE.md`.
- Deploy-day follow-up: rerun the drill (or the runbook steps) on the real customer VPS to confirm hardware timing; record as a deploy-day acceptance row.

## Self-Check: PASSED

- `tests/restore/test_restore_local.sh` exists on disk ✓
- `docs/runbook-backup-restore.md` exists on disk ✓
- `.planning/phases/06-acceptance-handover/06-02-SUMMARY.md` exists on disk ✓
- Commit `3661535` (Task 1, test) present ✓
- Commit `b05400e` (Task 2, fix) present ✓
- Drill re-run exit 0; backend suite 752 passed / 0 failed ✓

---
*Phase: 06-acceptance-handover*
*Completed: 2026-06-22*
