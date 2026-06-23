---
phase: 06-acceptance-handover
plan: 05
subsystem: testing
tags: [docker-compose, smoke-test, bash, makefile, source-isolation, v_live_feed, source_failure]

# Dependency graph
requires:
  - phase: 06-04
    provides: production deploy/docker-compose.yml (api/worker/beat/userbot/postgres/redis/minio/nginx/dashboard)
  - phase: 02-collector-pipeline
    provides: run_source_fetch_isolated + source_failure deduped alert (per-source failure isolation)
  - phase: 01-foundation
    provides: /api/v1/health, v_live_feed view, migrate+seed entrypoint chain
provides:
  - "tests/smoke/test_smoke_full_stack.sh — full-stack production-compose smoke (D-02) on synthetic data"
  - "make smoke target wrapping the smoke script"
  - "Live end-to-end validation of the deployment-guide stand-up sequence (referenceable by 06-06)"
  - "Fixed production-deploy defect: CBU FX source seed kind 'fx' → schema-valid 'external_index'"
affects: [06-06, deployment-guide, 06-ACCEPTANCE]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Runtime-generated placeholder .env (gitignored, removed on exit) — no real secrets committed for a full-stack smoke"
    - "Health-gated wait via `compose exec api curl` (TLS-only prod nginx bypassed for key-free local probe)"
    - "trap cleanup EXIT → `compose down -v` so mid-run failures still tear down"

key-files:
  created:
    - tests/smoke/test_smoke_full_stack.sh
    - Makefile
  modified:
    - backend/app/seed/data/sources_seed.json

key-decisions:
  - "Probe /api/v1/health via `compose exec api curl http://localhost:8000/...` instead of through nginx — prod nginx is TLS-only on 443 with example.com cert paths a key-free local smoke cannot satisfy; exec hits the exact internal path nginx proxies to."
  - "Bring up api/worker/beat + postgres/redis/minio but skip nginx (TLS certs) and dashboard (heavy Next.js build) — these are unrelated to the request→feed + source-isolation assertions; documented so 06-06 references the same minimal stand-up."
  - "Generate the placeholder .env at runtime at repo-root ./.env (the path the prod compose's `env_file: ../.env` and `--env-file` both resolve), reuse a pre-existing operator .env without deleting it, and delete a generated one on exit — zero secrets in git history."
  - "Reclassify CBU FX source seed kind as 'external_index' (a data-only fix), not add an 'fx' enum value — the locked source_kind schema stays untouched and no migration is needed."

patterns-established:
  - "Full-stack smoke structure: placeholder-env → compose up → health-gate → synthetic request→feed → forced fake-source failure 3x asserting isolation + one source_failure alert → trap teardown"

requirements-completed: []

# Metrics
duration: ~35 min
completed: 2026-06-22
---

# Phase 6 Plan 5: Full-stack Smoke (D-02) Summary

**A runnable `make smoke` that stands up the production docker-compose stack on synthetic data and proves /health, a synthetic request reaching v_live_feed, and per-source failure isolation with exactly one deduped source_failure alert — and which surfaced + fixed a real clean-deploy defect (CBU FX seed enum).**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-06-22
- **Tasks:** 2
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- **`tests/smoke/test_smoke_full_stack.sh`** — stands up the production `deploy/docker-compose.yml` (api/worker/beat + postgres/redis/minio) on a runtime-generated placeholder `.env` (no real secrets), health-gates on `/api/v1/health == ok`, inserts a synthetic purchase request and asserts it is queryable in `v_live_feed`, then forces a fake source's `fetch()` to raise 3× via `run_source_fetch_isolated` alongside a healthy sibling and asserts (a) the sibling still recorded success (isolation) and (b) exactly one `alerts` row with `kind='source_failure'` (the 3-strike deduped alert). Trap teardown (`compose down -v`) runs on any exit.
- **`make smoke`** target added at repo root wrapping the script.
- **Ran LIVE end-to-end** — full image build + stack bring-up + all four assertions + teardown; printed `[smoke] PASSED` with exit 0 on two consecutive runs, no leftover containers/volumes.
- **Fixed a production-deploy defect** the smoke surfaced: the CBU FX source seed declared `kind='fx'`, which is not a member of the locked `source_kind` enum — on a clean `docker compose up` this aborted the api's `migrate && seed && uvicorn` chain so the stack never became healthy. Reclassified as the schema-valid `external_index`.

## Task Commits

1. **Task 1: Author the smoke script + Makefile target** — `6882b5b` (feat)
2. **Task 2: Execute the smoke end-to-end (surfaced + fixed the CBU seed defect)** — `bc179b6` (fix)

## What the smoke does (step by step)

| Step | Action | Assertion |
|------|--------|-----------|
| 1 | Write placeholder `./.env` (fake-but-functional secrets; gitignored, removed on exit) and `docker compose -f deploy/docker-compose.yml up -d --build postgres redis minio api worker beat` | stack builds + starts |
| 2 | Poll `compose exec api curl http://localhost:8000/api/v1/health` (timeout 300s, configurable via `SMOKE_HEALTH_TIMEOUT`) | response contains `"status":"ok"` (proves migrate+seed ran) |
| 3 | `compose exec api python` inserts a synthetic `clients` row + `requests` row (FK to a seeded product), then `SELECT COUNT(*) FROM v_live_feed WHERE origin='request' AND id=:rid` | count == 1 (request reaches the feed view) |
| 4 | `compose exec api python` runs `run_source_fetch_isolated` once on a healthy sibling source then 3× on a fake source whose `_run_fetch_for_source` raises | sibling has `last_success_at` set & `consecutive_failures=0` (isolation); fake has `consecutive_failures>=3`; exactly one `alerts` row with `kind='source_failure'` and `dedupe_key LIKE 'source_failure:<fake_id>:%'` |
| 5 | `trap cleanup EXIT` → `compose down -v --remove-orphans` + remove generated `.env` | no orphaned containers/volumes/state |

The script prints `[smoke] PASSED` only if all four assertions pass.

### How source-failure isolation is asserted

The smoke mirrors `backend/tests/test_source_failure_alert.py::TestFailureIsolationDB` against the **live** stack rather than a unit DB: it inserts two real `sources` rows (a healthy sibling + a fake), patches `app.tasks.ingest._run_fetch_for_source` to raise for the fake on each of 3 isolated runs, and after each run commits. `run_source_fetch_isolated` never re-raises (per-source isolation, T-02-17), so the sibling's success is recorded independently and the fake's `consecutive_failures` reaches 3, at which point `record_fetch_failure` → `raise_source_failure_alert` inserts a single alert deduped on `source_failure:{source_id}:{UTC-date}` via `ON CONFLICT (dedupe_key) DO NOTHING`. The smoke then asserts exactly one such alert exists for the fake source and that the sibling stayed healthy. Live run logs confirmed the path: three `uzex_fetch.source_error` log lines followed by one `source_health.alert_raised`.

## What ran LIVE vs. by inspection

**Ran LIVE (real Docker engine, full build + bring-up):**
- Image build of the backend (`backend/Dockerfile`, ~uv/pip install) and start of postgres, redis, minio, api, worker, beat.
- migrate + seed (`app.entrypoint` + `seed_reference` + `seed_staff` + `seed_sources`) inside the api container.
- `/api/v1/health` returning `{"status":"ok",...}`.
- Synthetic `requests` insert → confirmed `id=1` visible in `v_live_feed`.
- Forced fake-source failure 3× → sibling isolation + exactly one `source_failure` alert.
- `compose down -v` teardown; verified no `pismoke` containers remain. Ran green twice (idempotent), exit 0 both times.

**By inspection (not driven live by this smoke):**
- **nginx** ingress (TLS 80/443) — not started; prod nginx requires real Let's Encrypt certs for a domain. Validated by `docker compose config` (interpolates cleanly) and reasoned: the smoke hits the api at the exact internal path nginx proxies to.
- **dashboard** (Next.js standalone) and **userbot** — not started; both are out of scope for the backend request→feed + isolation assertions and would add heavy build / require TG creds. Their service definitions were validated via `docker compose config --services` (all 9 services resolve with the placeholder env).

## Files Created/Modified

- `tests/smoke/test_smoke_full_stack.sh` (created) — full-stack production-compose smoke (D-02).
- `Makefile` (created) — repo-root `make smoke` target (+ `make help`).
- `backend/app/seed/data/sources_seed.json` (modified) — CBU FX source `kind` `fx` → `external_index` (clean-deploy fix).

## Decisions Made

See `key-decisions` frontmatter. Summary: probe health via `compose exec` (prod nginx is TLS-only); bring up the backend subset relevant to the assertions and validate nginx/dashboard/userbot by `compose config`; generate the placeholder `.env` at runtime at the prod-expected path and never delete a pre-existing operator `.env`; fix the CBU seed as data-only (`external_index`) without touching the locked schema.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CBU FX source seed used a non-existent `source_kind` enum value (`fx`)**
- **Found during:** Task 2 (executing the smoke end-to-end)
- **Issue:** `backend/app/seed/data/sources_seed.json` declared the CBU FX rates source with `kind: "fx"`, but the locked `source_kind` enum (migration `0001`, never altered) contains only `exchange, telegram_channel, website, webapp, manual, external_index, rss`. On a clean production `docker compose up`, the api `command` runs `seed_sources` before `uvicorn`; the enum violation (`invalid input value for enum source_kind: "fx"`) aborted the `&&` chain so the api never served and `/health` never returned ok. This is a genuine clean-deploy defect, not a smoke-script issue.
- **Fix:** Reclassified the CBU external currency-index feed as the schema-valid `external_index` (data-only change). No migration needed; the locked schema is untouched. Verified no code or test keys off `kind='fx'`.
- **Files modified:** `backend/app/seed/data/sources_seed.json`
- **Verification:** Smoke re-ran green end-to-end (`[smoke] PASSED`, exit 0, twice); backend suite `761 passed, 0 failed`; ruff + scoped mypy (app/services, app/schemas per dev-spec §7) green.
- **Committed in:** `bc179b6` (Task 2 commit)

**2. [Rule 3 - Blocking / documented adaptation] Health probe and stack subset adapted to the smoke environment**
- **Found during:** Task 1 (authoring) → confirmed in Task 2
- **Issue:** The plan says "poll `/api/v1/health` through nginx", but the production nginx is TLS-only on 443 with `example.com` Let's Encrypt cert paths that a key-free local smoke cannot satisfy; nginx/dashboard/userbot also need certs/build/creds not present in a synthetic smoke.
- **Fix:** Probe `/api/v1/health` via `compose exec api curl http://localhost:8000/api/v1/health` (the exact internal path nginx proxies to) and bring up the backend subset (api/worker/beat + postgres/redis/minio) that the request→feed + isolation assertions exercise. nginx/dashboard/userbot are validated statically via `docker compose config`. No assertions were weakened.
- **Files modified:** `tests/smoke/test_smoke_full_stack.sh` (design)
- **Verification:** `docker compose config --services` resolves all 9 services with the placeholder env; smoke passes end-to-end.
- **Committed in:** `6882b5b` (Task 1 commit)

---

**Total deviations:** 2 (1 Rule-1 bug auto-fixed, 1 Rule-3 documented environment adaptation)
**Impact on plan:** The Rule-1 fix was necessary for a clean production deploy to come up at all — the smoke did exactly its job (surfaced a real defect before handover). The Rule-3 adaptation preserves every assertion the plan requires while staying key-free; no scope creep.

## Issues Encountered

None beyond the documented deviations. The over-broad `mypy app` invocation initially showed 58 pre-existing errors in `parsing/` and `app/tasks/parse_telegram.py` (files untouched by this plan); the canonical gate (mypy scoped to `app/services` + `app/schemas` per `.github/workflows/ci.yml` / dev-spec §7) is green, as is ruff and the 761-test suite.

## User Setup Required

None — the smoke uses a runtime-generated placeholder `.env` only. For a real production deploy, operators supply a real `.env` per the deployment guide (06-06); the customer-gated live drills (real BOT_TOKEN/HTTPS/live sources) remain deploy-day rows in `06-ACCEPTANCE.md`.

## Next Phase Readiness

- `make smoke` is the canonical stand-up + prove-it-works sequence for the deployment guide (06-06) to reference verbatim.
- The CBU seed fix means a clean `docker compose up` now reaches healthy state with full seed; this unblocks any deploy-guide first-run walkthrough.
- Note for 06-06: the prod nginx ships with `example.com` placeholder cert paths; the deployment guide must cover certbot issuance before nginx will start.

## Self-Check: PASSED

- Files verified on disk: `tests/smoke/test_smoke_full_stack.sh`, `Makefile`, `backend/app/seed/data/sources_seed.json`, `.planning/phases/06-acceptance-handover/06-05-SUMMARY.md` — all FOUND.
- Commits verified: `6882b5b` (Task 1, feat), `bc179b6` (Task 2, fix) — both FOUND.
- Plan verification re-run: `bash -n` clean; script targets `deploy/docker-compose.yml`; asserts `/health` ok, request→`v_live_feed`, forced fake-source isolation + one `source_failure` alert; trap teardown; `make smoke` ran green end-to-end (exit 0, `[smoke] PASSED`, stack torn down) twice.
- Gates: backend suite `761 passed, 0 failed`; ruff clean; scoped mypy (app/services + app/schemas) clean.

---
*Phase: 06-acceptance-handover*
*Completed: 2026-06-22*
