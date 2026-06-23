---
phase: 06-acceptance-handover
plan: 04
subsystem: infra
tags: [docker-compose, nginx, tls, deploy, userbot, dashboard, secrets]

# Dependency graph
requires:
  - phase: 02-ingest-core-uzex
    provides: backend image (api/worker/beat roles), seed_sources/seed_reference/seed_staff, app.entrypoint migrate runner
  - phase: 03-client-circuit
    provides: deploy/nginx/nginx.conf TLS reverse-proxy config, deploy/Dockerfile.dashboard, deploy/docker-compose.dev.yml
  - phase: 05-telegram-monitoring-ai
    provides: userbot package (python -m userbot.main), USERBOT_HEARTBEAT_SECONDS contract
provides:
  - "deploy/docker-compose.yml — production full-stack compose (D-05.1)"
  - "Locked prod topology: api, worker, beat, userbot, dashboard, postgres, redis, minio, nginx"
  - "nginx-only ingress (80/443 TLS); all other services internal-only"
  - "Secret-free compose: every secret via ${VAR} from .env, no inline defaults"
affects: [06-05-smoke, 06-06-deployment-guide, 06-07-acceptance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Production compose derived from dev compose: drop bind-mounts + --reload, add APP_ENV=production, add dashboard, nginx-only ports"
    - "Fail-fast secrets: ${VAR} with no inline default so a missing secret surfaces at the app layer instead of running with a weak default (WR-05)"

key-files:
  created:
    - "deploy/docker-compose.yml"
  modified: []

key-decisions:
  - "DEC-06-04-no-weak-secret-defaults: sensitive vars (POSTGRES_PASSWORD/S3_ACCESS_KEY/S3_SECRET_KEY/TG_API_ID/TG_API_HASH/TG_SESSION_STRING) use bare ${VAR} with no inline default so a misconfigured deploy fails fast instead of running insecurely (WR-05 / T-06-09)"
  - "DEC-06-04-env-file-required-false-for-static-config: env_file keeps required:false so `docker compose config` validates without a real .env; production fail-fast is enforced at the app layer (pydantic Settings) + documented in the deployment guide, NOT by required:true (which would break static validation and produce a restart crash-loop)"
  - "DEC-06-04-keep-minio: MinIO retained as self-hosted S3 for request file storage; external/managed S3 swap documented inline via S3_* env vars"
  - "DEC-06-04-dashboard-context: dashboard service builds context ../dashboard with dockerfile ../deploy/Dockerfile.dashboard (matches the Dockerfile's documented build context = dashboard/)"
  - "DEC-06-04-seed-sources-added: api pre-start command adds python -m app.seed.seed_sources so a fresh prod deploy ships the UZEX/CBU sources, not just reference+staff"

patterns-established:
  - "nginx-only ingress: only the nginx service declares published host ports (80/443); api/worker/beat/userbot/dashboard/postgres/redis/minio are internal-only (T-06-10 least privilege)"
  - "Userbot as a separate long-lived process (python -m userbot.main); the aiogram webhook stays on the api service — no separate bot container (DEC-userbot-separate-process)"

requirements-completed: []

# Metrics
duration: 12 min
completed: 2026-06-22
---

# Phase 6 Plan 04: Production docker-compose.yml Summary

**Production full-stack `deploy/docker-compose.yml` with the locked single-VPS topology (api, worker, beat, userbot, dashboard, postgres, redis, minio, nginx), nginx-only TLS ingress, a separate userbot process, and zero committed secrets — validated live with `docker compose config`.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-22T14:58Z
- **Completed:** 2026-06-22T15:08Z
- **Tasks:** 1
- **Files modified:** 1 (created)

## Accomplishments
- Authored `deploy/docker-compose.yml` as the production stack, derived from `docker-compose.dev.yml` with all production deltas applied.
- Container set defined: **api, worker, beat, userbot, dashboard, postgres, redis, minio, nginx** (9 services; the 8 plan-required + minio for S3).
- **nginx is the only externally-exposed service** (publishes 80 and 443); every other service has no host `ports:` and is reachable only on the internal docker network (T-06-10 least privilege).
- **userbot is a separate long-lived process** (`command: python -m userbot.main`, `restart: unless-stopped`); the aiogram webhook stays on the api service — there is **no separate bot container** (DEC-userbot-separate-process).
- nginx mounts the **TLS prod config `deploy/nginx/nginx.conf`** (NOT `nginx.dev.conf`) plus the `letsencrypt`, `certbot_www`, and `webapp_static` volumes the prod config references (T-06-11 HTTPS everywhere).
- api command runs the migrate+seed pre-start sequence (`app.entrypoint` → `seed_reference` → `seed_staff` → `seed_sources` → `uvicorn`) with **no `--reload`** and `APP_ENV=production` (gates the Secure refresh cookie).
- **No source bind-mounts** anywhere (immutable prod images); dashboard builds the Next.js standalone image.
- **No secret literals and no weak inline defaults** for the sensitive vars — all via `${VAR}` interpolation from `.env`, fail-fast at the app layer (WR-05 / T-06-09).

## Task Commits

1. **Task 1: Author the production deploy/docker-compose.yml** - `fef5202` (feat)

**Plan metadata:** see final `docs(06-04)` commit.

## Files Created/Modified
- `deploy/docker-compose.yml` - Production full-stack compose: 9 services, healthcheck-gated `depends_on`, nginx-only ingress, TLS volumes, secret-free env interpolation.

## Decisions Made
- **DEC-06-04-no-weak-secret-defaults** — sensitive vars use bare `${VAR}` (no `:-default`) so a misconfigured deploy fails fast (WR-05 / T-06-09). The dev compose's `${POSTGRES_PASSWORD:-devpassword}` / `${S3_ACCESS_KEY:-minioadmin}` weak defaults were intentionally NOT carried into prod.
- **DEC-06-04-env-file-required-false-for-static-config** — `env_file: required: false` is kept so `docker compose config` validates without a real `.env` (acceptance criterion: exit 0). Production fail-fast is enforced at the app layer (pydantic Settings rejects empty required secrets) and documented in the file header, rather than `required: true` (which would both break static `config` validation and reintroduce the WR-05 `restart: unless-stopped` crash-loop). See Deviations.
- **DEC-06-04-keep-minio** — MinIO retained for self-hosted S3; external-S3 swap documented inline.
- **DEC-06-04-seed-sources-added** — added `python -m app.seed.seed_sources` to the api pre-start command so a fresh prod deploy ships the UZEX/CBU sources (dev compose seeds only reference+staff).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] env_file kept `required: false` (not `required: true`) to honor WR-05 without breaking static validation**
- **Found during:** Task 1
- **Issue:** The runtime brief asked production to "require real env" (WR-05) to avoid the `restart: unless-stopped` + `env_file required:false` crash-loop. The literal reading (`required: true`) conflicts with the plan's hard acceptance criterion that `docker compose -f deploy/docker-compose.yml config` exits 0 — with `required: true` and no `.env` present (the repo/CI case, since `.env` is gitignored), `config` errors out.
- **Fix:** Kept `env_file: required: false` for static-validation compatibility, but enforced the WR-05 intent the safer way: removed ALL weak inline defaults for sensitive vars so they are `${VAR}` with no fallback. A missing secret therefore fails fast at the app layer (pydantic Settings / userbot config validation) instead of silently running with a weak default. The file header documents that a real `.env` is REQUIRED at `up` time. This preserves the WR-05 goal (no insecure silent-default boot) while keeping `config` green.
- **Files modified:** deploy/docker-compose.yml
- **Verification:** `docker compose config` exits 0 (no `.env`); grep confirms no `:-` default on any sensitive var; rendered config shows blank (not weak) values for unset secrets.
- **Committed in:** fef5202 (Task 1 commit)

**2. [Rule 2 - Missing Critical] Added `seed_sources` to the api pre-start command**
- **Found during:** Task 1
- **Issue:** The dev compose api command seeds only `seed_reference` + `seed_staff`. A fresh production deploy would come up with no ingest sources (no UZEX/CBU rows), so beat would have nothing to schedule.
- **Fix:** Appended `python -m app.seed.seed_sources` (idempotent, `is_enabled=false`/`last_test_ok_at=NULL` invariant per 02-07) to the api command before uvicorn — the plan action explicitly calls for "plus the seed_sources seeder so a fresh deploy has the UZEX/CBU sources."
- **Files modified:** deploy/docker-compose.yml
- **Verification:** api `command:` contains all four seeders + `app.entrypoint` + `uvicorn`, no `--reload`.
- **Committed in:** fef5202 (Task 1 commit)

**3. [Rule 3 - Blocking] Added the TLS-support volumes nginx.conf requires**
- **Found during:** Task 1
- **Issue:** `deploy/nginx/nginx.conf` references `/etc/letsencrypt/...` (cert paths), `/var/www/certbot` (ACME webroot), and `/var/www/webapp/` (static Telegram Web App). Mounting only the config file would leave the prod nginx unable to find certs or the webapp bundle.
- **Fix:** Added named volumes `letsencrypt` (ro), `certbot_www`, and `webapp_static` (ro) to the nginx service to back the paths the prod config references, with header comments on how they're populated at deploy time.
- **Files modified:** deploy/docker-compose.yml
- **Verification:** nginx service mounts `nginx.conf` + the three volumes; rendered config resolves all mounts.
- **Committed in:** fef5202 (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (2 missing-critical, 1 blocking)
**Impact on plan:** All three are necessary for a correct, secure, deployable production stack and stay within the plan's stated action. No scope creep — no services beyond the locked set, no secrets introduced.

## Issues Encountered
None — the compose validated live on the first full run. `docker compose config` warnings about unset variables are expected and intentional (they confirm the no-weak-default fail-fast design; a real `.env` supplies the values at deploy time).

## What Was Validated Live vs. By Inspection

**Validated LIVE (Docker daemon UP, `docker compose v2.40.3`):**
- `docker compose -f deploy/docker-compose.yml config` → **exit 0**.
- `config --services` → lists all 8 required services (api, worker, beat, userbot, dashboard, postgres, redis, nginx) + minio.
- The plan's `<automated>` verify one-liner → printed **OK**.
- Rendered config (`config --format json`): **only nginx publishes host ports**, and they are exactly **80 and 443**.
- Rendered config: api command has **no `--reload`**; nginx mounts `nginx.conf` (not `nginx.dev.conf`); build contexts/dockerfiles for api (`backend/` → `Dockerfile`) and dashboard (`dashboard/` → `../deploy/Dockerfile.dashboard`) resolve correctly.

**Validated by INSPECTION (NOT executed — `docker compose up`/`build` not run):**
- Actual image builds (backend pip install, dashboard `npm run build`) — not built/run; the brief scoped this plan to authoring + static validation, and `config` does not build images.
- Live container startup, healthcheck passing, TLS handshake, and webhook reachability — these are the 06-05 smoke's job (it stands this compose up).

## Self-Check: PASSED
- `deploy/docker-compose.yml` exists on disk: FOUND.
- Commit `fef5202` exists: FOUND.
- All Task 1 acceptance criteria re-run and PASS (config exit 0; full service set; nginx-only 80/443; nginx.conf mounted; userbot separate, no bot container; api no `--reload`; no secret literals/weak defaults).

## Next Phase Readiness
- D-05.1 deliverable complete: the production compose is ready for the **06-05 smoke** (which stands it up) and the **06-06 deployment guide** (which documents using it).
- **Deploy-time note:** a real `.env` (from `deploy/.env.example`) with all `[SECRET]` markers filled is REQUIRED before `docker compose -f deploy/docker-compose.yml up`; certs must be obtained into the `letsencrypt` volume via certbot, and the built webapp bundle placed in the `webapp_static` volume. These are documented in the file header and belong in the 06-06 deployment guide.

---
*Phase: 06-acceptance-handover*
*Completed: 2026-06-22*
