---
status: testing
phase: 01-walking-skeleton
source: [01-VERIFICATION.md, 01-08-SUMMARY.md, 01-09-SUMMARY.md, 01-10-SUMMARY.md]
started: 2026-06-14T09:19:54Z
updated: 2026-06-15T13:00:00Z
---

## Current Test

number: 1
name: Full CI pipeline passes green on a clean GitHub Actions checkout
expected: |
  Push to main/develop; all 5 GitHub Actions jobs go green — especially the
  dashboard job, where the new `npx next typegen` step must generate
  `.next/types/routes.d.ts` on a clean checkout so `tsc --noEmit` exits 0 (no TS2307).
awaiting: user response

## Tests

### 1. Full CI pipeline passes green (live GitHub Actions run) — SC#5
expected: Push to main/develop; all 5 jobs (backend ruff+mypy+pytest, dashboard eslint+typegen+tsc, webapp eslint+tsc, build-images) pass green on a clean runner checkout.
result: pending
note: |
  All gates confirmed locally by the orchestrator: `ruff check .` 0 violations,
  `mypy app/services app/schemas` 0 errors, `pytest` 105 passed / 17 skipped, dashboard
  `next typegen` → `tsc --noEmit` exit 0, `eslint --max-warnings 0` exit 0. The remaining
  unknown is only the clean-runner behaviour of the new typegen step — needs a real CI run.
  Fastest path: `/gsd:ship` (opens a PR → triggers CI) or push the branch.

### 2. Browser CORS / httpOnly refresh-cookie flow — SC#3/SC#4
expected: Non-wildcard CORS for the dashboard origin; login issues an access JWT + an httpOnly refresh cookie; role guards enforced.
result: pass
note: |
  Live-verified by the orchestrator against a running dev stack (curl, not browser DevTools):
  - CORS preflight from Origin http://localhost:3000 → 200 with
    `access-control-allow-origin: http://localhost:3000` (NOT wildcard, CR-04) +
    `access-control-allow-credentials: true`.
  - POST /api/v1/auth/login (admin) → 200, access-token JWT (role=admin, 15-min exp),
    `Set-Cookie: refresh_token=...; HttpOnly; Max-Age=604800 (7d); Path=/api/v1/auth; SameSite=lax`.
  - RBAC: admin→/admin/whoami 200; viewer→/admin/whoami 403; no-token→401.
  - POST /api/v1/auth/refresh with the httpOnly cookie → 200.
  Only the literal in-browser DevTools observation remains; the API-side behaviour is confirmed.

## Resolved Gaps (gap-closure plans 01-08..01-10, executed 2026-06-15)

### G1. docker compose up brings up nginx; /health returns OK — SC#1
result: resolved
note: |
  Plan 01-08 (dedicated dev-conf-file option). Added deploy/nginx/nginx.dev.conf (HTTP-only:
  listen 80, no 443/ssl, no letsencrypt, no /dashboard upstream; proxy_pass /api/ → api:8000;
  security headers + auth rate-limit retained). dev compose mounts it, ports 80:80; nginx.conf
  unchanged as prod config. LIVE-VERIFIED: `docker compose up` → nginx Up, no [emerg];
  `curl http://localhost/api/v1/health` → 200 `{"status":"ok","db":"ok","redis":"ok","schema_version":"0001"}`.

### G2. CI (ruff, mypy, eslint+tsc, tests, image build) passes green — SC#5
result: resolved
note: |
  Plan 01-10. Resolved all 124 ruff violations; pinned ruff==0.15.17 / mypy==2.1.0.
  ruff check . → All checks passed; mypy services+schemas → 0 errors; pytest 105 passed.
  Dashboard tsc clean-checkout failure fixed by adding `npx next typegen` before tsc in ci.yml
  (see Test 1 for the remaining live-CI confirmation).

### G3. CI S3 endpoint env var matches Settings field (REVIEW CR-01) — major
result: resolved
note: |
  Plan 01-09. Renamed ci.yml S3_ENDPOINT_URL → S3_ENDPOINT to match Settings.S3_ENDPOINT;
  added a regression test (TestCiEnvContract) locking the contract.

## Deferred (Phase 2)

### D1. worker + beat containers fully operational — SC#1 (amended)
note: |
  worker/beat require the Celery app `app.tasks.celery_app`, built in Phase 2 (where the beat
  schedule drives UZEX fetch). SC#1 was amended to scope Phase 1 to api/postgres/redis/nginx +
  /health. Recorded in ROADMAP.md SC#1 and STATE.md Deferred Items. Accepted override in
  01-VERIFICATION.md (5/5, 1 override).

## Summary

total: 2
passed: 1
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

(none open — the 3 round-1 gaps above are resolved; SC#1 worker/beat is an accepted Phase-2 deferral)
