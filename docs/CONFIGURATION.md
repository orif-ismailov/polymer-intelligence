<!-- generated-by: gsd-doc-writer -->
# Configuration

Polymer Intelligence has two distinct configuration layers, and they are not
interchangeable:

1. **The env contract** — immutable per-deployment settings read once at process
   startup by `backend/app/core/config.py` (`Settings`, a Pydantic `BaseSettings`
   subclass, exposed as the single module-level `settings` instance). This covers
   secrets, infrastructure endpoints, and feature toggles that only make sense
   fixed for the lifetime of a container.
2. **Runtime settings** (`app_settings` table, `backend/app/services/settings_service.py`)
   — a small set of operator-editable knobs that staff can flip from the dashboard
   admin panel (`GET`/`PUT /api/v1/admin/settings`) without a redeploy. These are
   distinct from the env contract and documented separately below.

The frontend apps (`portal/`, `dashboard/`, `webapp/`) are almost entirely
env-var-free: they call the API through a relative `/api/v1` base and rely on
nginx (prod) or a dev proxy (local) for same-origin routing, so there is no
`VITE_*`/`NEXT_PUBLIC_*` contract to document beyond a couple of dev-only/
server-runtime exceptions noted in their own section.

> **Documentation gap found:** `deploy/.env.example` is the repository's
> authoritative, tracked env contract, but three groups of variables that exist
> in `Settings` are **not yet appended to it** — `deploy/CLAUDE.md` records this
> explicitly as a known gap (local tooling denies programmatic edits to `.env*`
> files, so it has to be done by hand): the three E-IMZO variables
> (`EIMZO_SERVER_URL`, `EIMZO_CHALLENGE_TTL_SECONDS`, `EIMZO_STUB`), the escrow
> webhook secret (`ESCROW_WEBHOOK_SECRET`), and the dev-only fixed OTP
> (`OTP_DEV_CODE`). Treat `Settings` (`backend/app/core/config.py`) as the source
> of truth until that file is updated. <!-- VERIFY: confirm deploy/.env.example has been updated to include EIMZO_*, ESCROW_WEBHOOK_SECRET, and OTP_DEV_CODE since this doc was generated -->

## Environment variables

All variables below are declared as fields on `Settings` in
`backend/app/core/config.py`. **Required** means the field has no default —
`Settings()` raises at import time (application startup) if it is missing, so a
misconfigured deployment fails fast rather than misbehaving at first use.
Everything else is **Optional** and falls back to the listed default.

### Database & cache

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | SQLAlchemy connection string (e.g. `postgresql+psycopg://user:pass@host:5432/db`). |
| `REDIS_URL` | Yes | — | Redis connection string. Backs Celery broker/result, OTP storage, E-IMZO challenges, feed SSE bus, userbot heartbeat. |

### Anthropic / LLM

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key used by all LLM extraction/report/analysis clients. |
| `LLM_EXTRACT_MODEL` | No | `claude-haiku-4-5` | Model used for per-item trade-signal extraction and news classification. |
| `LLM_REPORT_MODEL` | No | `claude-sonnet-4-5` | Higher-quality model used for daily/evening report digest generation. |
| `LLM_DAILY_TOKEN_LIMIT` | No | `500000` | Daily token budget gating all LLM calls (`parsing/budget.py`). On exhaustion, items are marked `budget_deferred` and reprocessed by the nightly catch-up task after the UTC midnight reset. |
| `LLM_PROMPT_VERSION` | No | `v1` | Pinned version of the trade-signal extraction prompt family (`parsing/prompts/extract_vN.md`). Journaled to `parse_runs.prompt_version` for replay. |
| `REPORT_PROMPT_VERSION` | No | `v6` | Pinned version of the daily/evening report prompt family (`parsing/prompts/report_vN.md`). |
| `UZEX_LLM_FALLBACK_ENABLED` | No | `false` | When true, UZEX rows the rule-based synonym dictionary cannot recognize are routed through the LLM extractor (like Telegram) instead of being marked irrelevant. Off by default — spends Anthropic tokens per unrecognized row, budget-gated. |
| `REQUEST_AI_ANALYSIS_ENABLED` | No | `true` | Enables LLM match/demand/recommendation analysis on submitted buyer requests, stamped into `requests.ai`. |
| `REQUEST_NOTIFY_CHAT_ID` | No | `None` | Telegram chat/group id (numeric, e.g. `-1001234567890`) notified for each new buyer request. Blank/unset disables notification. |
| `NOTIFY_TOPIC_BUYERS` | No | `None` | Forum-topic (`message_thread_id`) within `REQUEST_NOTIFY_CHAT_ID` for buyer-side notifications (new requests, offer inquiries). Falls back to the group's General topic if unset or invalid/closed. |
| `NOTIFY_TOPIC_SELLERS` | No | `None` | Forum-topic within `REQUEST_NOTIFY_CHAT_ID` for seller-side notifications (new/edited offers). |
| `REQUEST_AI_ANALYSIS_MODEL` | No | `claude-haiku-4-5` | Model used for buyer-request AI analysis. |
| `REQUEST_AI_ANALYSIS_PROMPT_VERSION` | No | `v1` | Pinned version of the `analyze_request` prompt family. |
| `REQUEST_AI_TOKEN_ESTIMATE` | No | `1500` | Conservative per-request token reservation used by the budget guard. |

### Telegram bot

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | Yes | — | Telegram Bot API token. |
| `WEBHOOK_SECRET` | Yes | — | Secret used to validate the Telegram webhook request. |
| `BOT_USERNAME` | No | `""` (empty) | Public bot `@handle` (without the leading `@`). Needed by the browser Telegram Login Widget so the webapp can authenticate visitors opening it outside Telegram. Delivered to the static bundle at runtime via `GET /webapp/auth/config`. Empty disables browser login. The bot's domain must also be registered via BotFather `/setdomain`. |
| `CLIENT_SESSION_TTL_SECONDS` | No | `2592000` (30 days) | Lifetime of the browser client-session cookie issued after a successful Login Widget authentication. No refresh flow — low-privilege client sessions re-auth via the widget on expiry. |

### Telegram userbot

| Variable | Required | Default | Description |
|---|---|---|---|
| `TG_API_ID` | Yes | — | Telegram API id (from https://my.telegram.org). |
| `TG_API_HASH` | Yes | — | Telegram API hash. |
| `TG_SESSION_STRING` | No | `""` (empty) | Session string generated once locally via the interactive `StringSession` login flow (`userbot/session.py`). Stored in `.env`, never committed. Empty lets the API/worker/beat services start; the userbot process itself raises a clear error at startup if empty. |
| `USERBOT_CHANNEL_REREAD_SECONDS` | No | `600` | How often the userbot re-reads the enabled Telegram channel list. |
| `USERBOT_HEARTBEAT_SECONDS` | No | `60` | How often the userbot writes its Redis heartbeat. The `check_userbot_health` beat task alerts admins after >5 min of silence. |

### Auth

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET` | Yes | — | HS256 signing secret for staff JWT auth. **Validated at startup: must be ≥32 characters** or `Settings()` raises. |

### Company verification & portal (R1)

| Variable | Required | Default | Description |
|---|---|---|---|
| `VERIFICATION_ENC_KEY` | Yes | — | Fernet key (urlsafe base64) that encrypts company bank account numbers and PINFL at the app layer. **Validated at startup: must be ≥32 characters** or `Settings()` raises. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `SMS_PROVIDER` | No | `console` | Phone-OTP SMS driver. `console` logs the code at INFO level (dev/CI). `eskiz` sends real SMS via Eskiz.uz and requires `ESKIZ_EMAIL`/`ESKIZ_PASSWORD`. |
| `ESKIZ_EMAIL` | Conditional | `""` | Eskiz.uz account email. **Required when `SMS_PROVIDER=eskiz`** — `Settings()` raises at startup if `SMS_PROVIDER=eskiz` and this or `ESKIZ_PASSWORD` is missing. |
| `ESKIZ_PASSWORD` | Conditional | `""` | Eskiz.uz account password. Same requirement as `ESKIZ_EMAIL`. |
| `OTP_DEV_CODE` | No | `""` (empty) | DEV/DEMO ONLY — a fixed OTP code (e.g. `000000`) so a demo login doesn't need the real code fished from a worker log. Honoured **only** when `DEBUG=true` **and** `SMS_PROVIDER=console`. Must be empty or exactly 6 digits, or startup fails. `Settings()` also refuses to boot if this is set alongside a non-`console` `SMS_PROVIDER` — combining a fixed OTP with a real SMS provider is an auth bypass, not a valid config. **Must stay empty in production.** |
| `OTP_TTL_SECONDS` | No | `300` | OTP code lifetime (Redis-backed). |
| `OTP_RESEND_COOLDOWN_SECONDS` | No | `60` | Minimum interval between OTP resend requests. |
| `OTP_MAX_SENDS_PER_DAY` | No | `5` | Per-phone-number daily OTP send cap. |
| `OTP_MAX_VERIFY_ATTEMPTS` | No | `5` | Max verify attempts before an OTP code is invalidated. |
| `PORTAL_SESSION_TTL_DAYS` | No | `30` | Portal refresh-cookie lifetime (days). A short-lived access JWT (`type=portal_access`) rides on top. |
| `VERIFICATION_NOTIFY_CHAT_ID` | No | `None` | Telegram chat/group id notified per submitted verification case. Falls back to `REQUEST_NOTIFY_CHAT_ID` when unset. `None` disables group notification. |

### E-IMZO verification rails (R3)

| Variable | Required | Default | Description |
|---|---|---|---|
| `EIMZO_SERVER_URL` | No | `http://eimzo-server:8080` | Base URL of the UNICON `eimzo-server` sidecar (internal network, no published ports). All PKCS#7 verification of national O'zDSt-algorithm signatures is delegated there — stock crypto libraries cannot verify them. Non-secret; the default matches the compose service name so dev/CI need no override. |
| `EIMZO_CHALLENGE_TTL_SECONDS` | No | `300` | Lifetime of a one-time signing challenge stored in Redis (single-use). |
| `EIMZO_STUB` | No | `false` | DEV/DEMO ONLY — when true, the gateway skips the sidecar and verifies a synthetic PKCS#7 blob produced by a stub CAPIWS bridge, so the onboarding flow is exercisable without the UNICON artifact. **Must be false in production** (real O'zDSt verification requires the sidecar). |

### Escrow provider callbacks (R6 / P7.b)

| Variable | Required | Default | Description |
|---|---|---|---|
| `ESCROW_WEBHOOK_SECRET` | Conditional | `""` (empty) | Shared secret the partner bank sends in the `X-Escrow-Token` header on every callback to `POST /api/v1/webhooks/escrow/{provider}`. Empty by design (not a "secrets have no defaults" violation) — the escrow rail is gated by the `escrow_mode` **runtime** setting, which a startup validator cannot see, so making this mandatory would force every deployment to invent a value even if escrow is never enabled. While empty, the webhook route answers `404` — an unconfigured deployment does not advertise the endpoint. |

### CORS

| Variable | Required | Default | Description |
|---|---|---|---|
| `CORS_ALLOWED_ORIGINS` | No | `["http://localhost:3000"]` | Explicit, non-wildcard list of allowed origins for credentialed CORS requests. Accepts a comma-separated string (e.g. `CORS_ALLOWED_ORIGINS=http://localhost:3000,https://dashboard.example.com`) or a JSON list. **Never defaults to `["*"]`** — wildcard origin with `allow_credentials=True` is both a security misconfiguration and non-functional per the CORS spec. |

### S3 / MinIO file storage

| Variable | Required | Default | Description |
|---|---|---|---|
| `S3_ENDPOINT` | No | `""` (empty) | S3-compatible endpoint URL. Set to `http://minio:9000` under compose, or an external/managed S3 provider's endpoint. |
| `S3_ACCESS_KEY` | Yes | — | S3/MinIO access key. Also used as the MinIO root user in dev/prod compose. |
| `S3_SECRET_KEY` | Yes | — | S3/MinIO secret key. Also used as the MinIO root password in dev/prod compose. |
| `S3_BUCKET` | No | `polymer-files` | Bucket name for uploaded files (verification documents, contract PDFs, lab results, evidence screenshots). Auto-created by the one-shot `minio-init` compose service. |

### Telegram Web App

| Variable | Required | Default | Description |
|---|---|---|---|
| `PUBLIC_WEBAPP_URL` | No | `""` (empty) | Externally reachable Web App base URL (e.g. `ai-imex.com`) used to build status-push deep-link buttons and the WebApp launch button, and to register the Telegram webhook (as a fallback target for `PUBLIC_API_URL`). Empty keeps the test suite green (no live infrastructure needed); the FastAPI lifespan only attempts webhook registration when this is set. <!-- VERIFY: production value of PUBLIC_WEBAPP_URL --> |
| `PUBLIC_API_URL` | No | `""` (empty) | Externally reachable API base URL (e.g. `api.ai-imex.com`) used to register the Telegram webhook. Falls back to `PUBLIC_WEBAPP_URL` when empty (single-domain deployments). <!-- VERIFY: production value of PUBLIC_API_URL --> |
| `NEWS_CHANNEL_ID` | No | `""` (empty) | Telegram news channel id (e.g. `@petroai_news` or a numeric `-100…` chat id) the approved daily/evening report and breaking-news alerts are posted to. Empty makes channel publishing a no-op (dev/test never call Telegram). <!-- VERIFY: production channel id --> |
| `TELEGRAM_INIT_DATA_TTL_SECONDS` | No | `86400` (24h) | TTL for `X-Telegram-Init-Data` HMAC verification — `initData` older than this is rejected as potentially replayed. |

### Ingest HTTP tunables

| Variable | Required | Default | Description |
|---|---|---|---|
| `INGEST_HTTP_TIMEOUT_SECONDS` | No | `30` | HTTP client timeout used by source adapters and Celery ingest tasks. |
| `INGEST_HTTP_RETRIES` | No | `3` | Retry count for ingest HTTP requests. |
| `INGEST_USER_AGENT` | No | `PolymerIntelligence/1.0 (+contact@polymer.example)` | User-Agent header sent by ingest adapters. |
| `INGEST_PER_HOST_DELAY_SECONDS` | No | `2.0` | Minimum delay between requests to the same host (politeness/rate-limit avoidance). |

### Timezone / display

| Variable | Required | Default | Description |
|---|---|---|---|
| `TZ_DISPLAY` | No | `Asia/Tashkent` | IANA timezone used to display timestamps (data is stored in UTC). Validated at startup against `zoneinfo` — an unknown timezone name fails fast. |

### Observability

| Variable | Required | Default | Description |
|---|---|---|---|
| `SENTRY_DSN` | No | `""` (empty) | Sentry DSN for error tracking. Empty disables Sentry reporting. <!-- VERIFY: whether Sentry is actually wired into app startup, and the production DSN --> |

### Runtime

| Variable | Required | Default | Description |
|---|---|---|---|
| `RUN_MIGRATIONS_ON_STARTUP` | No | `false` | When true, the FastAPI lifespan runs `alembic upgrade head` (advisory-locked, `app/entrypoint.py`) on startup, so a fresh `docker compose up` auto-applies the schema. Default `false` so the test suite / CI (which build the app via `TestClient` with no database) never attempt migrations at import/startup. Both compose files instead run migrations as an explicit pre-start step in the `api` service `command` (`python -m app.entrypoint`), so this flag stays `false` even under compose. |
| `DEBUG` | No | `false` | When true, exposes `/docs`, `/redoc`, and `/openapi.json`. **Must be `false` in production** — otherwise the full API schema (attack-surface map) is publicly accessible. Set `DEBUG=true` in `.env` for local development. |

### Validated at startup

A handful of fields are cross-checked by Pydantic validators on `Settings` beyond
type coercion, and violating them prevents the app (and CI) from booting at all:

- `JWT_SECRET` and `VERIFICATION_ENC_KEY` must each be **≥32 characters**.
- `OTP_DEV_CODE` must be empty or **exactly 6 digits**.
- `OTP_DEV_CODE` set alongside `SMS_PROVIDER != console` **fails startup** (a fixed OTP with a real SMS provider is an auth bypass).
- `SMS_PROVIDER=eskiz` **requires** both `ESKIZ_EMAIL` and `ESKIZ_PASSWORD`.
- `TZ_DISPLAY` must be a valid IANA timezone name (validated against `zoneinfo`).
- `CORS_ALLOWED_ORIGINS` is parsed from either a comma-separated string or a JSON
  list, and is never coerced to `["*"]`.

## Where `.env` is read from

- **Dev compose** (`deploy/docker-compose.dev.yml`) and `make` targets read `.env`
  from the **repo root** (`../.env` relative to `deploy/`).
- **Prod compose** (`deploy/docker-compose.yml`) reads `.env` from **one level
  above the repo root** (also `../.env` relative to `deploy/`, but the repo itself
  is expected to be checked out one directory deeper on the host).
- In both cases the real `.env` is gitignored and never committed; only
  `deploy/.env.example` is tracked. `Settings.model_config` also points
  `env_file=".env"` at the current working directory as a fallback for running
  the API directly with `uv run uvicorn app.main:app` from `backend/`.
- `env_file` blocks on every compose service set `required: false`, so static
  `docker compose config` validation (and `make smoke`) succeeds even without a
  real `.env` present — the real contract is enforced by `Settings` failing fast
  at container startup, not by compose.
- Every compose secret is interpolated as `${VAR}` with **no inline default** for
  required fields (`POSTGRES_PASSWORD`, `S3_ACCESS_KEY`/`S3_SECRET_KEY`,
  `TG_API_ID`/`TG_API_HASH`/`TG_SESSION_STRING`), so a missing secret fails at the
  `Settings` layer rather than silently running with a weak value.

## Per-environment overrides

There are no `.env.development` / `.env.production` files in this repository —
"per environment" here means **a different real `.env` file per deployment
target**, not multiple tracked env files:

- **Local dev**: copy `deploy/.env.example` to `.env` at the repo root, fill in
  placeholder secrets, run `docker compose -f deploy/docker-compose.dev.yml up`.
  `docker-compose.dev.yml` supplies safe fallback defaults for a handful of vars
  (e.g. `POSTGRES_PASSWORD:-devpassword`, `S3_ACCESS_KEY:-minioadmin`) so a bare
  `.env` copy still boots.
- **CI** (`.github/workflows/ci.yml`, `backend` job): every `Settings` field with
  no default is supplied as a hardcoded placeholder value directly in the
  workflow's `env:` block (e.g. `JWT_SECRET: ci-jwt-secret-placeholder-32chars!!`)
  so `Settings` never fails to construct, and a Postgres service container backs
  `DATABASE_URL`. No real secret ever appears in CI.
- **Production** and the auto-deploying **dev-server** environment (see
  `deploy/dev-compose.sh` and `deploy/env.dev-server.example`) each keep their own
  untracked `.env` on the host, one level above the repo checkout. The dev-server
  variant additionally overrides `INNER_NGINX_PORT`/`INNER_NGINX_CONF` so it can
  run alongside the production stack on the same host behind different `dev.*`
  vhosts. <!-- VERIFY: exact host paths and current values of the production and dev-server .env files (not readable from the repository) -->

## Runtime settings (`app_settings` table)

A small set of **operator-editable** knobs is stored in the `app_settings` table
and resolved through `backend/app/services/settings_service.py`. These are
**distinct** from the env contract above: they can be changed from the dashboard
admin panel (`GET`/`PUT /api/v1/admin/settings`, see `backend/app/api/admin_settings.py`)
without a redeploy, and each has a code-level default that applies when no row is
stored for that key. Unknown keys fall back to their code default; a `PUT` with an
unrecognized key or an out-of-range/invalid value is rejected with a 400
(`_coerce` in `settings_service.py`).

| Key | Type | Default | Effect |
|---|---|---|---|
| `news_ai_enabled` | bool | `true` | Run the LLM report digest; off falls back to rule-based summaries only. |
| `news_require_approval` | bool | `false` | Hold classified news until an analyst approves it before publishing. |
| `report_auto_publish` | bool | `false` | Auto-publish generated daily/evening reports, skipping manual staff approval. |
| `llm_extract_model` | str | value of `LLM_EXTRACT_MODEL` | Model the news extractor uses. |
| `news_prompt_version` | str | `v3` | News-extraction prompt version (`parsing/prompts/news_extract_vN.md`), selected at runtime rather than pinned by env. |
| `news_refresh_interval_minutes` | int (5–1440) | `60` | Cadence at which the `news_fetch_dispatch` beat task fetches enabled RSS news sources. |
| `verification_auto_approve` | bool | `false` | Auto-approve verification cases once all automated checks pass. |
| `bank_verification_required` | bool | `false` | Require a verified bank account before a company can be approved. |
| `verification_required_for_publish` | bool | `false` | Reserved (Telegram path) — require company verification before publishing offers. |
| `contract_pending_ttl_days` | int (1–365) | `30` | Days a contract may sit awaiting the counterparty/signatures before it expires (consumed by the `expire_stale_contracts` beat task). |
| `escrow_mode` | str (`stub`\|`live`) | `stub` | `stub` = an operator confirms fund movement manually; `live` = the bank adapter rail (requires `ESCROW_WEBHOOK_SECRET` and a live bank integration). |
| `rfq_supplier_push_enabled` | bool | `false` | Notify matching suppliers when a buyer publishes an RFQ. |
| `rfq_supplier_push_top_n` | int (1–100) | `10` | Maximum number of matched suppliers one RFQ may notify. |
| `rfq_supplier_offer_max_age_days` | int (1–730) | `90` | How recent a supplier's listing must be to count as a match for RFQ push. |
| `substance_ai_enabled` | bool | `true` | Offer an AI substance hint on the seller's offer form. |
| `dangerous_check_enforced` | bool | `false` | Block publication of regulated substances lacking required licence/documents. |
| `chem_registry_mode` | str (`stub`\|`live`) | `stub` | `stub` = the app's own `substances` table (no national chemical registry exists yet); `live` = a future external adapter. |
| `gov_registry_mode` | str (`stub`\|`live`) | `stub` | `stub` = manual operator state-registry checks; `live` = the ПЦД government-registry adapter (raises until that integration exists). |

## Config file format

Beyond the env contract and the `app_settings` table, there is **no separate
structured config file format** (no `config.yaml`/`config.json`/`app.config.*`)
in this project — all backend configuration flows through the single `Settings`
class described above.

## Frontend environment variables

The three frontend apps deliberately minimize their own env surface — each calls
the API through a **relative** `/api/v1` base and relies on same-origin routing
(nginx in prod, a Vite/Next dev proxy locally), so there is no `VITE_*` /
`NEXT_PUBLIC_*` contract of API base URLs to keep in sync.

### `portal/` (client cabinet + public marketplace, server-rendered)

The portal is a long-running Node SSR service (`portal/server.js`), not a static
bundle. It reads two **runtime** environment variables (set in
`deploy/docker-compose.yml`'s `portal` service, not baked into the build):

| Variable | Default | Description |
|---|---|---|
| `INTERNAL_API_ORIGIN` | — (set to `http://api:8000` in compose) | Where the SSR render reaches the API. Must stay on the internal Docker network — a render must not leave the network and come back through nginx. |
| `PUBLIC_SITE_ORIGIN` | `""` (empty) | Absolute origin used to build canonical / `og:url` / `sitemap.xml` URLs. Empty derives it per request from the forwarded `Host` header (correct for dev and for a browser-only render). **Should be set explicitly in production** — a canonical that varies by request header is one a crawler cannot trust. <!-- VERIFY: production value of PUBLIC_SITE_ORIGIN --> |

`import.meta.env.DEV` (a Vite built-in, not a custom env var) gates the `/dev/ui`
design-system reference route so it never ships in a production build.

### `dashboard/` (Next.js internal team dashboard)

| Variable | Default | Description |
|---|---|---|
| `BACKEND_ORIGIN` | `http://localhost:8000` | **Dev-only.** Target the Next.js dev server rewrites `/api/*` to (see `next.config.mjs` and `playwright.config.ts`). In production, nginx serves the dashboard and backend same-origin, so no rewrite/env var is involved. |

No `NEXT_PUBLIC_*` variables are read anywhere in `dashboard/app`, `dashboard/lib`,
or `dashboard/components`.

### `webapp/` (Telegram Web App / Mini App)

`webapp/` reads no custom environment variables at all — its Vite config
(`webapp/vite.config.ts`) only proxies `/api` to `http://localhost:8000` in dev,
and the built bundle is served statically by nginx at the root of the public
site. The bot's WebApp launch button URL comes from the backend's
`PUBLIC_WEBAPP_URL` (documented above), not from a frontend build-time variable.
