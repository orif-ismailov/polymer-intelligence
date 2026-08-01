<!-- generated-by: gsd-doc-writer -->
# Architecture

Polymer Intelligence is a market-intelligence platform for Uzbekistan's domestic polymer
market. A set of isolated collectors pull market events (UZEX exchange offers/contracts/deals,
CBU FX rates, e-procurement tenders, Telegram channels, ad-hoc HTML/RSS/LLM-scraped pages) into
an immutable raw store, a parsing layer (rule-based synonym matching or LLM extraction)
normalizes them into a single `signals` stream, and that stream feeds an internal staff
dashboard, a Telegram Web App / Mini App, and a Telegram bot/channel. On top of that signal
core the platform also runs a two-sided B2B marketplace (buyer purchase requests + per-offer
inquiries, seller offers, RFQs to manufacturers), an AI-classified News Engine (daily/evening
digest reports + breaking-news alerts), a company-verification and client-cabinet track
(phone-OTP accounts, E-IMZO digital-signature company confirmation), and a Deal Lifecycle
track (contracts, escrow payments, chemical-compliance licensing, lab sample verification,
government-registry evidence). The guiding invariant across every part of the system: **no
single source or integration can take the others down** — collectors are isolated, raw data is
never mutated, and every external provider degrades gracefully instead of blocking the core.

This document describes the architecture as it stands in code. For exhaustive table-by-table
schema detail, see [`docs/polymer-intelligence-db-architecture.md`](polymer-intelligence-db-architecture.md).
Each component also has its own scoped `CLAUDE.md` (`backend/CLAUDE.md`, `dashboard/CLAUDE.md`,
`webapp/CLAUDE.md`, `portal/CLAUDE.md`, `telegram/CLAUDE.md`, `userbot/CLAUDE.md`,
`deploy/CLAUDE.md`) with directory-local commands and gotchas.

## Component overview

```
                           ┌─────────────────────────────────────────────┐
                           │              Data sources                    │
                           │  UZEX exchange · CBU FX · xarid.uzex tenders │
                           │  Telegram channels · RSS · HTML/LLM pages    │
                           └───────────────────┬───────────────────────────┘
                                                │ Celery beat (cron)
                                                ▼
                     ┌──────────────────────────────────────────────┐
                     │   backend/app/ingest/*  (SourceAdapter impls) │
                     └───────────────────┬────────────────────────────┘
                                          │ save_raw_items() — INSERT ... ON CONFLICT DO NOTHING
                                          ▼
                               ┌───────────────────┐
                               │   raw_items (immutable)  │
                               └─────────┬─────────────┘
                                         │ Celery parse tasks
                        ┌────────────────┼────────────────────┐
                        ▼                ▼                    ▼
                 rule-based match   parsing/extractor.py  parsing/news_extractor.py
                 (synonym dict)     (LLM: trade signals)  (LLM: news classification)
                        └────────────────┼────────────────────┘
                                         ▼
                                  ┌────────────┐
                                  │  signals   │◄── v_live_feed / SSE stream
                                  └─────┬──────┘
                 ┌───────────────────────┼──────────────────────────┐
                 ▼                       ▼                          ▼
         dashboard (Next.js)      webapp (Vite Mini App)     telegram bot/channel
         internal staff feed,     marketplace, news reader,  alerts, report digests,
         moderation, admin        request wizard             inline moderation

   Marketplace / sourcing:  buyer requests + inquiries, seller offers  ──┐
   News Engine:             RSS→classify→dedup→draft report→approve→publish │
   Company verification:    phone-OTP accounts, E-IMZO signature,        ├─ portal (Vite SSR)
                             staff verification queue                    │  client cabinet +
   Deal Lifecycle:          contracts (E-IMZO e-sign), escrow payments,  │  public storefront
                             chemical compliance, lab sample verification,│  (cabinet.ai-imex.com)
                             government-registry evidence               ─┘
```

## Data flow: ingest → raw_items → signals

1. **Source adapters** (`backend/app/ingest/<type>/`) each implement the `SourceAdapter`
   Protocol declared in `backend/app/ingest/base.py` — `async fetch(source) -> list[RawItemDraft]`
   and `async test(config) -> TestResult` (capped at 10 sample rows; backs the dashboard's
   "Test" button on the no-code add-source wizard). Adapter directories on disk: `uzex/`
   (`uzex_offers`, `uzex_contracts`, `uzex_deals`), `cbu_rates/`, `xarid/` (`xarid_tenders` —
   buy-side demand from the `xarid.uzex.uz` e-procurement JSON API), and the no-code adapters
   `html_table/`, `llm_page/`, `rss/`, `telegram_channel/` (built through the dashboard's
   add-source wizard rather than shipped as code). RSS sources tagged `content_kind="news"`
   feed the News Engine instead of the trade-signal pipeline.
2. Adapters **self-register at import time** into `backend/app/ingest/registry.py`
   (`register_adapter` / `get_adapter` / `list_adapters`, a module-level `dict[str, SourceAdapter]`).
   Registration only happens in the process that imports the adapter module, so every adapter is
   imported in both `backend/app/main.py` (API process — the dashboard "Test" button and
   `GET /admin/source-types`) and `backend/app/tasks/ingest.py` (worker process). A new adapter
   must be imported in both places or the worker rejects it as "No adapter registered."
3. Celery `ingest`-queue tasks call `adapter.fetch()` and persist the drafts through
   `backend/app/services/raw_pipeline.py`'s `save_raw_items()`, which inserts into the
   **immutable** `raw_items` table with `INSERT ... ON CONFLICT (source_id, content_hash) DO
   NOTHING`. The dedup key is `sha256(source_id + external_id + normalized_content)`
   (`compute_content_hash`). Existing rows are never mutated — a re-parse (new prompt, fixed
   scraper) can always replay from the same raw data.
4. Celery `parse`-queue tasks turn `raw_items` into `signals` (kinds: `buy_request`,
   `sell_offer`, `deal`, `price_quote`, `news`). UZEX rows resolve products through a synonym
   dictionary first; unmatched UZEX rows, Telegram messages, and free-text pages fall through to
   the LLM extractor (`backend/parsing/extractor.py`). News RSS items go through the news
   extractor (`backend/parsing/news_extractor.py`, `parse_news_item`) instead. The resulting
   `signals` rows are what the dashboard live feed (`v_live_feed`) and its Server-Sent Events
   stream surface to staff in near-real time.

## Celery topology

- App factory: `backend/app/tasks/celery_app.py` — a `Celery("polymer_intelligence")` instance
  with an explicit `include=_TASK_MODULES` list (autodiscovery is a no-op in this layout: it
  would look for a nonexistent `app.tasks.tasks` module and silently register zero tasks). Every
  module that defines a task must be added to `_TASK_MODULES`, currently: `ingest`, `ingest_cbu`,
  `ingest_llm_page`, `ingest_html_table`, `ingest_rss`, `parse`, `parse_telegram`, `notify`,
  `userbot_health`, `nightly_catchup`, `rescore`, `reports`, `events`, `verification`,
  `contracts`, `deals`, `payments`, `rfq_push`, `portal_notify`.
- **Five queues**: `ingest`, `parse`, `notify`, `default`, `verify`. `verify` isolates company
  verification and other external-provider work (bank/E-IMZO/gov-registry calls) so a slow or
  dead provider cannot starve the signal pipelines. The queue set must stay in sync with the
  compose `-Q ingest,parse,notify,default,verify` flag in both `deploy/docker-compose.yml` and
  `deploy/docker-compose.dev.yml`, and with `task_routes` in `celery_app.py`.
- **Reliability**: `task_serializer`/`result_serializer`/`accept_content` are JSON-only (refuses
  pickle); `task_acks_late=True` + `worker_prefetch_multiplier=1` so a crashed worker re-queues
  in-flight work rather than dropping it.
- **Beat schedule** (`backend/app/tasks/schedule.py`, `BEAT_SCHEDULE`, Asia/Tashkent timezone):
  the domain-event outbox dispatcher runs every 15 s; `uzex_fetch_offers` every 15 min during
  business hours (Mon–Fri 09:00–18:00), `uzex_fetch_contracts`/`uzex_fetch_deals` hourly,
  `xarid_fetch_tenders` every 30 min, `fetch_cbu_rates` daily at 07:00, `html_table_fetch` hourly
  at :15, `llm_page_fetch` hourly at :30, `news_fetch_dispatch` every minute (only enqueues
  `rss_fetch` once the operator-tunable `news_refresh_interval_minutes` has elapsed),
  `check_source_health`/`check_userbot_health` every 5 min, `nightly_llm_catchup` daily at 02:00
  UTC, `generate_daily_report` at 08:00 and `generate_evening_report` at 18:00 Tashkent,
  `publish_breaking_news` every 10 min, `prune_portal_notifications` daily at 03:30 UTC,
  `sweep_provider_events` (escrow inbox safety net) every 5 min, `reconcile_escrow_payments`
  every 30 min on the `verify` queue, and `verify_contract_integrity`/`expire_stale_contracts`
  daily at 03:00/04:00 UTC.
- The **userbot is a separate long-lived process** (`userbot/main.py`), not a Celery task. It
  writes a Redis heartbeat that `check_userbot_health` monitors, raising a deduped admin alert
  after 5 minutes of silence.

## LLM extraction

- `backend/parsing/extractor.py` (trade signals) and `backend/parsing/news_extractor.py` (news
  classification) use the `instructor` library in `Mode.TOOLS` over the Anthropic SDK for forced
  structured output. Clients are module-level singletons constructed at import time; tests patch
  `parsing.extractor._client` so no network call happens in CI.
- Prompts live under `backend/parsing/prompts/` and are **versioned and immutable** — changing a
  prompt means adding `prompts/<family>_v{N+1}.md` and bumping the pin, journaled per-run in
  `parse_runs.prompt_version`. Families present on disk: `extract_v1.md`, `news_extract_v1/v2/v3.md`,
  `report_v1`–`v6.md`, `analyze_request_v1.md`, `substance_match_v1.md`. The `extract` and
  `analyze_request` pins are set by env vars (`LLM_PROMPT_VERSION`,
  `REQUEST_AI_ANALYSIS_PROMPT_VERSION`); `report` by `REPORT_PROMPT_VERSION`; `news_extract` is
  selected at **runtime** via the `news_prompt_version` app-setting so it can change from the
  dashboard without a deploy.
- Two model tiers: report generation uses the higher-quality `LLM_REPORT_MODEL`; per-item
  extraction, news classification, and request analysis use the cheaper `LLM_EXTRACT_MODEL`.
- A daily token budget (`LLM_DAILY_TOKEN_LIMIT`, `backend/parsing/budget.py`) gates every LLM
  call. On exhaustion, items are marked `budget_deferred` and reprocessed by the
  `nightly_llm_catchup` beat task after the UTC midnight reset; meanwhile a rule-based fallback
  (`backend/parsing/fallback.py`) degrades gracefully instead of blocking the pipeline.
- Extraction accuracy is guarded by golden/eval tests under `backend/tests/parsing/` (golden
  fixtures plus `eval_config.py`/`eval_metrics.py`/`golden_loader.py`), driven by the
  `backend/parsing/eval_cli.py` CLI — the runner lives with the parsing package, not the tests.

## Data model

SQLAlchemy 2 ORM models live in `backend/app/models/`. `models/__init__.py` imports every module
in FK order so `Base.metadata` is complete — Alembic's `env.py` depends on this, and any new
model must be added there. The migration chain runs `backend/alembic/versions/0001` through
`0034`, spanning the original signal/marketplace/sourcing/reports core (`0001`–`0016`), company
verification and the portal (`0017`–`0022`), the Deal Lifecycle track — contracts, deals,
escrow, chemical compliance, lab/sample verification, government-registry evidence
(`0021`, `0023`–`0029`) — and the manufacturers directory / company-profile fields
(`0030`–`0034`). See [`docs/polymer-intelligence-db-architecture.md`](polymer-intelligence-db-architecture.md)
for the table-by-table design; this doc groups the model files by bounded context instead:

| Domain | Model file(s) | Role |
|---|---|---|
| Signal core | `sources.py`, `signals.py`, `reference.py`, `counterparties.py`, `prices.py` | `raw_items`/`Source`/`ParseRun`, the normalized `Signal` stream, product/synonym reference data, counterparty resolution, derived price points. |
| Requests & alerts | `requests.py`, `alerts.py` | Client purchase requests (Telegram Web App submissions) and the alert-rule/delivery engine. |
| Marketplace & sourcing | `marketplace.py`, `sourcing.py` | Seller offers, offer requests/favorites, RFQ push log; broker-side inventory/partner-supplier tracking. |
| News Engine | `reports.py`, `app_settings.py` | Draft/pending/approved/published `Report` rows and the operator-editable runtime-settings table. |
| Company verification & portal | `accounts.py`, `companies.py`, `verification.py`, `events.py`, `notifications.py` | Phone-OTP `UserAccount`s, `Company`/`CompanyMember`/business roles, the verification case/check/document state machine, the transactional-outbox `DomainEvent`, portal notifications. |
| E-IMZO & integrations | `eimzo.py`, `integration.py` | Signature evidence + person-data captured from the UNICON e-imzo-server sidecar, and a generic external-call log. |
| Contracts | `contracts.py` | `ContractTemplate` / `Contract` / `ContractSignature` — two verified companies e-signing a contract. |
| Deal Lifecycle | `deals.py`, `payments.py`, `registry.py` | `Deal` + status history/messages/documents, RFQ responses; `EscrowPayment`/`ProviderEvent` (bank callback rail); append-only `RegistrySnapshot` government-registry evidence. |
| Chemical compliance | `compliance.py` | `Substance` reference data, `CompanyLicense`, AI-suggested substance matches. |
| Labs & samples | `lab.py` | `LabPartner`/`LabOrder` (manual analysis workflow) and the two-party `SampleRequest` machine. |
| Manufacturers directory | `manufacturers.py` | Factory RFQ threads/documents/messages for the manufacturer-facing directory. |
| Staff | `staff.py` | `StaffUser` + `AuditLog`. |

Domain enums (`app/models/enums.py`) are all declared `enum.StrEnum` (47 classes). ENUM *values*
are verbatim from the locked DDL and must not change without a migration.

> **Stale rationale warning.** The `UP042` ignore in `backend/pyproject.toml` — and the matching
> note in the root `CLAUDE.md` — still claim these enums are `(str, Enum)` and instruct
> contributors not to switch to `StrEnum`. The code no longer matches: the migration to
> `enum.StrEnum` already happened, which means `str(member)` and f-string output now yield
> `"news"` rather than `"SignalKind.NEWS"`. Treat that guidance as obsolete and confirm the
> intended string behaviour before relying on either form.

## API surface & auth

All routes are mounted under `/api/v1` in `create_app()` (`backend/app/main.py`), spread across
the routers in `backend/app/api/` (~30 top-level router modules) plus two sub-packages:
`app/api/webapp/` (the Telegram Web App/Mini App surface — auth, requests, market, seller,
news, reference, files, `me`) and `app/api/portal/` (the client-cabinet surface — auth,
companies, offers, market, inquiries, requests, notifications, contracts, eimzo, deals,
compliance, lab, samples, manufacturers, substances, reference, news). `app/api/public.py`
mounts a third, deliberately **unauthenticated** surface (`/api/v1/public/...`) — the
server-rendered marketplace storefront (offer catalog, the four company directories, category
tiles, price rail, published news, sitemap). It reuses the same service-layer queries as the
cabinet/Mini App (`offer_service`, `directory_service`, `public_market_service`) rather than its
own visibility rules, and its Pydantic schemas (`app/schemas/public.py`) intentionally drop
seller contact details.

- **Staff auth**: HS256 JWT access tokens (short-lived) plus a refresh cookie. Role guards
  (`require_admin`, `require_analyst_or_admin`, `require_role(*roles)`) live in
  `backend/app/api/deps.py`.
- **Portal auth**: phone-OTP `UserAccount`s with a separate JWT audience (`type=portal_access` /
  `portal_refresh` claims, not a jose `aud` claim), so a staff token can never be replayed
  against a portal endpoint.
- **Telegram Web App auth**: `X-Telegram-Init-Data` HMAC verification with a TTL
  (`TELEGRAM_INIT_DATA_TTL_SECONDS`).
- **Escrow webhook auth**: `POST /api/v1/webhooks/escrow/{provider}` (`app/api/webhooks_escrow.py`)
  authenticates via a shared secret in `X-Escrow-Token`, not a JWT, and is excluded from the
  OpenAPI schema.
- CORS origins come from `CORS_ALLOWED_ORIGINS` — an explicit list, never a wildcard (wildcard +
  credentials is both insecure and non-functional).
- `/docs`, `/redoc`, `/openapi.json` are only mounted when `settings.DEBUG` is true.

## Bounded contexts beyond the signal core

- **Marketplace & sourcing** — buyers submit purchase requests and per-offer inquiries and
  sellers publish offers through the Telegram Web App and the portal; staff moderate from the
  dashboard (`/moderation`, `/offer-requests`) and via Telegram inline callbacks
  (`telegram/handlers/moderation.py`). Services: `offer_service`, `offer_request_service`,
  `sourcing_service`, `request_service`. Submitted buyer requests can get an optional LLM
  match/demand/recommendation analysis (`request_analysis_service`, gated by
  `REQUEST_AI_ANALYSIS_ENABLED`).
- **News Engine & reports** — enabled RSS sources tagged `content_kind="news"` are fetched by
  `rss_fetch` and classified into `news` signals by `parse_news_item`; `news_dedup` clusters
  near-duplicate stories across sources. `generate_daily_report`/`generate_evening_report` build
  a draft `Report` (lifecycle `draft → pending_approval → approved → published`);
  staff approve/publish from `/admin/reports` unless the `report_auto_publish` runtime setting is
  on. `publish_report_to_channel` and `publish_breaking_news` post to `NEWS_CHANNEL_ID` via the
  `telegram.bot` client; rendering lives in `report_service`, not the `telegram/` package.
- **Company verification & portal** — phone-OTP `user_accounts`, company registration, and a
  staff-run verification case/check queue (`verification_service`, `verification_checks`,
  `admin_verification.py`). Domain events flow through a transactional outbox
  (`event_service`/`event_types`, dispatched every 15 s by `app.tasks.events.dispatch_domain_events`).
- **E-IMZO digital signature** — national O'zDSt PKCS#7 signature verification is delegated to
  the UNICON `eimzo-server` Java sidecar (stock crypto libraries cannot verify it); the client
  gateway is `backend/app/integrations/eimzo/`, orchestrated by `eimzo_service` (challenge/verify
  → identity lock + evidence). Profile-gated in compose (`profiles: ["eimzo"]`) — absent, the
  gateway's circuit breaker opens and the API returns 503 while the manual verification path
  stays usable.
- **Contracts** — `contract_service` runs the contract state machine and E-IMZO sign step;
  `contract_render` produces the PDF via WeasyPrint. Two verified companies e-sign a contract
  through `app/api/portal/contracts.py`.
- **Deal Lifecycle** (contracts' successor track) — `Deal` + status history/messages/documents
  and manufacturer RFQ responses; `EscrowPayment`/`ProviderEvent` implement a deliberately
  one-directional bank-callback rail (`backend/app/integrations/escrow/` — `client` outbound,
  `events` inbound with a per-provider mapper registry); chemical compliance
  (`offer_compliance_service`, `substances`/`CompanyLicense`) gates non-compliant offers as
  `draft` until required documents exist; lab/sample verification (`lab_service`,
  `sample_service`) runs a manual partner-lab analysis workflow; government-registry evidence
  (`registry_service`) writes append-only `RegistrySnapshot` rows from either a live registry API
  or a staff-transcribed manual check.
- **Runtime settings** — a small set of operator-editable knobs (`news_ai_enabled`,
  `report_auto_publish`, `escrow_mode`, `gov_registry_mode`, `dangerous_check_enforced`, and
  others) lives in the `app_settings` table (`settings_service.py`), editable from the dashboard
  admin panel — distinct from the immutable env/`config.py` contract.

## Frontends

Four separate frontends, each with its own scoped `CLAUDE.md`:

| App | Stack | Purpose | Served at |
|---|---|---|---|
| `dashboard/` | Next.js 16 (App Router), React 18, TanStack Query, Tailwind, shadcn, `app/[locale]/` + `next-intl` | Internal team dashboard: live signal feed, moderation, admin (users/products/settings/verification/contracts/escrow/substances/licenses/lab), news/reports, sourcing/partners/inventory/intel. | `admin.ai-imex.com` |
| `webapp/` | React 18 + Vite, react-router, i18next, zustand | Telegram Mini App: marketplace (buyer inquiries / seller offers), news reader, request-submission wizard. Also runs standalone in a plain browser. | `ai-imex.com` (static bundle at the site root) |
| `portal/` | React 18 + Vite (SSR via a small Express `server.js`), react-router v7, TanStack Query, zustand, i18next, Feature-Sliced Design | Client cabinet (phone-OTP accounts, company verification, offer publishing, contracts, deals, compliance, lab/samples, manufacturers) **and** the public, server-rendered marketplace storefront (`/`, `/market`, the four company directories, `/prices`, `/news`) for SEO crawlability. Public routes render to HTML (`entry-server.tsx`); everything behind login ships as an app shell and renders client-side (`entry-client.tsx`), because the access token lives in memory and the refresh cookie is scoped to `/api/v1/portal` — the SSR process has no session to render a cabinet page from. | `cabinet.ai-imex.com` |
| `telegram/` (bot) | aiogram 3 | Bot webhook (served inside the `api` container, no separate bot process) + message templates; inline moderation callbacks. | — |

`userbot/` (Telethon, MTProto) is a fifth, non-UI long-lived process that monitors Telegram
channels and writes into `raw_items` via the same immutable dedup path as the other adapters.
`workers/uzex_backfill/` is a standalone crawler with its own Postgres schema, entrypoint, and
process (systemd/tmux) — it never imports app code and is not part of the Celery topology.

### Routing (nginx)

`deploy/nginx/` holds the reverse-proxy config; only `nginx` publishes ports in the compose
stack (everything else is internal-only). Four host vhosts route by `Host` header
(`deploy/nginx/nginx.behind-proxy.conf`):

- `api.ai-imex.com` → `api:8000` directly.
- `admin.ai-imex.com` → `/api/` to `api:8000`, everything else to `dashboard:3000`.
- `ai-imex.com` (+`www`) → `/api/` to `api:8000`, everything else served from the static
  `webapp_static` volume (populated by `make webapp-bundle`).
- `cabinet.ai-imex.com` → `/api/` to `api:8000`, everything else proxied to `portal:3000` (the
  portal's own Express SSR process — no longer a static bundle/volume).

<!-- VERIFY: production TLS termination happens on a host-level nginx in front of this
docker-compose stack (behind-proxy topology) — confirm against the live deployment before
treating deploy/nginx/nginx.conf's self-TLS variant as what actually runs in prod. -->
