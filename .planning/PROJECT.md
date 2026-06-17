# Polymer Intelligence

## What This Is

A market-intelligence platform for Uzbekistan's domestic polymer market. It collects, structures, and delivers market information — UZEX exchange positions, monitored public Telegram channels, official CBU FX rates, and client purchase requests — to three surfaces: an internal Next.js dashboard for the team, a Telegram Web App for clients, and a Telegram bot/channel. It tracks market events, structures them into a single normalized signal stream, and explains price movements by observable factors. It does **not** forecast prices or give trading advice; AI outputs (lead score, urgency, summaries) are advisory and a human makes the final decision.

## Core Value

Every relevant market event — a client request, a UZEX polymer position, a channel signal — lands accurately and quickly in a single normalized stream that the team can see, filter, and act on, with no single data source able to take the others down.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- [x] **REQ-uzex-parser** (FR-1): UZEX offers/quotations/concluded-deals → `signals` on schedule — _Validated in Phase 2 (E2 Ingest Core + UZEX); ≥95% accuracy gate = 100% on 55-position control sample. Live deploy-drill deferred (02-UAT.md)._
- [x] **REQ-fx-rates** (FR-4): Daily CBU rate import; conversion computed on read, original preserved — _Validated in Phase 2 (E2)._
- [x] **REQ-sources-health** (FR-13): Source health view + enable/disable; 3-strike `source_failure` alert with per-source isolation — _Validated in Phase 2 (E2). Live alert-isolation drill deferred (02-UAT.md)._
- [x] **REQ-webapp-auth** (FR-5): Telegram initData auth; first login creates a client — _Validated in Phase 3 (E3 Client Circuit); HMAC verify + get_or_create_client, generic-401, future-token guard. Live deploy-drill deferred (03-UAT.md)._
- [x] **REQ-request-wizard** (FR-6): 4-step Web App request wizard with files; REQ-YYYY-MM-DD-NNNNN number — _Validated in Phase 3 (E3); request_service number gen + status machine, /webapp API, direct MinIO uploads. Live deploy-drill deferred (03-UAT.md)._
- [x] **REQ-my-requests** (FR-7): Client request list + status history; bot push on status change — _Validated in Phase 3 (E3); Мои заявки + detail + Asia/Tashkent timeline; notify task on `notify` queue (≤30 s dispatch proxy PASS). Live deploy-drill deferred (03-UAT.md)._
- [x] **REQ-webapp-i18n** (FR-9): RU/UZ toggle, default from Telegram language_code — _Validated in Phase 3 (E3); react-i18next, 72/72 RU/UZ key parity, toggle persists._
- [x] **REQ-bot-clients** (FR-17): Greeting, Web App button, status notifications to clients — _Validated in Phase 3 (E3); aiogram webhook bot /start greeting + Web App button + notify-queue routing. Live bot drill deferred (03-UAT.md)._
- [x] **REQ-nfr-performance** (partial): Web App bundle ≤300 KB gzip (42.8 KB largest chunk) + SLA proxies (≤10 s readback, ≤30 s notify dispatch) — _Validated in Phase 3 (E3); first-paint-on-3G live measurement deferred (03-UAT.md)._

### Active

<!-- Current milestone: Client Phase 1 (domestic-market MVP). Full list with IDs and acceptance criteria in REQUIREMENTS.md. -->

- [ ] **REQ-live-feed** (FR-10): Unified filterable feed (v_live_feed), SSE/polling refresh
- [ ] **REQ-purchase-requests** (FR-11): Requests table + detail card + actions, all → audit_log (flagship screen)
- [ ] **REQ-price-trends** (FR-12): Price chart per product/market from price_points
- [ ] **REQ-alerts** (FR-14): Alert feed + rules builder + delivery
- [ ] **REQ-roles** (FR-15): admin / analyst / trader / viewer authz
- [ ] **REQ-bot-team** (FR-16): Deliver alerts to DM/group respecting Telegram rate limits
- [ ] **REQ-ai-extraction** (FR-19): LLM structuring per fixed JSON schema; journaled in parse_runs
- [ ] **REQ-lead-scoring** (FR-20): lead_score + HOT/MEDIUM/LOW on signals/requests
- [ ] **REQ-llm-budget** (FR-21): Daily token limit; graceful degradation to rule-based + catch-up
- [ ] **REQ-source-builder** (FR-22): Admin add-source wizard with mandatory passing test before enable
- [ ] **REQ-telegram-monitoring** (FR-2): Userbot monitors public channels → LLM-extracted signals
- [ ] **NFR groups**: performance, reliability, security, observability, time/localization

### Out of Scope

<!-- Explicit boundaries from TZ §2.3 / §2.4. Includes reasoning to prevent re-adding. -->

- Price forecasting / trading advice — system explains observed factors only; AI is advisory (TZ §1.1)
- Counterparty creditworthiness scoring — not a goal of this product (TZ §2.4)
- "Offers to clients" module — managers reply manually in Telegram; system only records status changes (TZ assumption 2.3.1)
- Native iOS/Android apps — Telegram Web App is the only client surface (TZ §2.4)
- Paid international data sources (ChemOrbis, Argus, Platts, Polymerupdate, ETS) as data inputs — out of scope; landing strip is marketing brand-coverage only (TZ §2.3.5)
- 1C / CRM / payment integrations — not in scope (TZ §2.4)
- Monitoring private channels/chats without owner consent — only agreed public channels (TZ §2.4)
- SLA on external-source availability — best-effort only (TZ §2.4)
- Browser automation (Playwright) for collectors — escalate to lead if a page needs JS; no unilateral adoption (SPEC §2.1)
- Media download from Telegram in Phase 1 — presence flagged only (SPEC §2.2)

### Future Milestone — Phase 2 (planned follow-up, NOT in current roadmap)

Phase 2 (international content loop) is a planned follow-up milestone, scoped but deliberately excluded from the current ROADMAP. Registered in REQUIREMENTS.md tagged `Future Milestone`:

- **REQ-international-feed** (FR-3): SunSirs + DCE indices, RU/KZ/TR channels, ETS Kazakhstan (after verification)
- **REQ-webapp-news** (FR-8): Published-report feed in the Web App
- **REQ-reports** (FR-18): Morning/weekly reports with human-in-the-loop approval before channel publish
- **REQ-counterparty-linking**: Semi-automatic counterparty alias resolution with analyst confirmation
- **REQ-intraday-channel-alerts**: Publish selected alerts to a public channel via dashboard button

## Context

- **Five components, one backend, one DB**: internal dashboard, Telegram Web App, Telegram bot, Telegram channel, data-collection engine — all reading/writing one PostgreSQL 16 database.
- **Three frontend surfaces ship**: (A) public Next.js landing, (B) authenticated Next.js dashboard (may share the Next.js app with A), (C) separate Telegram Web App (React + Vite). The Purchase Requests master-detail screen is the highest-fidelity Phase-1 dashboard deliverable.
- **Design contract**: `docs/polymer-intelligence-ui-mockups.md` is the textual UI contract (dark high-contrast theme, green emerald accent, consistent status/urgency color coding). New screens beyond those listed are a scope change (TZ §2.3.7). The Web App honors Telegram theme vars, not a hardcoded dark theme.
- **Schema contract**: `docs/polymer-intelligence-db-architecture.md` is the locked PostgreSQL 16 DDL (v1.1). Schema changes only via Alembic migration + DB-doc edit in the same PR.
- **Epic→task breakdown**: `docs/polymer-intelligence-dev-spec.md` §9 defines epics E1–E10. Current milestone = E1–E6 (Phase 1). E7–E10 = Phase 2.
- **Risk allocation**: data sources limited to open uzex.uz (mandatory "По данным uzex.uz" attribution), agreed public TG channels, free open indices, official CBU rates, own client data. Userbot account-restriction risk borne by customer. Source-layout changes break collectors → fixed under support, not a warranty defect. AI-quality thresholds fixed in TZ §6.
- **Top external risk**: UZEX layout changes (SPEC §10.1); selectors live in `sources.config`, not in code, to absorb this.

## Constraints

- **Tech stack (backend)**: Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Celery + Redis, PostgreSQL 16 — locked by SPEC (see DEC-stack-backend).
- **Runtime topology**: Telethon userbot is a separate long-lived process (NOT a Celery task); aiogram 3 bot via FastAPI webhook (no separate bot container). Containers: api, worker, beat, userbot, dashboard, postgres, redis, nginx.
- **Datastore/schema**: One PostgreSQL 16 database; full DDL fixed in the DB-architecture doc. Source-enable DB invariant: `is_enabled = true ⇒ last_test_ok_at IS NOT NULL`.
- **AI**: Anthropic API. Extraction = claude-haiku-4-5 (configurable); reports = Sonnet-class. One LLM call = classify + extract; no multi-message batching. Daily token budget via Redis with graceful degradation.
- **Frontend**: Next.js (app router, TS strict, TanStack Query/Table, Recharts, shadcn/ui, dark theme); Web App = React + Vite + @telegram-apps/sdk, react-i18next ru/uz, bundle ≤300 KB gzip. Design tokens in tailwind config — no hardcoded colors.
- **Real-time**: SSE (`GET /feed/stream`) + 30 s polling fallback; no WebSocket (DEC-realtime-sse-not-websocket).
- **Auth**: Dashboard JWT (access 15 min + refresh 7 d httpOnly); Web App X-Telegram-Init-Data HMAC-validated per request (TTL 24 h). Passwords argon2. Never trust client identity from request body.
- **Time**: timestamptz/UTC in DB; display Asia/Tashkent; daily series observed_on = market-local date.
- **Deploy**: Single VPS (≥4 vCPU / 8 GB / 80 GB SSD), docker compose, nginx + TLS (certbot). MinIO bundled for request files. CI = GitHub Actions (ruff, mypy, eslint+tsc → tests → image build); deploy via ssh script. Backups pg_dump -Fc daily, rotate 14 d, weekly offsite; restore script + restore test is an acceptance item.

## Key Decisions

<!-- Durable technical decisions carried from SPEC/DB intel. SPEC-precedence; client TZ wins on any "what/why" conflict. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| DEC-stack-backend: Python 3.12 + FastAPI + SQLAlchemy 2 + Celery/Redis + PG16 | SPEC + PRD agree | — Pending |
| DEC-postgres-16: one PG16 DB, fixed DDL | single datastore + hard schema contract | — Pending |
| DEC-userbot-separate-process: Telethon outside Celery | persistent MTProto session conflicts with Celery event loops | — Pending |
| DEC-bot-webhook-no-separate-container: aiogram via FastAPI webhook | avoids extra container | — Pending |
| DEC-raw-immutable: immutable raw_items + reproducible parse_runs | data integrity, replayable parsing | — Pending |
| DEC-single-signal-stream: everything normalizes to `signals`; chart reads only price_points | one feed/alerts/analytics source | — Pending |
| DEC-llm-models: Haiku extract / Sonnet reports, configurable via env | cost vs quality tiering | — Pending |
| DEC-llm-budget-degradation: daily token limit, rule-based fallback + catch-up | cost control / reliability | — Pending |
| DEC-source-adapter-registry: pluggable SourceAdapter; admin form auto-built from config_schema | no-code source onboarding | — Pending |
| DEC-test-before-enable: source can't enable until a Test passes (DB invariant) | source-builder safety | — Pending |
| DEC-human-in-the-loop-reports: no auto-publish transition (code-level) | publishing compliance (Phase 2) | — Pending |
| DEC-file-storage: direct upload to MinIO, telegram_file_id fallback | better UX than store-and-fetch | — Pending |
| DEC-realtime-sse-not-websocket: SSE + 30 s polling | one-way updates don't need WS | — Pending |
| DEC-auth-split: JWT dashboard / initData Web App | right auth per surface | — Pending |
| DEC-tz-handling: UTC store, Asia/Tashkent display, market-local observed_on | correct time semantics | — Pending |
| DEC-deploy-single-vps: one VPS, docker compose, nginx+TLS | simple, fits scale | — Pending |

---
*Last updated: 2026-06-17 — Phase 3 (E3 Client Circuit) complete: Telegram initData auth, 4-step Web App request wizard + Мои заявки/detail/timeline, RU/UZ i18n, direct MinIO uploads, aiogram client bot + status notifications. REQ-webapp-auth / REQ-request-wizard / REQ-my-requests / REQ-webapp-i18n / REQ-bot-clients validated; REQ-nfr-performance partial (bundle 42.8 KB + SLA proxies). All 9 code-review findings fixed. Live deploy-drill deferred (03-UAT.md). Next: Phase 4 — Dashboard + Source Constructor.*
