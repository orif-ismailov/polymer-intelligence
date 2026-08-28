# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Polymer Intelligence is a market-intelligence platform for Uzbekistan's domestic
polymer market. It collects market events from many sources, structures them into
a single normalized signal stream, and delivers them to an internal dashboard, a
Telegram Web App, and a Telegram bot/channel. On top of that signal core it also runs
a **two-sided marketplace** (buyers submit purchase requests + per-offer inquiries,
sellers publish offers) and an AI **News Engine** (classified petrochemical news →
approved daily/evening reports + breaking-news alerts). The guiding invariant: **no
single source can take the others down** — collectors are isolated, dedup is immutable,
and degradation is graceful.

The original signal pipeline shipped through Phase 6 (acceptance/handover); later work
added the marketplace/sourcing surface (buyer↔seller inquiries, buyer-request AI analysis)
and the News Engine (Phases 7–8). The **company-verification & portal** track (R1–R3, under
`.planning/company-verification/`) then added the client cabinet (`portal/`), staff
verification, **E-IMZO digital-signature company confirmation** (UNICON `eimzo-server`
sidecar), and the **contracts** bounded context (two verified companies e-sign a contract via
E-IMZO — the seed of the Deal Lifecycle domain). Design history, requirements (`TZ`), and
per-phase plans/summaries live under `.planning/` and `docs/`; read those for the *why* behind
a decision before changing load-bearing behavior.

## Component guides

Each major component has its own scoped `CLAUDE.md` with directory-local commands, layout, and
gotchas. **Read the relevant one before working inside that directory:**

- [`backend/CLAUDE.md`](backend/CLAUDE.md) — FastAPI + Celery + SQLAlchemy core (API, ingest, tasks, LLM parsing).
- [`dashboard/CLAUDE.md`](dashboard/CLAUDE.md) — Next.js internal team dashboard.
- [`webapp/CLAUDE.md`](webapp/CLAUDE.md) — Vite Telegram Web App (client request submission).
- [`portal/CLAUDE.md`](portal/CLAUDE.md) — Vite/React client cabinet (phone-OTP accounts, company verification, offers).
- [`telegram/CLAUDE.md`](telegram/CLAUDE.md) — aiogram 3 bot (webhook + templates).
- [`userbot/CLAUDE.md`](userbot/CLAUDE.md) — Telethon MTProto channel monitor.
- [`deploy/CLAUDE.md`](deploy/CLAUDE.md) — docker-compose, nginx, backup.

## Monorepo layout

| Path | Stack | Notes |
|------|-------|-------|
| `backend/` | FastAPI + Celery + SQLAlchemy 2, Python 3.12, **uv**-managed | The core. API, ingest adapters, Celery tasks, LLM parsing. |
| `dashboard/` | Next.js 16 (App Router), React 18, TanStack Query, Tailwind, shadcn | Internal team dashboard. |
| `webapp/` | React 18 + Vite, react-router, i18next, zustand | Telegram Web App / Mini App: client request submission **+ two-sided marketplace (buyer inquiries / seller offers) + news reader**. Also runs standalone in a plain browser. |
| `portal/` | React 18 + Vite, react-router v7, TanStack Query, zustand, i18next, **Feature-Sliced Design** | Client cabinet (R1): phone-OTP `user_accounts`, company registration + verification, offer publishing. Served at the root of `cabinet.ai-imex.com`. |
| `telegram/` | aiogram 3 | Bot handlers + webhook + message templates. **Repo-root package**, not inside `backend/` — mounted read-only into containers. |
| `userbot/` | Telethon (MTProto) | Long-lived process monitoring Telegram channels. **Repo-root package**, separate from Celery worker/beat. |
| `workers/` | standalone Python | `uzex_backfill/` — isolated crawler that walks the uzex.uz offer-detail ID space into its **own** Postgres tables. No app imports, own DB schema + entrypoint + requirements, own process (systemd/tmux) — **never Celery**. |
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
# type-check — the WHOLE app package. Modules that don't pass yet are named in
# pyproject.toml's burn-down override; that list should only ever shrink.
mypy app --ignore-missing-imports
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
   Types: `uzex_offers/contracts/deals`, `cbu_rates`, `xarid_tenders` (built-in code adapters for
   seeded sources — the last is buy-side demand from the xarid.uzex.uz e-procurement JSON API) plus
   no-code adapters `html_table`, `llm_page`, `rss`, `telegram_channel` (created via the dashboard
   add-source wizard). RSS sources tagged `content_kind="news"` feed the News Engine.
2. Adapters **self-register at import time** into the registry (`app/ingest/registry.py`),
   keyed by `type_name`. **Critical gotcha:** registration only happens in the process that
   imports the adapter module. They are imported in BOTH `app/main.py` (so the dashboard
   "Test" button and `GET /admin/source-types` work in the API process) AND `app/tasks/ingest.py`
   (so the worker can resolve them). Adding a new adapter means importing it in both places.
3. Celery `ingest` tasks call `adapter.fetch()` and persist via
   `app/services/raw_pipeline.save_raw_items()`, which inserts into **immutable** `raw_items`
   with `INSERT ... ON CONFLICT (source_id, content_hash) DO NOTHING`. Dedup key =
   `sha256(source_id + external_id + normalized_content)`. Existing rows are never mutated.
4. Celery `parse` tasks turn `raw_items` into `signals` (kinds: `buy_request`, `sell_offer`,
   `deal`, `price_quote`, `news`). UZEX rows resolve products via a synonym dictionary; Telegram
   messages (and optionally unrecognized UZEX rows) go through the **LLM extractor**
   (`parsing/extractor.py`); news RSS items go through the **news extractor**
   (`parsing/news_extractor.py`) via `parse_news_item`. The live feed (`v_live_feed`) and SSE
   stream surface the resulting signals.

### Celery topology

- App factory: `app/tasks/celery_app.py`. Beat schedule: `app/tasks/schedule.py`.
- **Task modules must be listed explicitly** in `_TASK_MODULES` (autodiscover is a no-op here).
  Adding a new task module without listing it = "unregistered task" at dispatch.
- Five queues: `ingest`, `parse`, `notify`, `default` + `verify` (R1 company
  verification, isolated so a slow provider can't starve the signal pipelines).
  Must match the compose `-Q ingest,parse,notify,default,verify` flag in BOTH
  compose files. Routing is in `task_routes`.
- JSON-only serialization (refuses pickle); `task_acks_late=True` +
  `worker_prefetch_multiplier=1` so a crashed worker re-queues rather than dropping work.
- The **userbot is a separate long-lived process** (`userbot/main.py`), NOT a Celery task. It
  writes a Redis heartbeat; the `check_userbot_health` beat task raises a deduped admin alert
  on >5 min silence.

### LLM extraction & prompts (Phase 5+)

- `parsing/extractor.py` (and `parsing/news_extractor.py`) use `instructor` + the Anthropic SDK
  (`Mode.TOOLS`) for forced structured output. Clients are module-level singletons built at import;
  tests patch `parsing.extractor._client` so no network call happens in CI.
- Prompts are **versioned and immutable**: to change one, add `parsing/prompts/<family>_v{N+1}.md`
  and bump its version pin (journaled in `parse_runs.prompt_version` for replay). Four families:
  `extract_v*` (trade signals, pinned by `LLM_PROMPT_VERSION`, currently **v1**), `news_extract_v*`
  (news classification, **v1–v3**, selected at **runtime** via the `news_prompt_version` app-setting),
  `report_v*` (daily/evening report digest, `REPORT_PROMPT_VERSION`, currently **v6**), and
  `analyze_request_v*` (buyer-request analysis, `REQUEST_AI_ANALYSIS_PROMPT_VERSION`, **v1**).
- Two model tiers: report generation uses the higher-quality `LLM_REPORT_MODEL` (Sonnet); per-item
  extraction/classification and request analysis use the cheaper `LLM_EXTRACT_MODEL` (Haiku).
- A **daily token budget** (`LLM_DAILY_TOKEN_LIMIT`, `parsing/budget.py`) gates all LLM calls.
  On exhaustion, items are marked `budget_deferred` and reprocessed by the `nightly_llm_catchup`
  beat task after the UTC midnight reset; meanwhile a rule-based fallback degrades gracefully.
- Extraction accuracy is guarded by golden/eval tests under `tests/parsing/` (`eval_cli.py`,
  golden fixtures). `*.example.json` golden files are committed; real control samples are not.

### News Engine & reports (Phases 7–8)

- **Ingest → classify:** enabled RSS sources with `content_kind="news"` are fetched by `rss_fetch`
  (dispatched by the `news_fetch_dispatch` beat task at a runtime-tunable cadence,
  `news_refresh_interval_minutes`) and classified into `news` signals by `parsing/news_extractor.py`
  (`parse_news_item`). `app/services/news_dedup.py` clusters near-duplicate stories across sources.
- **Reports:** `generate_daily_report` (08:00) and `generate_evening_report` (18:00 Tashkent) build
  a 3-section brief as a **draft** `Report` row (`app/models/reports.py`), rendered by
  `report_service`. Lifecycle: `draft → pending_approval → approved → published` — human-in-the-loop;
  staff approve/publish from the dashboard (`/admin/reports`) unless the `report_auto_publish`
  app-setting is on.
- **Channel delivery:** the `notify`-queue tasks `publish_report_to_channel` and `publish_breaking_news`
  (every 10 min, high-importance news) post to `NEWS_CHANNEL_ID` via the `telegram.bot` client.
  Rendering (`render_telegram_digest`, `render_breaking_alert`) lives in `report_service`, **not** the
  `telegram/` package. Mini-App news cards read `GET /webapp/news/articles`.

### Runtime settings & marketplace

- **Runtime settings:** a small set of operator-editable knobs lives in the `app_settings` table
  (`settings_service.py`, declared in `_SPECS`) and is editable from the dashboard admin panel —
  **distinct from the immutable env/`config.py` contract**. Keys: `news_ai_enabled`,
  `news_require_approval`, `report_auto_publish`, `llm_extract_model`, `news_prompt_version`,
  `news_refresh_interval_minutes`. Unknown keys fall back to their code default.
- **Marketplace/sourcing:** buyers submit purchase requests + per-offer inquiries and sellers publish
  offers through the Telegram Web App; staff moderate from the dashboard (`/moderation`,
  `/offer-requests`) and Telegram inline callbacks (`telegram/handlers/moderation.py`). Models in
  `app/models/{marketplace,sourcing,requests}.py`; services `offer_service`, `offer_request_service`,
  `sourcing_service`, `request_service`. Submitted buyer requests get an optional LLM
  match/demand/recommendation analysis (`request_analysis_service`, gated by `REQUEST_AI_ANALYSIS_ENABLED`).

### Models & migrations

- SQLAlchemy 2 ORM in `app/models/`. `app/models/__init__.py` imports every module in FK order
  so `Base.metadata` is complete — alembic's `env.py` depends on this. Add new models there.
- Domain enums (`app/models/enums.py`) are declared `(str, Enum)` (not `StrEnum`) to match the
  Postgres ENUM types verbatim; `str(member)` / f-string output is relied upon — don't switch to
  `StrEnum` (ruff `UP042` is disabled for this reason).
- Migrations: `backend/alembic/versions/` (`0001`→`0034`; the chain grew past the original
  Phase-6 `0005` with marketplace/sourcing `0007`–`0013`, `reports`/evening-report `0014`,
  `app_settings` `0015`, source groups `0016`, R1 verification/portal `0017`, R2 portal-parity
  `0018`, market-list index `0019`, R3 E-IMZO rails `0020`, R3 contracts `0021`, then the deal-
  lifecycle track's company logo `0022`, deals `0023`, escrow `0024`, offer sale fields `0025`,
  RFQ push log `0026`, compliance `0027`, lab `0028`, gov registry `0029`, offer product facts
  `0030`, and the manufacturer/logistics/laboratory company profiles `0031`–`0033` plus the
  manufacturers module `0034`). Run `alembic upgrade head` (or let `app/entrypoint.py` do it,
  advisory-locked, idempotent for concurrent workers).
- Reference/seed data: `app/seed/` (`seed_reference`, `seed_staff`, `seed_sources`, `seed_demo`,
  `seed_contract_templates`), with JSON/HTML under `app/seed/data/`. Seeders are idempotent (`ON CONFLICT`).

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

- **Dashboard**: Next.js App Router with `app/[locale]/...` and `next-intl` (locales
  `ru`/`uz`/`tr`/`fa`/`zh`, messages in `messages/`). Authed pages under the `(dashboard)` group span
  the signal side (feed, signals, offers, prices, requests, sources, alerts) **and** the newer surfaces
  (news admin, reports, moderation, offer-requests, sourcing/partners/inventory, intel,
  admin/users + admin/products). API calls hit the relative `/api/v1` base; in dev, `next.config.mjs`
  rewrites `/api/*` → `BACKEND_ORIGIN` (default `http://localhost:8000`), in prod nginx serves both
  same-origin (no CORS). Live feed uses SSE (`hooks/useSSE.ts`). UI primitives in `components/ui/`
  (shadcn), feature components grouped by domain.
- **Webapp**: Vite + react-router, i18next (`src/i18n/`, locales `ru`/`en`/`uz`/`tr`/`fa`/`zh`),
  zustand (request wizard + role stores). Now a full Telegram Mini App surface — marketplace
  (buyer inquiries / seller offers), news reader, and the request-submission wizard — that also runs
  in a plain browser. Built as a static bundle served by nginx at the **root of `ai-imex.com`**
  (see `make webapp-bundle`).

## Conventions

- **Time**: store UTC, display `Asia/Tashkent` (`TZ_DISPLAY`). Time helpers in `app/core/time.py`
  (backend) and `lib/tz.ts` (dashboard).
- **Domain folders**: the backend reorg is **complete**. Every bounded context lives in
  `backend/app/domains/<name>/` (models + schemas + service + routers together) — 20 of them:
  accounts, alerts, companies, compliance, contracts, deals, lab_orders, laboratory, logistics,
  manufacturers, marketplace, news, notifications, pricing, reference, requests, signals,
  sourcing, storefront, verification. What remains in `app/services|schemas|models|api/` is a
  **closed shared kernel**, declared in those packages' `__init__.py` docstrings — "still in
  `app/services/`" means kernel, not unmigrated. Plans and the binding rules (including the
  models-barrel module-import rule) are in `.planning/backend-domain-reorg/`.
- **mypy is strict over all of `app/`.** CI runs `mypy app`, so a new module is type-checked by
  default; the modules that don't pass yet are named in a burn-down override in
  `pyproject.toml`, and that list should only ever shrink. (It replaced a hand-maintained
  list of ~90 file paths that had to be kept in sync across three files, and that silently
  left anything not on it unchecked.)
- Dependency versions are deliberately pinned: `uv.lock` is authoritative (`uv sync --frozen`),
  `fastapi`/`starlette` are tightly bounded (route registration is version-sensitive), and
  `ruff==0.15.17` / `mypy==2.1.0` are pinned for a reproducible gate. Don't bump without re-running
  the gates.
- Domain exceptions are named without the `Error` suffix (`InvalidInitData`, `BudgetExceeded`) —
  ruff `N818` is disabled to match this. Follow the convention.
- Languages handled across the stack: Russian (primary), Uzbek, Turkish, plus Farsi and Chinese in
  the client-facing surfaces (the webapp also ships English). Keep locale files in sync — see each
  component's `CLAUDE.md` for the exact set it ships.

## Verify every change in a real browser

**A green test suite is not evidence that a change works. Drive it in a real browser — through
the `chrome-devtools` MCP server — before saying it does.** Not curl, not a Node/Python script,
not a passing `pytest`/`playwright` run. This applies to every change that a person can reach:
a screen, a form, an API a screen calls.

It is a rule because it keeps paying. Every bug in this list was sitting behind a fully green
suite, and each was visible within a minute of clicking:

- `window.CAPIWS` was assigned by **nothing**, so every user got `module_missing` — R3 contract
  signing had been broken for everyone.
- `signBase64` double-encoded UTF-8: «Поставка» was signed as «ÐÐ¾ÑÑÐ°Ð²ÐºÐ°», so the signature
  covered bytes no verifier could reproduce. Types, tests and curl all passed — ASCII survives it.
- `GET /v1/newoffer/base64` returns raw base64, not JSON, so a working 200 surfaced as
  `didox_unavailable` (the mocked test used a JSON fixture).
- Publishing an offer with an ИКПУ was **impossible** (422 on a field Didox never returns), and
  editing an offer silently ERASED the ИКПУ, because the read schema omitted what the write
  schema took.
- The E-IMZO handshake cached its own REJECTION, so the app insisted «модуль не найден» for the
  life of the page while the module answered raw calls perfectly.
- Dead Tailwind classes (`text-muted`, `border-line` — neither exists) fail **silently**.

How, in practice: `navigate_page` → `take_snapshot` for element uids → `click`/`fill`/`fill_form`
on the real controls; `list_network_requests` + `get_network_request` for what actually went over
the wire; `list_console_messages` for what a screenshot hides. Then confirm the state landed in
Postgres/Redis/S3 — an HTTP 200 is not proof that anything persisted. Finally, say plainly what
was verified in the browser and what is still only unit-tested; never let a script stand in for
the browser check.

**There is no diagnostic exception.** "I'll just probe the provider's API with a script" is the
same rule broken with a better excuse — and it was broken that way on 26–27.08.2026, driving the
whole Didox signing chain from Python. It produced a real signed document that then existed at the
operator and NOWHERE in our product, because the script had gone around the app. A script proves
the PROVIDER's contract and nothing about ours. If a flow cannot be driven from the UI, that gap is
the finding: report it and ask how to unblock it — the answer took one sentence and would have
saved two days.

**Running the stack means all of it**, and a missing piece looks like a broken feature rather than
a missing process. One command starts every piece:

```bash
make dev        # infra containers + migrations + seeds + api + worker + beat + portal + dashboard
make dev-stop   # stop the infra containers it leaves running
```

`scripts/dev.sh` refuses to start on a busy port (otherwise the OLD process keeps answering and you
debug code you are not running), and if any process dies it takes the rest down — a half-stack is
the state that makes a working feature look broken. It does NOT start the userbot (needs real
`TG_API_*`) or the Telegram Web App (`make webapp-bundle`). By hand, if you need the pieces apart:

```bash
docker start pi-pg pi-redis pi-minio          # 5432 / 6379 / 9000
cd backend && uv run uvicorn app.main:app --reload            # :8000
cd backend && uv run celery -A app.tasks.celery_app worker \
    -Q ingest,parse,notify,default,verify                     # REQUIRED
cd backend && uv run celery -A app.tasks.celery_app beat      # REQUIRED
cd portal && npm run dev                                      # :5173
cd dashboard && npm run dev                                   # :3000
```

Without the **worker**, verification checks sit at «Ожидает» forever and the case never reaches
`pending_review`, so «Одобрить» answers "already handled by another member of staff" about a case
nobody touched. Without **beat**, `poll_didox_documents` never runs — and that poller is the only
way we learn a counterparty signed in their own EDI cabinet, since Didox publishes no webhooks.
Both were missing from a stack reported as "fully up" on 27.08.2026.

Note `portal/e2e/*.spec.ts` still runs under `npx playwright test` — that is the test runner, a
different thing from this check.

## CI

`.github/workflows/ci.yml` runs eight jobs: **backend** (ruff · mypy · pytest against a Postgres
service), **dashboard** (eslint · `next typegen` · tsc), **dashboard-e2e** (Playwright against a
live migrated+seeded API), **webapp** (eslint · tsc), **portal** (eslint · tsc · vite build),
**build-images** (builds + pushes four GHCR images — backend, dashboard, webapp, portal — gated on
all four frontend/backend jobs), then **deploy** (push to `main`) and **deploy-dev** (push to
`dev`), which pull those images and re-run the one-shot `webapp-build`/`portal-build` services to
refresh the static bundles. CI uses placeholder secrets so `Settings` doesn't fail-fast.
