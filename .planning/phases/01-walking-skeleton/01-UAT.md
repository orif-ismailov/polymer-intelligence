---
status: diagnosed
phase: 01-walking-skeleton
source: [01-05-SUMMARY.md, 01-06-SUMMARY.md, 01-07-SUMMARY.md]
started: 2026-06-14T09:19:54Z
updated: 2026-06-15T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. docker compose config resolves all six services
expected: `docker compose -f deploy/docker-compose.dev.yml config` exits 0; all six services (postgres, redis, api, worker, beat, nginx) resolve; no missing-file errors.
result: pass
note: Verified live — `docker compose config` exits 0; `--services` lists postgres, redis, worker, api, beat, nginx.

### 2. nginx config syntax is valid / nginx starts in the dev stack
expected: `nginx -t` against `deploy/nginx/nginx.conf` exits 0; nginx comes up in `docker compose up` (only acceptable error is cert-file-not-found if certs are stubbed).
result: issue
reported: "nginx -t fails in dev-equivalent conditions. Config SYNTAX is valid, but nginx will NOT start in the dev compose: (1) `location /dashboard/` proxies to `http://dashboard:3000` (line 118) and the dev compose intentionally excludes the dashboard service (compose comment line 11) → startup DNS resolution fails: `[emerg] host not found in upstream \"dashboard\"`; (2) `listen 443 ssl` references `/etc/letsencrypt/live/example.com/fullchain.pem` which the dev nginx service never mounts → `[emerg] cannot load certificate`. Either crashes nginx, so SC#1 'docker compose up brings up nginx' is not met."
severity: blocker

### 3. backend builds with the PEP 517 build backend
expected: `pip install -e ".[dev]"` / a PEP 517 build succeeds; `build-backend = "setuptools.build_meta"` is consumed correctly.
result: pass
note: Verified live — `python -m build --wheel backend/` ran the `setuptools.build_meta` backend and produced `polymer_intelligence_backend-0.1.0-py3-none-any.whl` (exit 0). The 01-06 build-backend fix is real.

### 4. Full CI pipeline passes green
expected: All CI jobs green (backend ruff+mypy+pytest, dashboard eslint+tsc, webapp eslint+tsc, build-images).
result: issue
reported: "Backend CI ruff gate FAILS. CI installs `ruff>=0.4.0` (unpinned → latest) and runs `ruff check .` from backend/. Live run reports **124 errors** (I001 unsorted-imports ×32, F401 unused-import ×12, UP017 datetime-timezone-utc ×12, UP042 replace-str-enum ×14, SIM117 ×10, B008 ×8, B017/B904 ×7, N806 ×5, plus more). The backend code was never actually linted — 01-06 only removed `|| true` from eslint and fixed the build backend, it never ran ruff. SC#5 'CI passes green' is not met. (mypy could not be run locally — not installed in the venv — so the mypy gate is also unverified. Dashboard tsc and eslint pass locally including with `.next` absent, so WR-01 did NOT reproduce; webapp not separately failing.)"
severity: blocker

### 5. Browser CORS / httpOnly-cookie refresh flow
expected: With settings-driven CORS (non-wildcard), the browser attaches the httpOnly refresh cookie on `/api/v1/auth/refresh` for the allowed origin; 401 on bad credentials, 200 + access token on good credentials.
result: pass
note: Code defect (CR-04) is verifiably fixed — `main.py` uses `allow_origins=settings.CORS_ALLOWED_ORIGINS` (default `["http://localhost:3000"]`, non-wildcard) with explicit methods/headers and `allow_credentials=True`. Live browser enforcement still worth a manual spot-check once the stack runs, but the wildcard-with-credentials defect is gone.

### 6. CI S3 env var name matches config (REVIEW CR-01)
expected: `ci.yml` exports `S3_ENDPOINT` so `config.py`'s `Settings.S3_ENDPOINT` reads it.
result: issue
reported: "Confirmed mismatch — `ci.yml:79` exports `S3_ENDPOINT_URL: http://localhost:9000` but `config.py:62` reads `S3_ENDPOINT: str = \"\"`. With `case_sensitive=True` + `extra=\"ignore\"` the CI value is silently dropped and the field defaults to empty string. Latent (no S3 client until Phase 2/3) but a silent storage-misconfiguration on a required dependency. REVIEW CR-01."
severity: major

## Summary

total: 6
passed: 3
issues: 3
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "docker compose up brings up nginx; /health returns OK (SC#1)"
  status: failed
  reason: "nginx will not start in the dev compose: unresolvable `dashboard` upstream (proxy_pass http://dashboard:3000 at nginx.conf:118; dashboard service excluded from dev scaffold) and unmounted SSL certs (listen 443 ssl → /etc/letsencrypt/... not mounted by the dev nginx service). nginx -t reproduces both as [emerg]."
  severity: blocker
  test: 2
  root_cause: "deploy/nginx/nginx.conf is effectively a production config (443/ssl + letsencrypt certs + dashboard upstream) reused verbatim by the dev compose, which mounts no certs and omits the dashboard service. nginx resolves all upstream hostnames and loads all ssl_certificate files at startup, so both cause a hard [emerg] start failure."
  artifacts:
    - path: "deploy/nginx/nginx.conf"
      issue: "443 ssl server block with letsencrypt cert paths + `location /dashboard/` proxy_pass to dashboard:3000, neither available in the dev compose"
    - path: "deploy/docker-compose.dev.yml"
      issue: "nginx service mounts only nginx.conf (no certs) and the stack has no dashboard service"
  missing:
    - "Make the dev nginx startable: e.g. a dev-specific nginx.conf (HTTP-only, no 443/ssl block) OR mount self-signed certs in the dev compose; AND guard the dashboard upstream — make it resolver+variable based (deferred resolution, 502 when down) or drop the /dashboard/ location from the dev config since the dashboard runs separately"
    - "Re-verify with an actual `docker compose -f deploy/docker-compose.dev.yml up` that nginx stays up and `/health` returns OK"
  debug_session: ""

- truth: "CI (ruff, mypy, eslint+tsc, tests, image build) passes green (SC#5)"
  status: failed
  reason: "`ruff check .` reports 124 errors against the backend; the backend code was never linted. mypy gate unverified locally."
  severity: blocker
  test: 4
  root_cause: "01-04 set up the CI workflow and 01-06 fixed the eslint `|| true` and the build backend, but no one ever ran `ruff check` against the backend source. ruff is pinned `>=0.4.0` (unpinned upper bound) so CI runs the latest ruff with select=[E,F,I,N,UP,B,SIM]; the existing code violates 124 of those rules (import order, unused imports, datetime.UTC/str-enum upgrades, B-series, SIM-series, N806)."
  artifacts:
    - path: "backend/app/**/*.py"
      issue: "124 ruff violations: I001 ×32, UP042 ×14, F401 ×12, UP017 ×12, SIM117 ×10, B008 ×8, B017/B904 ×7, N806 ×5, others"
    - path: "backend/pyproject.toml"
      issue: "ruff>=0.4.0 unpinned — CI lint behavior drifts with ruff releases"
    - path: ".github/workflows/ci.yml"
      issue: "ruff/mypy gates were never confirmed green"
  missing:
    - "Run `ruff check --fix` (68 autofixable) then manually resolve the non-autofixable findings (B008 function-call-in-default-argument, B017/B904, N806, SIM117, UP042 str-enum), keeping behavior identical"
    - "Pin ruff (and ideally mypy) to a known-good version so the CI lint gate is reproducible"
    - "Install/run mypy on app/services + app/schemas and resolve any findings so the type gate is actually green"
    - "Re-run the full CI command set locally (ruff check ., mypy, pytest, eslint, tsc) to confirm green before claiming SC#5"
  debug_session: ""

- truth: "CI S3 endpoint env var matches the Settings field (REVIEW CR-01)"
  status: failed
  reason: "ci.yml exports S3_ENDPOINT_URL; config.py reads S3_ENDPOINT (case-sensitive). The value is silently discarded → empty-string fallback."
  severity: major
  test: 6
  root_cause: "Env var name drift between the CI workflow and the pydantic Settings field; `case_sensitive=True` + `extra=\"ignore\"` means the mismatch fails silently with no startup error."
  artifacts:
    - path: ".github/workflows/ci.yml"
      issue: "line 79 exports S3_ENDPOINT_URL: http://localhost:9000"
    - path: "backend/app/core/config.py"
      issue: "line 62 reads S3_ENDPOINT: str = \"\" (no non-empty validation)"
  missing:
    - "Rename ci.yml `S3_ENDPOINT_URL` → `S3_ENDPOINT` to match the Settings field"
    - "Optionally fail-fast: validate S3_ENDPOINT is non-empty when an S3-dependent feature is enabled, so a future mismatch is loud not silent"
  debug_session: ""
