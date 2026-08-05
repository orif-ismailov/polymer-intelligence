<!-- generated-by: gsd-doc-writer -->
# backend/

FastAPI + Celery + SQLAlchemy 2 core of Polymer Intelligence — a market-intelligence
platform for Uzbekistan's domestic polymer market. This package owns the API, the
ingest source adapters, the Celery task/worker/beat topology, the LLM parsing
pipeline, and the client-cabinet (portal) and Telegram Web App server surfaces. It
is the hub every other component in this monorepo (`dashboard/`, `webapp/`, `portal/`,
`telegram/`, `userbot/`) talks to.

For the full system narrative, see [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).
For the complete environment-variable contract, see
[`docs/CONFIGURATION.md`](../docs/CONFIGURATION.md). For every registered route, see
[`docs/API.md`](../docs/API.md). For day-to-day workflow and CI details beyond this
page, see [`docs/DEVELOPMENT.md`](../docs/DEVELOPMENT.md) and
[`docs/TESTING.md`](../docs/TESTING.md).

## Prerequisites

- Python `>= 3.12` (`pyproject.toml` `requires-python`)
- [`uv`](https://docs.astral.sh/uv/) for dependency management — `uv.lock` is authoritative
- PostgreSQL and Redis reachable via `DATABASE_URL` / `REDIS_URL`
- WeasyPrint's native libraries (Pango, Cairo, GDK-Pixbuf) if you need to render
  contract PDFs locally — see the CI step in `.github/workflows/ci.yml` for the
  exact `apt` package list on Debian/Ubuntu

## Install

```bash
cd backend
uv sync --frozen --extra dev        # installs the exact locked deps from uv.lock
```

## Configuration

All settings are read once at startup by `app/core/config.py` (`Settings`, a
Pydantic `BaseSettings` subclass exposed as the single module-level `settings`
instance — import it, never construct `Settings()` again). Secrets
(`JWT_SECRET`, `BOT_TOKEN`, `WEBHOOK_SECRET`, `TG_API_*`, `ANTHROPIC_API_KEY`,
`S3_*`, ...) have no defaults and fail fast at startup if missing. The repo-root
`deploy/.env.example` is the authoritative env contract; the full variable
reference lives in [`docs/CONFIGURATION.md`](../docs/CONFIGURATION.md).

`RUN_MIGRATIONS_ON_STARTUP` defaults to `false` so the TestClient-built app used
by the test suite / CI never touches a database.

## Running the API locally

```bash
cd backend
uv run uvicorn app.main:app --reload   # needs DATABASE_URL/REDIS_URL + required secrets in env
```

Routes are mounted under `/api/v1` by the `create_app()` factory in `app/main.py`.
With `DEBUG=true`, `/docs`, `/redoc`, and `/openapi.json` are exposed (off by
default/production).

To run the full stack (Postgres, Redis, MinIO, api, worker, beat, userbot, nginx)
instead, use the repo-root compose file — see
[`docs/DEVELOPMENT.md`](../docs/DEVELOPMENT.md).

## Database migrations

Alembic migrations live in `alembic/versions/`. The chain currently runs from
`0001` through **`0034`** (`0034_manufacturers_module.py` is the current head).

```bash
cd backend
uv run alembic upgrade head
```

`app/entrypoint.py` runs this same upgrade under a PostgreSQL session-level
advisory lock, so it is safe to let the container entrypoint apply migrations on
startup even with multiple workers starting concurrently.

New ORM models must be added to `app/models/__init__.py` (in FK order) or
alembic's `env.py` will not see them when autogenerating a revision.

## Directory map

| Path | Role |
|------|------|
| `app/main.py` | `create_app()` factory — CORS, lifespan (migrations + Telegram webhook registration), and every router mounted under `/api/v1`. |
| `app/core/` | Cross-cutting infrastructure: `config.py` (`settings` singleton), `db.py`, `logging.py` (structlog), `security.py`, `crypto.py` (Fernet PII encryption), `storage.py` (S3/MinIO), `time.py`, `feed_bus.py` (SSE). |
| `app/api/` | Routers. Includes `app/api/webapp/` (Telegram Web App surface), `app/api/portal/` (client cabinet — auth, companies, offers, market, inquiries, requests, contracts, E-IMZO, deals, compliance, lab, samples, notifications), plus admin/staff routers (`admin_*.py`), `feed.py`, `dashboard*.py`, `prices.py`, `sources.py`, `sourcing.py`, `reports.py`, `moderation.py`, `public.py`, `telegram_webhook.py`, `webhooks_escrow.py`. `deps.py` holds auth/RBAC dependencies. |
| `app/models/` | SQLAlchemy 2 ORM. `__init__.py` imports every module in FK order so `Base.metadata` is complete for Alembic. Domains: `signals`, `sources`, `requests`, `marketplace`, `sourcing`, `reports`, `app_settings`, `prices`, `alerts`, `reference`, `counterparties`, `staff`, `accounts`, `companies`, `verification`, `eimzo`, `contracts`, `deals`, `payments`, `compliance`, `lab`, `manufacturers`, `registry`, `notifications`, `integration`, `enums`. |
| `app/schemas/` | Pydantic request/response models (mypy-strict, CI-gated). |
| `app/services/` | Business logic (mypy-strict, CI-gated) — the largest package (53 modules). Includes ingest/parsing glue, `offer_service`, `sourcing_service`, `request_service`, `settings_service`, `event_service` (transactional outbox), `otp_service`, `company_service`, `verification_service`, `eimzo_service`, `contract_service`, `contract_render`, `lab_service`, `sample_service`, `registry_service`, `news_service`, `news_dedup`, `report_service`, and more. |
| `app/ingest/` | Source adapters implementing the `SourceAdapter` protocol (`base.py`): `uzex/`, `cbu_rates/`, `xarid/`, plus no-code adapters `html_table/`, `llm_page/`, `rss/`, `telegram_channel/`. Adapters self-register at import time into `registry.py`. `http_client.py` is SSRF-guarded. |
| `app/integrations/` | External gateway adapters: `sms/` (console/Eskiz), `eimzo/` (UNICON e-imzo-server sidecar client), `escrow/` (outbound client + inbound provider-event mapper registry), `chem_registry/` and `gov_registry/` (stubs pending external access), `circuit_breaker.py`. |
| `app/tasks/` | Celery app (`celery_app.py`), beat schedule (`schedule.py`), and every task module — `ingest*.py`, `parse*.py`, `notify.py`, `reports.py`, `nightly_catchup.py`, `rescore.py`, `userbot_health.py`, `request_analysis.py`, `verification.py`, `contracts.py`, `deals.py`, `payments.py`, `portal_notify.py`, `rfq_push.py`, `events.py`. Task modules must be listed explicitly in `_TASK_MODULES` — autodiscover is a no-op here. |
| `app/seed/` | Idempotent seeders (`ON CONFLICT`-safe): `seed_reference`, `seed_staff`, `seed_sources`, `seed_demo`, `seed_contract_templates`, `seed_substances`, `seed_showcase*`. JSON/HTML fixtures under `seed/data/`. |
| `parsing/` | LLM extraction — a **repo-root-relative sibling package of `app/`, at `backend/parsing/`, not `backend/app/parsing/`**. Contains `extractor.py` (trade signals), `news_extractor.py` + `news_schemas.py` (news classification), `prompts/` (versioned prompt files per family), `budget.py` (daily token budget guard), `fallback.py` (rule-based degrade path), `lead_scoring.py`, `text_prep.py`, `eval_cli.py` (golden-fixture accuracy eval). Not directly covered by the mypy CI gate (see `pyproject.toml` mypy overrides), but transitively imported code is still checked. |
| `alembic/` | Migration environment (`env.py`) and `versions/` (`0001` → `0034`). |
| `tests/` | Pytest suite — see [`docs/TESTING.md`](../docs/TESTING.md). |
| `scripts/` | Standalone operational/dev scripts. |
| `Dockerfile` | Backend API/worker image build. |

## CI gates

Run from `backend/` (matches `.github/workflows/ci.yml`, job "Backend (ruff · mypy · pytest)"):

```bash
ruff check .                                   # lint
mypy app/services --ignore-missing-imports     # type-check (scoped to services/ + schemas/)
mypy app/schemas  --ignore-missing-imports
pytest tests/ -q                               # full suite (needs Postgres + Redis)
```

CI runs these against a live `postgres:16-alpine` service and placeholder secrets so
`Settings` doesn't fail-fast. `ruff==0.15.17` and `mypy==2.1.0` are pinned exactly
(see `pyproject.toml` dev extras) for a reproducible gate — don't bump without
re-running everything locally first.

Single test / pattern:

```bash
pytest tests/test_feed_api.py -q
pytest tests/test_feed_api.py::test_name -q
pytest -k "telegram and not accuracy" -q
```

The default `pytest` run excludes the `performance` (needs a live Postgres seeded
with ~1M rows) and `refresh` (needs live LLM calls) markers — see
`pyproject.toml` `addopts` and [`docs/TESTING.md`](../docs/TESTING.md) for how to
opt into them.

## Where to go next

- [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) — system-wide design and data flow
- [`docs/CONFIGURATION.md`](../docs/CONFIGURATION.md) — full environment-variable reference
- [`docs/API.md`](../docs/API.md) — every route mounted under `/api/v1`
- [`docs/DEVELOPMENT.md`](../docs/DEVELOPMENT.md) — day-to-day workflow, full-stack compose, conventions
- [`docs/TESTING.md`](../docs/TESTING.md) — test suite structure, markers, and CI wiring
- [`CLAUDE.md`](CLAUDE.md) — component-scoped agent guidance with deeper gotchas (adapter/task registration, prompt versioning, runtime settings, per-feature state machines)
