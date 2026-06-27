# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Polymer Intelligence is a market-intelligence platform for Uzbekistan's domestic
polymer market. It collects market events from many sources, structures them into
a single normalized signal stream, and delivers them to an internal dashboard, a
Telegram Web App, and a Telegram bot/channel. The guiding invariant: **no single
source can take the others down** — collectors are isolated, dedup is immutable,
and degradation is graceful.

The build is feature-complete through Phase 6 (acceptance/handover). Design history,
requirements (`TZ`), and per-phase plans/summaries live under `.planning/` and `docs/`;
read those for the *why* behind a decision before changing load-bearing behavior.

## Monorepo layout

| Path | Stack | Notes |
|------|-------|-------|
| `backend/` | FastAPI + Celery + SQLAlchemy 2, Python 3.12, **uv**-managed | The core. API, ingest adapters, Celery tasks, LLM parsing. |
| `dashboard/` | Next.js 16 (App Router), React 18, TanStack Query, Tailwind, shadcn | Internal team dashboard. |
| `webapp/` | React 18 + Vite, react-router, i18next, zustand | Telegram Web App (client request-submission surface). |
| `telegram/` | aiogram 3 | Bot handlers + webhook + message templates. **Repo-root package**, not inside `backend/` — mounted read-only into containers. |
| `userbot/` | Telethon (MTProto) | Long-lived process monitoring Telegram channels. **Repo-root package**, separate from Celery worker/beat. |
| `deploy/` | docker-compose, nginx, backup | `docker-compose.yml` (prod), `docker-compose.dev.yml` (dev). |
| `docs/` | — | Dev spec, DB architecture, deployment guide, backup/restore runbook, RU admin guide, extraction schema. |
| `.planning/` | — | Phase plans, roadmap, requirements, design decisions. Not shipped code. |

## Commands

All backend commands run **from `backend/`** and use `uv`:

```bash
cd backend
uv sync --frozen --extra dev        # install exact locked deps (uv.lock is authoritative)

# CI gates (must pass — see .github/workflows/ci.yml):
ruff check .                         # lint
mypy app/services --ignore-missing-imports   # type-check (scoped to services/ + schemas/)
mypy app/schemas  --ignore-missing-imports
pytest tests/ -q                     # full backend suite

# Single test / file / pattern:
pytest tests/test_feed_api.py -q
pytest tests/test_feed_api.py::test_name -q
pytest -k "telegram and not accuracy" -q

# Run the API locally (needs DATABASE_URL/REDIS_URL + the required secrets in env):
uv run uvicorn app.main:app --reload
```

Frontend (`dashboard/` and `webapp/` each have their own `package.json`):

```bash
cd dashboard       # or webapp
npm ci
npm run lint       # eslint, --max-warnings 0
npm run typecheck  # tsc --noEmit
npm run e2e        # Playwright
# dashboard only: `npx next typegen` regenerates route types before `tsc` on a clean checkout
```

Full stack:

```bash
docker compose -f deploy/docker-compose.dev.yml up   # postgres, redis, minio, api, worker, beat, userbot, nginx
make smoke           # production-compose smoke test with synthetic data + placeholder env
make webapp-bundle   # build the Telegram Web App into the nginx-served webapp_static volume
```

Note: `make` targets use `docker compose --env-file .env -f deploy/docker-compose.yml` — the
`--env-file .env` is required so Compose interpolates from the repo-root `.env` (not `deploy/.env`).

## Configuration & secrets

- All config flows through `backend/app/core/config.py` (`Settings`, a single module-level
  `settings` instance — import it, never construct `Settings()` again). `deploy/.env.example`
  is the authoritative env contract.
- **Secrets have no defaults** (`JWT_SECRET`, `BOT_TOKEN`, `WEBHOOK_SECRET`, `TG_API_*`,
  `ANTHROPIC_API_KEY`, `S3_*`) — misconfiguration fails fast at startup. No secret literals
  appear in tracked source.
- The real `.env` is gitignored. Dev reads it from the **repo root**; prod compose reads it
  from **one level above the repo root** (`../.env`).
- `RUN_MIGRATIONS_ON_STARTUP` defaults `false` so the TestClient-built app (tests/CI) never
  touches a database. Compose runs migrations as an explicit pre-start step instead.
- `DEBUG=true` exposes `/docs`, `/redoc`, `/openapi.json` (off in prod).

## Backend architecture

### Ingest → raw_items → signals pipeline

1. **Source adapters** (`app/ingest/<type>/adapter.py`) each implement the `SourceAdapter`
   Protocol in `app/ingest/base.py` (`fetch(source) -> list[RawItemDraft]`, `test(config) -> TestResult`).
   Types: `uzex_offers/contracts/deals`, `cbu_rates` (built-in code adapters for seeded sources)
   plus no-code adapters `html_table`, `llm_page`, `rss`, `telegram_channel` (created via the
   dashboard add-source wizard).
2. Adapters **self-register at import time** into the registry (`app/ingest/registry.py`),
   keyed by `type_name`. **Critical gotcha:** registration only happens in the process that
   imports the adapter module. They are imported in BOTH `app/main.py` (so the dashboard
   "Test" button and `GET /admin/source-types` work in the API process) AND `app/tasks/ingest.py`
   (so the worker can resolve them). Adding a new adapter means importing it in both places.
3. Celery `ingest` tasks call `adapter.fetch()` and persist via
   `app/services/raw_pipeline.save_raw_items()`, which inserts into **immutable** `raw_items`
   with `INSERT ... ON CONFLICT (source_id, content_hash) DO NOTHING`. Dedup key =
   `sha256(source_id + external_id + normalized_content)`. Existing rows are never mutated.
4. Celery `parse` tasks turn `raw_items` into `signals`. UZEX rows resolve products via a
   synonym dictionary; Telegram messages (and optionally unrecognized UZEX rows) go through the
   **LLM extractor** (`parsing/extractor.py`). The live feed (`v_live_feed`) and SSE stream
   surface the resulting signals.

### Celery topology

- App factory: `app/tasks/celery_app.py`. Beat schedule: `app/tasks/schedule.py`.
- **Task modules must be listed explicitly** in `_TASK_MODULES` (autodiscover is a no-op here).
  Adding a new task module without listing it = "unregistered task" at dispatch.
- Four queues: `ingest`, `parse`, `notify`, `default` (must match the compose
  `-Q ingest,parse,notify,default` flag). Routing is in `task_routes`.
- JSON-only serialization (refuses pickle); `task_acks_late=True` +
  `worker_prefetch_multiplier=1` so a crashed worker re-queues rather than dropping work.
- The **userbot is a separate long-lived process** (`userbot/main.py`), NOT a Celery task. It
  writes a Redis heartbeat; the `check_userbot_health` beat task raises a deduped admin alert
  on >5 min silence.

### LLM extraction (Phase 5)

- `parsing/extractor.py` uses `instructor` + the Anthropic SDK (`Mode.TOOLS`) for forced
  structured output. Clients are module-level singletons built at import; tests patch
  `parsing.extractor._client` so no network call happens in CI.
- Prompts are **versioned and immutable**: `parsing/prompts/extract_vN.md`. To change a prompt,
  add `extract_v{N+1}.md` and bump `LLM_PROMPT_VERSION` — the version is stored in
  `parse_runs.prompt_version` for replay. Same pattern for the request-analysis prompt.
- A **daily token budget** (`LLM_DAILY_TOKEN_LIMIT`, `parsing/budget.py`) gates LLM calls.
  On exhaustion, items are marked `budget_deferred` and reprocessed by the `nightly_llm_catchup`
  beat task after the UTC midnight reset; meanwhile a rule-based fallback degrades gracefully.
- Extraction accuracy is guarded by golden/eval tests under `tests/parsing/` (`eval_cli.py`,
  golden fixtures). `*.example.json` golden files are committed; real control samples are not.

### Models & migrations

- SQLAlchemy 2 ORM in `app/models/`. `app/models/__init__.py` imports every module in FK order
  so `Base.metadata` is complete — alembic's `env.py` depends on this. Add new models there.
- Domain enums (`app/models/enums.py`) are declared `(str, Enum)` (not `StrEnum`) to match the
  Postgres ENUM types verbatim; `str(member)` / f-string output is relied upon — don't switch to
  `StrEnum` (ruff `UP042` is disabled for this reason).
- Migrations: `backend/alembic/versions/` (`0001`→`0005`). Run `alembic upgrade head` (or let
  `app/entrypoint.py` do it, advisory-locked, idempotent for concurrent workers).
- Reference/seed data: `app/seed/` (`seed_reference`, `seed_staff`, `seed_sources`, `seed_demo`),
  with JSON under `app/seed/data/`. Seeders are idempotent (`ON CONFLICT`).

### API & auth

- All routes mounted under `/api/v1` in the `create_app()` factory (`app/main.py`); routers in
  `app/api/`. The Telegram Web App surface is under `app/api/webapp/`.
- Staff auth: JWT (HS256, `JWT_SECRET` ≥ 32 chars enforced) + refresh cookie. RBAC via
  `require_admin` / `require_analyst_or_admin` / `require_role` factory in `app/api/deps.py`.
- Telegram Web App auth: `X-Telegram-Init-Data` HMAC verification with a TTL
  (`TELEGRAM_INIT_DATA_TTL_SECONDS`).
- CORS origins come from `CORS_ALLOWED_ORIGINS` (explicit, never `*` — wildcard + credentials is
  both insecure and non-functional).

## Frontend notes

- **Dashboard**: Next.js App Router with `app/[locale]/...` and `next-intl` (locales: `ru`/`uz`/`tr`,
  messages in `messages/`). API calls hit the relative `/api/v1` base; in dev, `next.config.mjs`
  rewrites `/api/*` → `BACKEND_ORIGIN` (default `http://localhost:8000`), in prod nginx serves both
  same-origin (no CORS). Live feed uses SSE (`hooks/useSSE.ts`). UI primitives in `components/ui/`
  (shadcn), feature components grouped by domain.
- **Webapp**: Vite + react-router, i18next (`src/i18n/`), zustand for the request-submission wizard
  store. Built and served as a static bundle by nginx at `/webapp/` (see `make webapp-bundle`).

## Conventions

- **Time**: store UTC, display `Asia/Tashkent` (`TZ_DISPLAY`). Time helpers in `app/core/time.py`
  (backend) and `lib/tz.ts` (dashboard).
- **mypy is strict** for `app/services` and `app/schemas` (the CI-gated scope). Business logic
  lives in `app/services/`; keep it typed.
- Dependency versions are deliberately pinned: `uv.lock` is authoritative (`uv sync --frozen`),
  `fastapi`/`starlette` are tightly bounded (route registration is version-sensitive), and
  `ruff==0.15.17` / `mypy==2.1.0` are pinned for a reproducible gate. Don't bump without re-running
  the gates.
- Domain exceptions are named without the `Error` suffix (`InvalidInitData`, `BudgetExceeded`) —
  ruff `N818` is disabled to match this. Follow the convention.
- Languages handled across the stack: Russian (primary), Uzbek, Turkish.

## CI

`.github/workflows/ci.yml` runs five jobs: **backend** (ruff · mypy · pytest against a Postgres
service), **dashboard** (eslint · `next typegen` · tsc), **dashboard-e2e** (Playwright against a
live migrated+seeded API), **webapp** (eslint · tsc), and **build-images** (docker build of the
backend + dashboard images). Deploy to the server runs only on push to `main` after the gates pass.
CI uses placeholder secrets so `Settings` doesn't fail-fast.
