---
phase: 01-walking-skeleton
plan: "05"
subsystem: infrastructure
tags: [nginx, docker-compose, dockerfile, security-headers, gap-closure]
dependency_graph:
  requires: ["01-04"]
  provides: ["SC#1-nginx-service", "nginx-events-block", "backend-dockerfile", "security-headers-static-assets"]
  affects: ["deploy/docker-compose.dev.yml", "deploy/nginx/nginx.conf", "backend/Dockerfile"]
tech_stack:
  added: []
  patterns:
    - "nginx top-level events block required alongside http block"
    - "nginx add_header non-additive: repeat all headers in any nested location that adds its own"
    - "backend/Dockerfile co-exists with deploy/Dockerfile.backend: compose resolves context:../backend + dockerfile:Dockerfile; CI uses -f deploy/Dockerfile.backend"
key_files:
  created:
    - backend/Dockerfile
  modified:
    - deploy/nginx/nginx.conf
    - deploy/docker-compose.dev.yml
decisions:
  - "Added backend/Dockerfile (not modified compose build blocks) — keeps compose context: ../backend + dockerfile: Dockerfile intact while both CI (-f deploy/Dockerfile.backend) and compose (backend/Dockerfile) continue to work"
  - "Security headers repeated inside static-asset location (not moved) — preserves server-level declaration as documentation anchor while fixing the non-additive drop"
metrics:
  duration: "8 minutes"
  completed: "2026-06-14"
  tasks_completed: 2
  files_changed: 3
---

# Phase 01 Plan 05: Gap Closure — nginx events block, backend Dockerfile, compose nginx service Summary

**One-liner:** nginx.conf gains mandatory events block + security-header inheritance fix; backend/Dockerfile created so compose resolves; nginx service added to dev compose stack, closing SC#1 gap.

## What Was Built

### Task 1 — nginx.conf: events block + CR-06 security-header fix (commit 34e66b4)

Added `worker_processes auto;` and a top-level `events { worker_connections 1024; }` block as a sibling of `http {}`, positioned before the `http {}` block. This is the mandatory nginx top-level structure without which nginx refuses to start (`no "events" section in configuration`).

Fixed CR-06: nginx's `add_header` directive is non-additive — any `add_header` in a nested location block discards all headers inherited from the enclosing server block. The static-asset location `~* \.(js|css|woff2?|png|svg|ico)$` was adding `Cache-Control "public, immutable"` and thereby silently dropping all five server-level security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Strict-Transport-Security`, `Referrer-Policy`) on every hashed asset response. All five headers are now re-declared with `always` inside that location block.

**Files:** `deploy/nginx/nginx.conf`

### Task 2 — backend/Dockerfile + compose nginx service (commit 6716e90)

Created `backend/Dockerfile` as a real build target whose build context is `backend/`. It is behaviourally equivalent to `deploy/Dockerfile.backend` (same base image, system deps, pip install pattern, non-root appuser uid 1001, HEALTHCHECK, EXPOSE 8000, CMD uvicorn). The existing compose build blocks (`context: ../backend` + `dockerfile: Dockerfile`) now resolve to this file without any changes to the compose YAML. The CI step (`docker build -f deploy/Dockerfile.backend ... backend/`) continues to work unchanged.

Added an `nginx` service to `deploy/docker-compose.dev.yml` using `image: nginx:stable`, publishing ports `80:80` and `443:443`, mounting `./nginx/nginx.conf:/etc/nginx/nginx.conf:ro`, and declaring `depends_on: api`. Updated the header comment "Services:" line to include `nginx`. Added a comment noting TLS cert volumes are wired in the prod compose.

**Files:** `backend/Dockerfile`, `deploy/docker-compose.dev.yml`

## Verification Results

All static checks passed:

| Check | Result |
|-------|--------|
| `events {` block present (non-comment line) | PASS |
| `worker_connections 1024` count = 1 | PASS |
| `X-Content-Type-Options` occurrences = 2 (server + static-asset location) | PASS |
| `backend/Dockerfile` exists + `FROM python:3.12-slim` | PASS |
| `nginx:` service in compose | PASS |
| `nginx.conf:/etc/nginx/nginx.conf:ro` volume mount | PASS |
| `80:80` and `443:443` ports in nginx service | PASS |
| `depends_on: api` in nginx service | PASS |
| "Services:" comment updated to include nginx | PASS |

Docker-based checks (require Docker daemon, CI/human verification):
- `docker compose -f deploy/docker-compose.dev.yml config` — expected to exit 0; no "failed to read dockerfile" error with `backend/Dockerfile` in place
- `nginx -t` inside `nginx:stable` — expected `syntax is ok`; only cert-file-not-found is the remaining acceptable error

## Deviations from Plan

None — plan executed exactly as written. Both tasks followed the specified implementation approach without requiring any Rule 1/2/3/4 deviations.

## Known Stubs

None. No placeholder values, TODO markers, or data stubs were introduced.

## Threat Flags

No new security surface introduced beyond what the threat model covers. The nginx service exposes only ports 80/443 (as planned); postgres/redis remain on the internal compose network. The backend/Dockerfile does not add any new network endpoints.

## Self-Check: PASSED

- `deploy/nginx/nginx.conf` — confirmed modified with events block and security headers
- `backend/Dockerfile` — confirmed created at `/Users/kholmumin/WebstormProjects/polymer-intelligence/backend/Dockerfile`
- `deploy/docker-compose.dev.yml` — confirmed modified with nginx service
- Commit `34e66b4` — Task 1 (nginx.conf)
- Commit `6716e90` — Task 2 (backend/Dockerfile + compose)
