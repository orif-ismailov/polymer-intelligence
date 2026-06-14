---
status: testing
phase: 01-walking-skeleton
source: [01-05-SUMMARY.md, 01-06-SUMMARY.md, 01-07-SUMMARY.md]
started: 2026-06-14T09:19:54Z
updated: 2026-06-14T09:19:54Z
---

## Current Test

number: 1
name: docker compose config resolves all six services
expected: |
  `docker compose -f deploy/docker-compose.dev.yml config` exits 0; all six services
  (postgres, redis, api, worker, beat, nginx) resolve with no "failed to read dockerfile"
  or other missing-file errors.
awaiting: user response

## Tests

### 1. docker compose config resolves all six services
expected: `docker compose -f deploy/docker-compose.dev.yml config` exits 0; all six services (postgres, redis, api, worker, beat, nginx) resolve; no missing-file errors. Then `docker compose up` brings the stack up and `/health` returns OK.
result: [pending]

### 2. nginx config syntax is valid
expected: `nginx -t` inside an `nginx:stable` container against `deploy/nginx/nginx.conf` exits 0 and prints "syntax is ok" (only acceptable error is cert-file-not-found if certs are stubbed).
result: [pending]

### 3. backend installs in a clean Python 3.12 env
expected: `pip install -e ".[dev]"` from `backend/` exits 0 with all packages installed — the `setuptools.build_meta` build backend is consumed correctly.
result: [pending]

### 4. Full CI pipeline passes green
expected: Pushing a commit runs all five GitHub Actions jobs (backend, dashboard, webapp, build-images) green. Watch points: (a) backend pip install succeeds; (b) dashboard `tsc --noEmit` — REVIEW WR-01 warns `tsc` may raise TS2307 on `.next/types/routes.d.ts` on a clean checkout where `.next` is gitignored; if the dashboard job fails, add `npx next build --no-lint` before `tsc`; (c) build-images job succeeds.
result: [pending]

### 5. Browser cookie / CORS flow works end-to-end
expected: With settings-driven CORS (non-wildcard), the dashboard login page in a real browser sends the httpOnly refresh cookie on `/api/v1/auth/refresh` for the allowed origin; 401 on bad credentials, 200 + access token on good credentials.
result: [pending]

### 6. CI S3 env var name matches config (REVIEW CR-01)
expected: `ci.yml` exports `S3_ENDPOINT: http://localhost:9000` (renamed from `S3_ENDPOINT_URL`) so `config.py`'s `Settings.S3_ENDPOINT` reads it instead of silently falling back to an empty string. Pending fix from REVIEW CR-01; should be resolved before Phase 2 adds any S3/MinIO client code.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
