---
phase: 01-walking-skeleton
plan: "08"
subsystem: infra
tags: [nginx, docker, docker-compose, dev-stack, proxy, rate-limiting, security-headers]

# Dependency graph
requires:
  - phase: 01-walking-skeleton
    provides: "Plan 01-05 added nginx service to dev compose with valid events{} block; this plan closes UAT Gap 1 by making it actually boot"
provides:
  - "deploy/nginx/nginx.dev.conf — HTTP-only dev nginx config: no letsencrypt certs, no dashboard upstream, limit_req_zone + auth-login rate-limit + 4 security headers + /api/ proxy to api:8000"
  - "deploy/docker-compose.dev.yml updated — nginx mounts nginx.dev.conf, publishes port 80:80 only (443 dropped for dev)"
  - "SC#1 closed: dev compose nginx boots with no [emerg], /api/v1/health returns HTTP 200 live-verified"
affects:
  - 01-walking-skeleton
  - future phases that bring up the dev compose stack

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "prod/dev nginx config split: nginx.conf = prod (TLS, letsencrypt, dashboard upstream); nginx.dev.conf = dev (HTTP-only, no dashboard dependency)"
    - "Dev nginx liveness: root = / returns 200 plain-text instead of 301 to absent dashboard"

key-files:
  created:
    - deploy/nginx/nginx.dev.conf
  modified:
    - deploy/docker-compose.dev.yml

key-decisions:
  - "dev-conf-file strategy chosen: a separate deploy/nginx/nginx.dev.conf is mounted by dev compose; nginx.conf is left UNCHANGED as the prod config (TLS/letsencrypt/dashboard preserved for prod)"
  - "HTTP-only dev server on port 80 only; 443:443 port binding dropped from dev compose (no TLS server block in nginx.dev.conf)"
  - "No /dashboard/ location in dev config and no return 301 /dashboard/ — root returns 200 dev stack up so curl confirms liveness without the absent dashboard upstream"
  - "limit_req_zone + auth-login burst block carried into nginx.dev.conf so rate-limiting is effective in dev (T-08-03)"
  - "HSTS header omitted in dev (HTTP-only; HSTS over plain HTTP is a no-op and could interfere with prod domain testing)"

patterns-established:
  - "prod/dev nginx split: keep prod config intact; mount a dev-specific config from dev compose"
  - "Dev liveness location: location = / { return 200; } instead of redirecting to a service not in the dev compose"

requirements-completed: ["REQ-nfr-security", "REQ-nfr-observability"]

# Metrics
duration: gap-closure (Task 1 only; decision and human-verify checkpoints resolved by operator/orchestrator)
completed: 2026-06-15
---

# Phase 01 Plan 08: Gap-Closure — Dev Nginx Boot (UAT Gap 1 / SC#1) Summary

**Separate nginx.dev.conf (HTTP-only, no dashboard upstream, no letsencrypt) mounted by dev compose so nginx boots cleanly and `/api/v1/health` returns 200 — SC#1 live-verified with `docker compose up`.**

## Performance

- **Duration:** Gap-closure plan — Task 1 committed at 2026-06-15T07:10:58Z; live verification completed by orchestrator on 2026-06-15
- **Started:** 2026-06-15 (decision checkpoint resolved: dev-conf-file)
- **Completed:** 2026-06-15
- **Tasks:** 1 auto task + 1 decision checkpoint (resolved) + 1 human-verify checkpoint (PASSED)
- **Files modified:** 2

## Accomplishments

- Created `deploy/nginx/nginx.dev.conf`: a self-contained HTTP-only nginx config with `listen 80`, `limit_req_zone` + auth-login rate-limit, 4 security headers, `location /api/ { proxy_pass http://api:8000; }`, and `location = / { return 200 "dev stack up"; }` — NO `listen 443 ssl`, NO `ssl_certificate /etc/letsencrypt`, NO `/dashboard/` upstream, NO `return 301 /dashboard/`
- Updated `deploy/docker-compose.dev.yml`: nginx service now mounts `./nginx/nginx.dev.conf:/etc/nginx/nginx.conf:ro` and publishes `80:80` only (443:443 dropped since no TLS server block in dev config)
- `deploy/nginx/nginx.conf` left UNCHANGED — production TLS, letsencrypt cert references, HTTPS server block, and `/dashboard/` upstream are fully preserved for the prod compose
- SC#1 confirmed live: `docker compose up -d` → all 6 containers created, nginx Up with no `[emerg]`, `curl -i http://localhost/api/v1/health` → HTTP 200

## Task Commits

1. **Task 1: Make the dev nginx boot (dev-conf-file option)** — `9912950` (fix)

**Plan metadata:** (this SUMMARY commit — see final_commit below)

## Files Created/Modified

- `deploy/nginx/nginx.dev.conf` — HTTP-only dev nginx config: `worker_processes auto`, `events { worker_connections 1024; }`, `http { limit_req_zone $binary_remote_addr zone=auth_login:10m rate=10r/m; ... server { listen 80; server_name _; } }` with 4 security headers (X-Content-Type-Options, X-Frame-Options, Content-Security-Policy frame-ancestors, Referrer-Policy), auth-login rate-limit location, and `/api/` proxy to `http://api:8000` with `proxy_buffering off` (SSE-compatible)
- `deploy/docker-compose.dev.yml` — nginx service volume mount changed from `./nginx/nginx.conf` to `./nginx/nginx.dev.conf:/etc/nginx/nginx.conf:ro`; ports changed from `80:80` + `443:443` to `80:80` only

## Decisions Made

**Decision checkpoint resolved: `dev-conf-file`**

The operator selected the "Add deploy/nginx/nginx.dev.conf and mount it from the dev compose" option. Rationale for why the prod/dev split is safe:

- `deploy/nginx/nginx.conf` is the production config (443/ssl, letsencrypt cert paths, dashboard upstream, HSTS, HTTP→HTTPS redirect). It is completely unchanged — verified via `git diff HEAD~1 -- deploy/nginx/nginx.conf` showing zero diff.
- `deploy/nginx/nginx.dev.conf` is a purpose-built dev config. It duplicates the structural elements needed for dev correctness (rate-limit zone, security headers, `/api/` proxy) but deliberately omits TLS and dashboard.
- The divergence (two files) is the intended trade-off: explicit separation over a single file with conditional logic. Nginx has no native `if-cert-exists` guard, making conditional TLS in a single file fragile and risky for the prod posture. Two files removes that risk.
- The prod compose (when created) will continue mounting `nginx.conf`; the dev compose now mounts `nginx.dev.conf`. No prod capability is weakened.

## Deviations from Plan

None - plan executed exactly as written. The decision checkpoint selected `dev-conf-file`, Task 1 implemented it per the plan's `dev-conf-file` action specification, and the human-verify checkpoint was resolved by the orchestrator performing a live `docker compose up`.

## Out-of-Scope Observations (flag for phase verifier — do NOT fix in 01-08)

The following were observed during live re-verification. They are documented here for the phase verifier and are explicitly out of scope for this gap-closure plan.

**1. `.env` file required for api startup**

The api service exits on boot with a pydantic `ValidationError` if a repo-root `.env` is absent. 8 settings are required: `ANTHROPIC_API_KEY`, `BOT_TOKEN`, `WEBHOOK_SECRET`, `TG_API_ID`, `TG_API_HASH`, `JWT_SECRET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`. The compose file header documents this as a prerequisite; the `.env` is gitignored (dev setup, not a defect). The orchestrator created a local gitignored `.env` with dev placeholders to complete the live check. This is expected documented behavior for a developer setting up the stack — not a 01-08 defect. Future plans should ensure `.env.example` is present and documented.

**2. worker and beat containers crash-loop: `ModuleNotFoundError: No module named 'app.tasks'`**

The Celery `worker` and `beat` containers crash-loop because `app.tasks` does not yet exist. Celery task modules are a later-phase concern (Phase 2/3 ingest/parse/notify pipeline). The walking skeleton does not require worker/beat to be operational — only nginx+api+postgres+redis are needed for SC#1. Flag for the Phase 2/3 plan that introduces `app.tasks`.

**3. nginx upstream IP caching on api container recreation**

nginx caches the upstream `api` IP at boot (standard nginx behavior without a resolver directive). If the `api` container is recreated (new IP assigned) while nginx stays up, requests to `/api/` return 502 until `docker compose restart nginx`. In a clean `docker compose up` the `depends_on: api` ordering means nginx boots after api and caches the correct IP. Acceptable for a dev stack. If zero-downtime api restarts become a dev requirement, a future plan can add `resolver 127.0.0.11 valid=10s` + a variable-based `proxy_pass` to force runtime DNS resolution.

## Live Re-Verification Results (SC#1 confirmation)

Performed by the orchestrator on a Docker-capable machine on 2026-06-15:

**Step 1 — Compose config validation:**
```
docker compose -f deploy/docker-compose.dev.yml config
```
Exit code: 0. No "host not found" or "cannot load certificate" errors.

**Step 2 — Isolated nginx syntax check:**
```
docker run --rm -v .../nginx.dev.conf:/etc/nginx/nginx.conf:ro nginx:stable nginx -t
```
Result: fails with `[emerg] host not found in upstream "api"` — this is EXPECTED when testing nginx in isolation (no `api` host on a lone container with no compose network). Critically, the two Gap 1 `[emerg]` causes are GONE: no `host not found in upstream "dashboard"` and no `cannot load certificate`.

**Step 3 — Full stack up:**
```
docker compose up -d
```
All 6 containers created. nginx container: `Up` with NO `[emerg]` in `docker compose logs nginx`.

**Step 4 — Health check through proxy:**
```
curl -i http://localhost/api/v1/health
```
Response:
```
HTTP/1.1 200 OK
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: frame-ancestors 'none'
Referrer-Policy: strict-origin-when-cross-origin

{"status":"ok","db":"ok","redis":"ok","schema_version":null}
```
SC#1 CONFIRMED: HTTP 200, JSON body with `db:ok` and `redis:ok`, all 4 security headers present.

**Step 5 — Stack teardown:**
```
docker compose down
```
Completed cleanly.

## Issues Encountered

None beyond the out-of-scope observations documented above. Task 1 executed cleanly per plan.

## User Setup Required

Developers must create a repo-root `.env` before `docker compose up`. Required variables (dev placeholders acceptable for local testing):

```
ANTHROPIC_API_KEY=...
BOT_TOKEN=...
WEBHOOK_SECRET=...
TG_API_ID=...
TG_API_HASH=...
JWT_SECRET=...
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
```

Without `.env`, the api container exits with a pydantic ValidationError and the health check cannot pass through nginx (nginx still boots, but `/api/v1/health` returns 502 until api is up).

## Next Phase Readiness

- Dev compose backbone operational: nginx + api + postgres + redis form the HTTP dev skeleton
- `/api/v1/health` returns 200 through the nginx proxy — walking skeleton walks
- SC#1 (UAT Gap 1) is closed with live evidence
- Out-of-scope items to address in later plans: `.env.example` file, `app.tasks` module (Phase 2/3), optional nginx upstream resolver for api recreation resilience

## Threat Surface Scan

No new security-relevant surface introduced beyond the plan's threat model. The threat register items in the plan frontmatter were all addressed:
- T-08-01 (boot failure DoS): MITIGATED — nginx now boots
- T-08-02 (HTTP-only in dev): ACCEPTED — documented, prod TLS preserved
- T-08-03 (credential stuffing): MITIGATED — `limit_req_zone` + auth-login burst block carried into `nginx.dev.conf`
- T-04-05 (exposed internal services): MITIGATED — only port 80 published; postgres/redis/api remain on compose network

---

## Self-Check: PASSED

- `deploy/nginx/nginx.dev.conf` — FOUND (created by commit 9912950)
- `deploy/docker-compose.dev.yml` — FOUND (modified by commit 9912950)
- `deploy/nginx/nginx.conf` — FOUND and UNCHANGED (prod config preserved)
- Commit 9912950 — FOUND (`git show --stat 9912950` returned full diff above)
- SC#1 live verification — CONFIRMED by orchestrator live `docker compose up` on 2026-06-15

---
*Phase: 01-walking-skeleton*
*Completed: 2026-06-15*
