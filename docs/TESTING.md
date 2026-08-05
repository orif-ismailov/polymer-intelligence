<!-- generated-by: gsd-doc-writer -->
# Testing

This document covers the backend pytest suite, the frontend lint/typecheck/Playwright
suites for `dashboard/`, `webapp/`, and `portal/`, the repo-root smoke/restore scripts,
and how CI wires all of it together. For the system this is testing, see
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md); for the environment variables the suite
depends on, see [`docs/CONFIGURATION.md`](CONFIGURATION.md).

## Backend (`backend/tests/`)

**Framework**: pytest 8.2+ with `pytest-asyncio` (`asyncio_mode = "auto"`) and
`pytest-cov` (installed but **not** invoked with `--cov` anywhere in CI — there is no
enforced coverage threshold). Config lives in `backend/pyproject.toml`
(`[tool.pytest.ini_options]`): `testpaths = ["tests"]`, and `pythonpath = [".", ".."]`
so tests can import the repo-root `telegram/` and `userbot/` packages as well as
`backend/app`.

As of this writing the suite is **192** `test_*.py` files directly under
`backend/tests/`, plus a `backend/tests/parsing/` sub-package (extractor unit tests +
the golden/eval accuracy harness — see below) and shared non-test helpers
(`conftest.py`, `_claims.py`, `_fake_redis.py`, `_verification_db.py`).

### Running tests

```bash
cd backend
uv sync --frozen --extra dev        # install exact locked deps

pytest tests/ -q                             # full suite (excludes performance/refresh by default)
pytest tests/test_feed_api.py -q             # one file
pytest tests/test_feed_api.py::test_name -q  # one test
pytest -k "telegram and not accuracy" -q     # by name pattern
```

No live Postgres or Redis is required for the default run — see the fixture model
below. `DATABASE_URL`/`REDIS_URL` still need to satisfy `Settings` validation (any
syntactically valid connection string works; nothing actually connects unless a test
opts into the real-DB path described further down).

### Fixture model (`backend/tests/conftest.py`)

- **Env vars**: `conftest.py` writes a fixed `_TEST_ENV` dict into `os.environ` at
  **import time** (not from a fixture) — `DATABASE_URL`, `REDIS_URL`,
  `ANTHROPIC_API_KEY`, `BOT_TOKEN`, `WEBHOOK_SECRET`, `TG_API_ID`, `TG_API_HASH`,
  `JWT_SECRET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `VERIFICATION_ENC_KEY`, plus
  `LLM_DAILY_TOKEN_LIMIT` and `OTP_MAX_SENDS_PER_DAY` pinned to their documented
  defaults. This runs before any test module import so the `Settings` singleton
  (built the first time anything imports `app.core.config`) is never accidentally
  constructed from a developer's local `backend/.env` file. A session-scoped,
  autouse `patch_env` fixture then keeps those values pinned for the session and
  rolls back any test that deliberately mutates one.
- **`client` fixture**: builds the real FastAPI app via `create_app()`, then
  overrides the `get_db` dependency with a `MagicMock()` session (so
  `db.execute(...)` succeeds without a real connection) and patches
  `app.api.health._check_redis` to return `"ok"`. Most API-level tests use this — it
  never touches a live database or Redis instance. `client_db_error` and
  `client_redis_error` are the same shape with one probe forced to fail, used by the
  `/health` tests.
- **Adapter registry isolation**: the source-adapter registry
  (`app/ingest/registry.py`) is a process-global `dict`. A session-scoped
  `_production_adapters` fixture imports every production adapter once and snapshots
  the registry; an autouse `_restore_adapter_registry` fixture resets the global to
  that snapshot after every test, so adapter-registration tests are no longer
  order-dependent regardless of what a prior test did to `_REGISTRY`.

### Real-Postgres-gated tests

A subset of tests need a real database and are skipped by default. The gate is the
shared `requires_real_db` marker in `backend/tests/_verification_db.py`:

```python
_DB_URL = os.environ.get("DATABASE_URL", "")
IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL
requires_real_db = pytest.mark.skipif(not IS_REAL_DB, reason="...")
```

It skips unless `DATABASE_URL` points at a **localhost** database literally named
`test_polymer`. **72 files** import and apply this marker — not only the files whose
names end in `_db.py` (e.g. `test_company_service_db.py`), but also several plain
`test_*.py` files that need real query/constraint behavior (e.g. `test_public_api.py`,
`test_seed.py`, `test_cbu_rates.py`, `test_supplier_matching.py`). The filename suffix
is a convention, not the actual gate — check for `@requires_real_db` if you're unsure
whether a given test needs a live database.

To actually run these locally: create a `test_polymer` database on a local Postgres
instance and point `DATABASE_URL` at it, e.g.

```bash
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/test_polymer pytest tests/ -q
```

`_verification_db.py` also defines the FK-safe table delete order used by real-DB test
teardown (children before parents, from `domain_events`/`audit_log` down through
`requests`).

### Pytest markers

Declared in `backend/pyproject.toml`, and excluded from the default run by
`addopts = "-m 'not performance and not refresh'"`:

| Marker | Meaning | How to run |
|---|---|---|
| `performance` | Integration test against a live Postgres DB seeded to ~1M rows (`test_feed_performance.py`). | `pytest -m performance` |
| `gate` | TZ §6.1.3 acceptance-gate assertions (recall ≥ 80%, precision ≥ 85%) — blocks CI when it fails. Used in `backend/tests/parsing/test_telegram_accuracy.py`. | `pytest -m gate` |
| `refresh` | Regenerates frozen extraction predictions via a **live** Anthropic call. Local only; requires an explicit `--runlive` flag; never runs in CI. | `pytest -m refresh --runlive` |

Note that `pytest tests/ -q` (the command CI and `backend/CLAUDE.md` both use) already
runs the `gate` assertions — `gate` is not excluded by the default `addopts`, only
`performance` and `refresh` are.

### Golden/eval tests for LLM extraction (`backend/tests/parsing/`)

Two accuracy harnesses back the TZ §6.1.2/§6.1.3 acceptance gates:

- **`test_uzex_accuracy.py`** (repo-root `backend/tests/`) — a pure-function harness
  over `backend/tests/fixtures/uzex/control_sample.json` (≥50 positions). Runs the
  same grade-extraction + signal-construction logic as production, with no DB and no
  network, and asserts ≥95% field-level accuracy (TZ §6.1.2). `product_id`/`grade_id`
  synonym resolution is out of scope (needs a live DB) — only structural/numeric
  fields the rule-based parser controls are checked.
- **`backend/tests/parsing/test_telegram_accuracy.py`** — mirrors the above for the
  LLM-based Telegram extractor (TZ §6.1.3). It loads a 100-message golden set via
  `golden_loader.py` and **frozen predictions** (`golden/predictions/extract_v1.json`)
  rather than calling the Anthropic API — the `@pytest.mark.gate` tests are
  **key-free**: they run safely under the CI placeholder `ANTHROPIC_API_KEY`. Recall
  and aggregate field precision are computed by `eval_metrics.py` against
  `eval_config.py`'s `RECALL_GATE` (0.80) / `PRECISION_GATE` (0.85).
- **Committed example vs. real customer fixtures**: the 100-message control sample
  and the synonym map are gated customer inputs and are **not committed**.
  `golden_loader.py` resolves each path as *explicit arg → env var
  (`GOLDEN_SET_PATH`/`SYNONYMS_PATH`) → committed `.example.json` fallback*, so the
  harness (and CI) always has something to run against:
  `backend/tests/parsing/golden/control_sample_100.example.json`,
  `backend/tests/parsing/golden/dev_golden_20.example.json`, and
  `backend/tests/parsing/synonyms.example.json` are the tracked fallbacks; the real
  customer files, if supplied, are gitignored and never checked in.
- **`backend/parsing/eval_cli.py`** — the tool a developer/trader runs at acceptance
  review time (and after any prompt-version bump) for the full per-field breakdown
  and PASS/FAIL verdict:

  ```bash
  cd backend
  python -m parsing.eval_cli --golden PATH --predictions v1 --synonyms PATH
  ```

  Exit code `0` if both gates pass, `1` otherwise.
- **Refreshing frozen predictions**: `pytest -m refresh --runlive` regenerates
  `golden/predictions/extract_{version}.json` by calling the real extractor over each
  golden row. This makes a live Anthropic call, is local-only, and must never run in
  CI (there is no `--runlive` flag set in the CI workflow).

### LLM clients are patched — no network calls in the default suite

`parsing/extractor.py` and `parsing/news_extractor.py` build their Anthropic/
`instructor` clients as module-level singletons at import time. Tests patch
`parsing.extractor._client` (see `backend/tests/parsing/test_extractor.py`) so the
default suite never makes a network call — this is why the whole suite runs green
under the CI placeholder `ANTHROPIC_API_KEY: sk-ant-ci-placeholder`.

### `RUN_MIGRATIONS_ON_STARTUP` and the test app

`RUN_MIGRATIONS_ON_STARTUP` defaults to `false` specifically so the `client` fixture's
`TestClient(create_app())` never attempts `alembic upgrade head` against a database —
combined with the mocked `get_db`/`_check_redis` overrides above, the default suite
never touches a real database or Redis instance at all. Both compose files instead run
migrations as an explicit pre-start step (`python -m app.entrypoint`), independent of
this flag.

### Writing new tests

- Naming: `backend/tests/test_<area>.py`, one file per service/router/adapter. Tests
  needing a real Postgres append `_db` to the filename by convention (not enforced —
  the actual gate is the `@requires_real_db` decorator, see above).
- Use the `client` fixture for API-level tests; call services/functions directly for
  unit tests. Reuse `_fake_redis.py` for tests that need Redis-shaped behavior
  (rate limiting, OTP storage, feed SSE bus) without a live Redis server.
- If you add a new real-DB test, import `requires_real_db` from
  `tests._verification_db` and decorate the test function/class with it; add any new
  tables you write to `_verification_db.py`'s FK-ordered delete list if your test
  needs teardown beyond what already exists.

## Repo-root `tests/` (shell scripts, not pytest)

`tests/` at the repo root holds two bash scripts — neither is collected by pytest
(`testpaths` in `backend/pyproject.toml` is scoped to `backend/tests`) and neither
runs in the GitHub Actions CI workflow; both are manual/local drills:

- **`tests/smoke/test_smoke_full_stack.sh`** — brings up the full **production**
  compose stack (`deploy/docker-compose.yml`) against a generated placeholder `.env`
  (synthetic secrets, torn down on exit), polls `/api/v1/health` until the API +
  migrate + seed sequence succeeds, submits a synthetic purchase request and asserts
  it surfaces in `v_live_feed`, then forces a fake failing source adapter through
  `run_source_fetch_isolated` three times and asserts exactly one deduped
  `source_failure` alert plus an unaffected healthy sibling source (per-source
  isolation). Run via `make smoke` (defined in `Makefile`) or directly:
  `bash tests/smoke/test_smoke_full_stack.sh`.
- **`tests/restore/test_restore_local.sh`** — proves the DB restore runbook
  end-to-end: `pg_dump`s the running dev DB, spins up a fresh disposable
  `postgres:16-alpine` container (never the dev `postgres_data` volume), restores
  into it, applies pending Alembic migrations, and verifies per-table row-count
  equality, the 14 locked ENUM types, and that `v_live_feed` is queryable — then
  asserts the whole drill finished in under 2 hours (the documented D-04 / TZ §6.1.5
  budget).

## Frontend

Each of `dashboard/`, `webapp/`, and `portal/` is an independent `npm` project with
its own `package.json`, ESLint config, `tsc`, and Playwright config. Install and run
each from its own directory:

```bash
cd dashboard   # or webapp, or portal
npm ci
npm run lint
npm run typecheck
npm run e2e     # Playwright — see per-app notes below
```

| App | `lint` | `typecheck` | `e2e` | Notes |
|---|---|---|---|---|
| `dashboard/` | `eslint` | `tsc --noEmit` | `playwright test` | e2e **runs in CI** (`dashboard-e2e` job). |
| `webapp/` | `eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0` | `tsc --noEmit` | `playwright test` | e2e config exists but is **not run in CI** — local only. |
| `portal/` | `eslint . --max-warnings 0` | `tsc --noEmit` | `playwright test` | e2e config exists but is **not run in CI**; its own config file states it is "intentionally NOT wired to run in this environment (no live API)". CI instead runs `npm run build` (vite build) as its correctness gate. |

`dashboard/CLAUDE.md` and the repo-root `CLAUDE.md` also note that `next typegen`
(`npx next typegen`) must run before `tsc --noEmit` on a clean checkout — the
generated `.next/types/routes.d.ts` that `next-env.d.ts` imports is gitignored, so
`tsc` fails with `TS2307` without it. The `dashboard` CI job runs this step
explicitly before type-checking.

### Playwright e2e — what each suite needs and covers

- **`dashboard/e2e/`** (`auth.spec.ts`, `dashboard.spec.ts`) — logs in once as staff
  via the real UI (`auth.setup.ts`, storageState reused by subsequent specs) against
  a live FastAPI backend on `http://localhost:8000` (override with `BACKEND_ORIGIN`)
  with seed data, then exercises the live feed, the purchase-requests master-detail,
  prices, sources, and alerts pages. Starts its own `next dev` on a dedicated port
  (`E2E_PORT`, default `3137`) via Playwright's `webServer` block — `next dev` proxies
  `/api/*` to `BACKEND_ORIGIN`. Requires `npx playwright install chromium` once. This
  is the suite CI's `dashboard-e2e` job runs end-to-end (it migrates + seeds
  `reference`/`staff`/`demo` and starts `uvicorn` itself before invoking `npm run e2e`).
- **`webapp/e2e/`** (`webapp.spec.ts`, `cross-app.spec.ts`) — injects a signed
  `X-Telegram-Init-Data` header (`e2e/telegram.ts`) so the Mini App authenticates in a
  plain browser; needs a FastAPI backend on `:8000` started with a `BOT_TOKEN`
  matching `E2E_BOT_TOKEN` (default `dev-bot-token-placeholder`). Its `webServer`
  block also starts a second Next.js dev server (the dashboard) for the
  cross-app §6.1.1 test. Not run in CI — run locally against a dev stack.
- **`portal/e2e/`** (`r2-portal.spec.ts`, `p0-design-system.spec.ts`,
  `product-detail.spec.ts`, `r3-eimzo.spec.ts`, `offer-wizard.spec.ts`,
  `portal.spec.ts`, `r3-contracts.spec.ts`, `p0-ui-kit.spec.ts`) — expects the portal
  SPA on `:5173` (`PORTAL_BASE_URL` override) and the API on `:8000`, single worker
  (the suite shares one backend + one per-IP OTP rate-limit bucket, so specs run
  serially — a healthy run is ~9s). Not wired into CI; a valid, type-correct local
  harness only.

## CI (`.github/workflows/ci.yml`)

Eight jobs, all triggered on push/PR to `main` or `dev`:

| Job | What it runs | Notes |
|---|---|---|
| `backend` | `ruff check .` → `mypy app/services` → `mypy app/schemas` → `pytest tests/ -q --tb=short` | Against a real `postgres:16-alpine` service container. WeasyPrint's native libs (Pango/Cairo/GDK-Pixbuf) are installed via `apt-get` first, so the contract-PDF render test actually runs instead of skipping. |
| `dashboard` | `eslint` → `next typegen` → `tsc --noEmit` | No Postgres/API needed. |
| `dashboard-e2e` | Migrates + seeds a Postgres DB, starts `uvicorn` on `:8000`, then `npm run e2e` (Playwright + chromium) | The only frontend job that runs Playwright in CI. Uploads the HTML report as an artifact regardless of pass/fail. |
| `webapp` | `eslint` → `tsc --noEmit` | No e2e. |
| `portal` | `eslint` → `tsc --noEmit` → `npm run build` (vite build) | No e2e; the production build itself is the gate. |
| `build-images` | Builds (and, on a real branch push, pushes) four GHCR images — backend, dashboard, webapp, portal | Gated on all four jobs above passing (`needs: [backend, dashboard, webapp, portal]`). |
| `deploy` | SSH + `docker compose pull && up -d` on push to `main` | Gated on `build-images`. |
| `deploy-dev` | Same, targeting the isolated `polymer-dev` compose project, on push to `dev` | Gated on `build-images`. |

**Placeholder-secret approach**: the `backend` and `dashboard-e2e` jobs hardcode
placeholder values directly in the workflow's `env:` block for every `Settings`
field that has no default (`JWT_SECRET`, `BOT_TOKEN`, `WEBHOOK_SECRET`, `TG_API_ID`,
`TG_API_HASH`, `ANTHROPIC_API_KEY`, `S3_ACCESS_KEY`/`S3_SECRET_KEY`,
`VERIFICATION_ENC_KEY`) so `Settings()` never fails to construct in CI, and no real
secret is ever needed to run the test suite. `DATABASE_URL`/`REDIS_URL` point at the
job's own service containers. See [`docs/CONFIGURATION.md`](CONFIGURATION.md) for the
full env var reference these placeholders satisfy.

## Coverage

No coverage threshold is configured anywhere in this repository — `pytest-cov` is a
declared dependency in `backend/pyproject.toml` but CI never invokes pytest with
`--cov`, and none of the three frontend `package.json` files define a coverage
script or threshold.
