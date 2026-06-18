# Roadmap: Polymer Intelligence

## Overview

The current milestone delivers **Client Phase 1** — the domestic-market MVP. We build a walking skeleton first (monorepo, locked PostgreSQL 16 schema, JWT auth, /health), then bring up the immutable ingest pipeline with the UZEX collector and FX rates so real polymer signals exist. With data flowing, we ship the client loop (Telegram bot + Web App request wizard + my-requests) so requests reach the team, then the internal dashboard (live feed, the flagship Purchase Requests master-detail, prices, alerts, sources health) including the no-code source constructor. We then layer Telegram-channel monitoring with LLM extraction onto the same adapter registry. Finally we run the client acceptance criteria (TZ §6.1), the restore test, and handover. Phases follow the dev-spec §9 dependency order E1 → E2 → E3 → E4(+E4a) → E5 → E6. Phase 2 (international content loop) is a planned follow-up milestone, not in this roadmap.

**Schema contract for every phase:** `docs/polymer-intelligence-db-architecture.md` (locked PostgreSQL 16 DDL v1.1) — schema changes only via Alembic migration + DB-doc edit in the same PR.
**UI contract for every frontend phase:** `docs/polymer-intelligence-ui-mockups.md` — new screens beyond those listed are a scope change.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: Walking Skeleton** (E1) - Monorepo, full DB schema + seed, JWT auth + roles, /health, CI, docker-compose (gap-closure plans 01-08..01-10 executed 2026-06-15: dev-nginx boot SC#1 ✓ live, ruff/mypy green SC#5 ✓, S3 env CR-01 ✓; re-verification 2026-06-15 found 3 new gaps → 3/5 must-haves: SC#1 worker/beat crash on missing app.tasks [deferrable to Phase 2], SC#2 migrations not auto-applied on compose up [no lifespan hook], SC#5 dashboard tsc fails on clean CI [.next typegen missing])
- [x] **Phase 2: Ingest Core + UZEX** (E2) - Immutable raw pipeline, SourceAdapter registry, UZEX collectors → signals, FX rates, source health (completed 2026-06-16)
- [x] **Phase 3: Client Circuit** (E3) - aiogram bot, Telegram Web App 4-step wizard + my-requests + i18n, files → MinIO, status notifications (completed 2026-06-17)
- [ ] **Phase 4: Dashboard + Source Constructor** (E4 + E4a) - Live feed, flagship Purchase Requests master-detail, prices, alerts, sources, no-code add-source wizard
- [ ] **Phase 5: Telegram Monitoring + AI** (E5) - Userbot over the registry, LLM extraction + budget, needs_review flow, eval golden-set, control-sample run
- [ ] **Phase 6: Acceptance & Handover** (E6) - TZ §6.1 acceptance criteria, restore test, runbook, handover

## Phase Details

### Phase 1: Walking Skeleton

**Goal**: A deployable end-to-end skeleton exists — the locked schema is migrated and seeded, the team can authenticate by role, and health/CI/compose are green — so every later phase plugs into a real, running backbone.
**Depends on**: Nothing (first phase)
**Requirements**: REQ-roles, REQ-nfr-security, REQ-nfr-observability, REQ-nfr-time-localization
**Success Criteria** (what must be TRUE):

  1. `docker compose up` brings up api, postgres, redis, nginx; `/health` returns OK. (worker + beat containers are defined and start, but their Celery app `app.tasks.celery_app` is built in Phase 2 — until then they intentionally idle/restart; full worker+beat operation is verified in Phase 2 where the beat schedule drives UZEX fetch. Deferred 2026-06-15 — see Deferred Items.)
  2. Alembic applies the full locked PostgreSQL 16 schema (all tables, ENUMs, `v_live_feed`) plus seed data (products, grades, synonyms) on a clean database
  3. A staff user can log in and receive a JWT (access 15 min + refresh 7 d httpOnly); endpoints enforce admin/analyst/trader/viewer roles
  4. Passwords are argon2-hashed; secrets load from `.env` outside the repo; timestamps are stored UTC with an Asia/Tashkent display helper
  5. CI (ruff, mypy, eslint+tsc, tests, image build) passes green on the scaffold

**Plans**: 10 plans (4 executed + 3 verification gap-closure + 3 UAT gap-closure)

**Wave 1**

- [x] 01-01-PLAN.md — Monorepo + core config/secrets, db session/Base, structlog JSON, Asia/Tashkent helper, /health, docker-compose dev (postgres, redis, api, worker, beat)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — SQLAlchemy models + 14 ENUMs + Alembic migration reproducing the locked schema verbatim (20 tables + v_live_feed), advisory-locked entrypoint, seed (products, UZ grades, synonyms)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Auth backbone: argon2 hashing, JWT (access 15m + refresh 7d httpOnly), /auth/login + /auth/refresh, require_role guard (admin/analyst/trader/viewer), audit_log, per-role seed users
- [x] 01-04-PLAN.md — CI (ruff, mypy services/+schemas/, eslint+tsc, tests, image build), Next.js dashboard + React/Vite webapp scaffolds, Dockerfiles, TLS-ready nginx reverse proxy

**Wave 4 — Gap closure** *(remediation of verification gaps; plans run in parallel — no file overlap)*

- [x] 01-05-PLAN.md — SC#1 deployable stack: add nginx service + backend/Dockerfile so compose build blocks resolve, add nginx events{} block, fix CR-06 security-header inheritance
- [x] 01-06-PLAN.md — SC#5 green CI: fix invalid PEP 517 build-backend (setuptools.build_meta), remove `|| true` from both eslint gates and confirm scaffolds lint clean
- [x] 01-07-PLAN.md — REQ-nfr-security hardening: settings-driven CORS (no wildcard+credentials, CR-04), real argon2 dummy-verify (CR-05/T-03-01), JWT_SECRET ≥32-char startup validator (WR-01)

**Wave 5 — UAT gap closure** *(remediation of live-UAT findings 2026-06-15; 01-08 + 01-09 run in parallel, 01-10 serializes after 01-09 on shared config.py/ci.yml)*

- [x] 01-08-PLAN.md — SC#1 dev-nginx actually boots: drop the boot-time `dashboard` upstream resolution and the unmounted-letsencrypt-cert load so `docker compose up` brings nginx up and `/health` returns 200 (live re-verify required)
- [x] 01-09-PLAN.md — REVIEW CR-01: rename CI `S3_ENDPOINT_URL` → `S3_ENDPOINT` so the case-sensitive Settings field reads it; regression test locks the CI env name to the field name (config default preserved, suite stays green)
- [x] 01-10-PLAN.md — SC#5 backend lint/type gate truly green: resolve the 124 `ruff check .` violations behavior-preservingly, make `mypy app/services`/`app/schemas` pass, and exact-pin ruff + mypy for reproducibility (pytest stays 100 passed / 17 skipped)

**Schema contract**: `docs/polymer-intelligence-db-architecture.md` — the migration MUST reproduce the locked DDL verbatim (raw_items, signals, requests, price_points, alerts, reports, sources, counterparties, fx_rates, staff_users, audit_log, ENUM types, v_live_feed). This is the foundation all phases build on.

### Phase 2: Ingest Core + UZEX

**Goal**: Real UZEX polymer signals and FX rates flow into the database through an immutable, deduplicated, reproducible pipeline whose health is observable and whose failures alert without stopping other sources.
**Depends on**: Phase 1
**Requirements**: REQ-uzex-parser, REQ-fx-rates, REQ-sources-health, REQ-nfr-reliability
**Success Criteria** (what must be TRUE):

  1. Polymer positions from a test trading day appear in `signals` with correct fields; on a ≥50-position control sample, field accuracy is ≥95% (TZ §6.1.2)
  2. UZEX offers/quotations/concluded-deals are fetched on the beat schedule (15 min trading hours, hourly otherwise); re-runs create no duplicates (sha256 dedupe, ON CONFLICT DO NOTHING) and raw data is stored immutably before parsing
  3. The daily CBU rate imports into `fx_rates`; a value displayed in any currency shows the converted figure alongside the preserved original
  4. A SourceAdapter registry exists (`fetch`/`test`/`config_schema`); the synonyms dictionary drives relevance and is admin-top-up-able; non-polymer rows land as `raw_items` status='irrelevant'
  5. When one source fails 3 consecutive cycles it raises a `source_failure` alert within 30 min and the other collectors keep running; success resets the counter

**Plans**: 7 plans in 4 waves

**Wave 1** *(foundations — parallel, no file overlap)*

- [x] 02-01-PLAN.md — Celery app + queue topology + Asia/Tashkent beat schedule + ingest config keys (unblocks Phase-1 SC#1 worker/beat carryover)
- [x] 02-02-PLAN.md — [BLOCKING migration 0002] product_synonyms + manual_classification_queue tables, synonyms.json seeder, relevance service (admin-top-up-able)
- [x] 02-03-PLAN.md — SourceAdapter Protocol + registry + SSRF-hardened httpx client + GET /admin/source-types (config_schema feed)

**Wave 2** *(concrete adapters + parse — blocked on Wave 1)*

- [x] 02-04-PLAN.md — UZEX offers/contracts/deals adapters (selectolax, config-driven selectors) + immutable sha256-dedupe raw pipeline + HTML fixtures (has selectolax legitimacy + no-JS escalation checkpoint)
- [x] 02-05-PLAN.md — CBU rates adapter → fx_rates (on-read conversion) + rule-based parse_raw_item (raw → signals, relevance routing, grade regex, parse_runs journal)

**Wave 3** *(health + alerting — blocked on Wave 2)*

- [x] 02-06-PLAN.md — Source-health bookkeeping + 3-consecutive-failure deduped source_failure alert + per-source failure isolation + check_source_health beat task + GET /admin/sources/health

**Wave 4** *(reliability hardening + acceptance — blocked on Wave 3)*

- [x] 02-07-PLAN.md — Worker auto-restart + pg_dump backup + ≤2h restore runbook + UZEX/CBU source seeder + ≥95% accuracy gate on a ≥50-position control sample + live end-to-end human-verify checkpoint (live drill deferred to deploy; automated gate: 100% on 55 positions / TZ §6.1.2 PASS)

**Schema contract**: `docs/polymer-intelligence-db-architecture.md` (sources, raw_items, parse_runs, signals, price_points, fx_rates). UZEX selectors live in `sources.config`, not in code. No browser automation — escalate if a page needs JS.

### Phase 3: Client Circuit

**Goal**: A client can submit a purchase request end-to-end from the Telegram Web App, that request lands in the system promptly, and the client is kept informed of its status — closing the client-facing loop.
**Depends on**: Phase 2 (registry/pipeline scaffolding; requests share the raw→signal patterns and feed view)
**Requirements**: REQ-webapp-auth, REQ-request-wizard, REQ-my-requests, REQ-webapp-i18n, REQ-bot-clients, REQ-nfr-performance
**Success Criteria** (what must be TRUE):

  1. A client opens the Web App, is authenticated via Telegram initData (first login creates a `clients` row), and completes the 4-step wizard; submitting produces a confirmation with number REQ-YYYY-MM-DD-NNNNN, and the request is queryable on the backend within 10 s (TZ §6.1.1)
  2. The client can attach files (PDF/Excel/JPG, ≤10 MB, ≤5) which upload directly to MinIO (telegram_file_id fallback for bot-sent files)
  3. The client sees "Мои заявки" with current statuses and history, and receives a bot push within 30 s of a status change (TZ §6.1.1)
  4. The Web App toggles RU/UZ (default from Telegram language_code) and honors Telegram theme vars; first paint ≤3 s on 3G and bundle ≤300 KB gzip
  5. The bot greets the client with a Web App button and routes status notifications via the deliveries queue

**Plans**: 6 plans in 4 waves

**Wave 1** *(backend foundation)*

- [x] 03-01-PLAN.md — Deps (aiogram/boto3/python-multipart) + MinIO compose + S3 client + initData auth dep (get_current_client) + upload validation service + /webapp Pydantic schemas

**Wave 2** *(parallel — backend API + frontend shell, no file overlap)*

- [x] 03-02-PLAN.md — request_service (REQ-YYYY-MM-DD-NNNNN number + status machine + history + notify enqueue) + /webapp request/me/files API, initData-authed and IDOR-scoped
- [x] 03-04-PLAN.md — Web App shell (router + i18n ru/uz + Telegram SDK) + api client + zustand wizard store + Home (C-01) + 4-step wizard (C-02..C-05) with per-step zod validation

**Wave 3** *(parallel — bot/notify + frontend my-requests, no file overlap)*

- [x] 03-03-PLAN.md — aiogram webhook bot (/start greeting + Web App button) + RU/UZ templates + send_status_change_notification notify task (D-10 labels, deep-link)
- [x] 03-05-PLAN.md — Мои заявки (C-06) + detail + Asia/Tashkent status timeline (C-07) + notifications (C-08) + RU/UZ settings toggle (C-09) + bundle ≤300 KB gzip

**Wave 4** *(acceptance gate)*

- [x] 03-06-PLAN.md — Automated SLA proxies (≤10 s readback, ≤30 s notify dispatch) + phase-03 acceptance doc mapping the 5 success criteria to a deploy-time live drill

**UI hint**: yes
**UI contract**: `docs/polymer-intelligence-ui-mockups.md` §4 (Surface C — 5 Web App screens: home, wizard steps 1–3, confirmation, plus Мои заявки / detail / notifications / profile-language). React + Vite + @telegram-apps/sdk, MainButton/BackButton, zustand state survives minimize, react-hook-form + zod, react-i18next ru/uz.

### Phase 4: Dashboard + Source Constructor

**Goal**: The internal team has a live, filterable working surface — the flagship Purchase Requests master-detail, the unified feed, prices, alerts, and source management — and an admin can onboard new public sources with no developer and no code.
**Depends on**: Phase 3 (real requests and signals exist to display and act on)
**Requirements**: REQ-live-feed, REQ-purchase-requests, REQ-price-trends, REQ-alerts, REQ-bot-team, REQ-source-builder
**Success Criteria** (what must be TRUE):

  1. The team views the unified Live Market Feed (`v_live_feed`) with filters (period, product, type, source, urgency) that refresh without reload via SSE (30 s polling fallback); feed/table API responds ≤500 ms at up to 1M signals
  2. On the Purchase Requests screen the team opens a request's detail card (details, files, AI block: score + target-vs-avg price), changes status, assigns an owner, and adds notes — every action writes to `audit_log`
  3. The team views a price chart per product/market sourced from `price_points`, and sees per-source health (last fetch, consecutive failures) with enable/disable
  4. The team builds an alert rule (product, volume/price threshold, urgency, channel); matches deliver to DM/group respecting Telegram rate limits via the `deliveries` queue
  5. An admin adds a new public website AND a new Telegram channel through the add-source wizard with no developer: the form is auto-built from the adapter's config_schema, a Test shows a ≤10-row preview, the source cannot be enabled until a test passes, and its signals subsequently appear in the feed (TZ §6.1.6). **Cross-phase caveat (CONTEXT.md):** Phase 4 delivers website (`html_table`/`rss`) onboarding end-to-end; `telegram_channel`/`llm_page` are config-saveable in a PENDING state only — the "telegram-channel signals appear in feed" slice is a Phase-5/6 acceptance item (userbot + LLM extraction land then).

**Plans**: 9 plans in 6 waves (foundation-first per D-03)

**Wave 1** *(foundation — parallel, no file overlap)*

- [x] 04-01-PLAN.md — Backend feed foundation: `GET /feed` keyset `(event_at, id)` pagination over `v_live_feed` + SSE `GET /feed/stream` (Redis pub/sub `feed:new`, unbuffered) + dashboard schemas + router registered (REQ-live-feed)
- [x] 04-02-PLAN.md — Frontend foundation (D-03): shadcn/ui init + token reconciliation (no token overwrite), auth-guarded app-router shell + 240px sidebar + AppShell, TanStack Query client, `useSSE` (backoff + 30 s polling fallback), typed `api.ts` Bearer client, Asia/Tashkent `tz.ts`, login submit (REQ-live-feed)

**Wave 2** *(parallel — feed screen + requests backend, no file overlap)*

- [x] 04-03-PLAN.md — Live Market Feed screen: TanStack feed table + filters wired to `/feed` + SSE refresh, dashboard home (5 KPI cards, AI Market Signals D-01 placeholder panel), `/signals` + `/offers` pages (REQ-live-feed)
- [x] 04-04-PLAN.md — Flagship Purchase Requests backend: `GET/PATCH /requests` + note/assign/contact actions (all → `audit_log`, D-10), D-12 status machine via `transition_status`, D-11 contact deep-link, D-02 real price analysis, `GET /admin/users` (REQ-purchase-requests)

**Wave 3** *(parallel — requests frontend + sources backend, no file overlap)*

- [x] 04-05-PLAN.md — Purchase Requests master-detail frontend: paginated table + filter bar + 6 KPI cards, 400px right detail Sheet (Request Details / Source Info / AI block D-01+D-02 / Files / Actions), all D-10/D-11/D-12 actions, CSV export endpoint + stream (REQ-purchase-requests)
- [x] 04-06-PLAN.md — Source constructor backend: `html_table`/`rss` live adapters (SSRF-guarded, ≤10-row preview D-06) + `telegram_channel`/`llm_page` pending stubs (D-04/D-05), `/sources` GET/POST/PATCH + `POST /sources/{id}/test`, server-side enable-gate invariant, startup registration (REQ-source-builder, REQ-sources-health)

**Wave 4** *(alerts + prices backend — blocked on Wave 3 main.py)*

- [x] 04-07-PLAN.md — Alerts engine + team delivery + prices: `alert_service` hardcoded JSONB predicate interpreter (NOT eval, D-07) + dedupe + NEW `send_delivery` task on the `notify` queue with token-bucket (D-09), `/alert-rules` CRUD + `/alerts` feed (per-rule chat_id D-08), `GET /prices/series` (REQ-alerts, REQ-bot-team, REQ-price-trends)

**Wave 5** *(remaining feature screens — blocked on Wave 4)*

- [ ] 04-08-PLAN.md — Sources wizard (auto-form `JsonSchemaForm` from `config_schema`, real Test preview, enable-gate UI, pending pre-staging D-05) + Alerts feed + rule builder (full predicate set, `lead_score_gte` disabled D-07, per-rule chat_ids D-08) + Recharts Price Trends + admin users screen (REQ-source-builder, REQ-alerts, REQ-price-trends, REQ-sources-health)

**Wave 6** *(acceptance gate)*

- [ ] 04-09-PLAN.md — Acceptance gate: feed performance test (≤500 ms @ ~1M rows, REQ-nfr-performance) + dashboard RBAC matrix test (viewer 403 on writes) + `04-ACCEPTANCE.md` mapping SC#1–SC#5 to a deploy-time drill (honoring the SC#5 telegram cross-phase caveat) + human-verify checkpoint (all 6 requirements)

**UI hint**: yes
**UI contract**: `docs/polymer-intelligence-ui-mockups.md` §3 (Surface B — sidebar nav, dashboard home KPIs, the high-fidelity Purchase Requests master-detail, Price Trends Recharts, /sources add-source wizard, /alerts rules). Next.js app router, TS strict, TanStack Query/Table, shadcn/ui, dark theme via tailwind tokens (no hardcoded colors). Add-source forms render from `GET /admin/source-types` config_schema. Adapters added here: llm_page, html_table, rss (no-code); telegram_channel reused next phase.

### Phase 5: Telegram Monitoring + AI

**Goal**: Public Telegram channels are monitored by the userbot and their messages become accurate, journaled, budget-bounded LLM-extracted signals in the same stream — with low-confidence items routed to human review and quality measured against a golden set.
**Depends on**: Phase 4 (telegram_channel adapter slots into the registry; signals surface in the feed and the needs_review screen)
**Requirements**: REQ-telegram-monitoring, REQ-ai-extraction, REQ-lead-scoring, REQ-llm-budget
**Success Criteria** (what must be TRUE):

  1. The userbot runs as a separate long-lived process, subscribes to enabled `telegram_channel` sources, rereads the channel list every ~10 min without restart, writes new messages to `raw_items`, and emits a Redis heartbeat (silence >5 min alerts)
  2. Each message gets one LLM call (classify + extract) producing strict JSON per the fixed schema; model + prompt_version + tokens are journaled in `parse_runs`; confidence <0.5 routes the signal to a `needs_review` queue surfaced in the dashboard
  3. Signals and requests carry lead_score (0–1) and HOT/MEDIUM/LOW; scores recompute on prompt-version change
  4. When the daily token limit is exceeded, new items stay pending with rule-based fallback + nightly catch-up and the admin is alerted; per-source 7-day token spend is visible for AI sources
  5. On the customer's 100-message control sample, relevant-signal recall is ≥80% and field precision on detected signals ≥85% (TZ §6.1.3), measured via the eval tool + golden-set

**Plans**: TBD
**Schema contract**: `docs/polymer-intelligence-db-architecture.md` (raw_items, parse_runs, signals.ai). Extraction output per `docs/extraction-schema.json`; prompts in `parsing/prompts/extract_v{N}.md` (never edit old versions). Media not downloaded in Phase 1.

### Phase 6: Acceptance & Handover

**Goal**: The customer can confirm Phase 1 is accepted — every TZ §6.1 acceptance criterion and the source-constructor acceptance pass, the database can be restored from backup within the stated window, and the system is documented and handed over.
**Depends on**: Phase 5
**Requirements**: (cross-cutting verification of Phase-1 requirements; no net-new requirements)
**Success Criteria** (what must be TRUE):

  1. All TZ §6.1 acceptance items pass on review: Web App request ≤10 s to dashboard and status notification ≤30 s (§6.1.1); UZEX accuracy ≥95% on ≥50-item sample (§6.1.2); channel recall ≥80% / precision ≥85% on the 100-message sample (§6.1.3); one source failing doesn't stop others, failure alert ≤30 min (§6.1.4)
  2. A DB restore from backup onto a clean server, following the written procedure, completes within 2 hours (TZ §6.1.5)
  3. The source-constructor acceptance passes: an admin onboards a new public site + Telegram channel with no developer and a failed-test source cannot be enabled (TZ §6.1.6)
  4. Deliverables are handed over: deployment + restore docs, runbook, prompt/extraction-schema descriptions, and admin instructions (sources, alert rules)

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Walking Skeleton | 10/10 | Gaps Found | - |
| 2. Ingest Core + UZEX | 7/7 | Complete    | 2026-06-16 |
| 3. Client Circuit | 6/6 | Complete    | 2026-06-17 |
| 4. Dashboard + Source Constructor | 7/9 | In Progress|  |
| 5. Telegram Monitoring + AI | 0/TBD | Not started | - |
| 6. Acceptance & Handover | 0/TBD | Not started | - |

---
*Roadmap created: 2026-06-13 (Client Phase 1 milestone). Phase 2 international loop = planned follow-up milestone, not in this roadmap.*
