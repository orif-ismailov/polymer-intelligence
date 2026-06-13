# Decisions (Intel)

Synthesized architectural/technical decisions extracted from the ingested doc set.

NOTE: No ADR-typed documents were present in this ingest. There are therefore no
formally-locked ADR decisions. The decisions below are durable technical choices
recorded by the two SPEC documents (dev-spec, db-architecture). They carry SPEC
precedence — the client PRD (TZ) wins on any "what/why" conflict per the dev-spec's
own deference clause ("При противоречии приоритет у клиентского ТЗ").

Provenance abbreviations:
- TZ   = docs/polymer-intelligence-tz.md (PRD)
- SPEC = docs/polymer-intelligence-dev-spec.md (SPEC)
- DB   = docs/polymer-intelligence-db-architecture.md (SPEC)

---

## DEC-stack-backend — Backend stack
- source: docs/polymer-intelligence-tz.md (§3); docs/polymer-intelligence-dev-spec.md (§1)
- status: recorded (not locked; SPEC + PRD agree)
- decision: Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Celery + Redis, PostgreSQL 16.
- scope: backend runtime + persistence + task queue

## DEC-postgres-16 — PostgreSQL 16 as the single datastore
- source: docs/polymer-intelligence-db-architecture.md (header, §Принципы); docs/polymer-intelligence-tz.md (§1, §2.1)
- status: recorded (DB doc records concrete locked schema DDL; not ADR-locked)
- decision: One backend, one PostgreSQL 16 database for all components. Full DDL is fixed
  in the DB architecture doc (raw_items, signals, requests, price_points, alerts, reports,
  sources, counterparties, fx_rates, staff_users, audit_log, plus ENUM types and v_live_feed).
- scope: primary datastore + schema contract

## DEC-userbot-separate-process — Telethon userbot runs outside Celery
- source: docs/polymer-intelligence-dev-spec.md (§1, §2.2)
- status: recorded
- decision: The Telethon (MTProto) userbot is a standalone long-lived process, NOT a Celery
  task. It writes directly to raw_items and enqueues parse tasks via Redis. Rationale:
  persistent MTProto connection/session conflicts with Celery worker event loops.
- scope: data-collection runtime topology

## DEC-bot-webhook-no-separate-container — Telegram bot via FastAPI webhook
- source: docs/polymer-intelligence-dev-spec.md (§1, §4.1)
- status: recorded
- decision: aiogram 3 bot is served via webhook through FastAPI (POST /telegram/webhook/{secret});
  no separate bot container. Containers: api, worker, beat, userbot, dashboard, postgres, redis, nginx.
- scope: deployment topology

## DEC-raw-immutable — Immutable raw layer + reproducible parsing
- source: docs/polymer-intelligence-tz.md (§3 Принципы); docs/polymer-intelligence-db-architecture.md (§Принципы); docs/polymer-intelligence-dev-spec.md (§2)
- status: recorded (all three docs agree)
- decision: All inbound data is stored immutably in raw_items before parsing. Parsing is a
  separate, repeatable task. Dedupe by sha256(source_id + external_id + content_normalized)
  with ON CONFLICT DO NOTHING. Every LLM call is journaled in parse_runs (model, prompt_version, tokens).
- scope: ingestion/data-integrity invariant

## DEC-single-signal-stream — One normalized signals stream
- source: docs/polymer-intelligence-db-architecture.md (§Принципы, §4)
- status: recorded
- decision: Everything parsed normalizes into a single `signals` table; feed, alerts, and
  analytics all read from it. price_points is a derived layer computed from deals + external
  indices; chart UI reads only price_points.
- scope: data model

## DEC-llm-models — LLM model tiers
- source: docs/polymer-intelligence-tz.md (§3); docs/polymer-intelligence-dev-spec.md (§2.3, §5, §7)
- status: recorded (configurable via env)
- decision: Anthropic API. Extraction = Haiku-class (claude-haiku-4-5, configurable via
  LLM_EXTRACT_MODEL); report generation = Sonnet-class (LLM_REPORT_MODEL). Single LLM call
  per message = classification + extraction; no batching of multiple messages per call.
- scope: AI processing

## DEC-llm-budget-degradation — Configurable daily token budget with graceful degradation
- source: docs/polymer-intelligence-tz.md (FR-21); docs/polymer-intelligence-dev-spec.md (§2.3)
- status: recorded
- decision: LLM_DAILY_TOKEN_LIMIT enforced via Redis counter. On exceed: new items stay
  pending (rule-based fallback + nightly catch-up), admin alerted. Per-source 7-day token
  spend visible in admin for AI sources.
- scope: cost control / reliability

## DEC-source-adapter-registry — Pluggable SourceAdapter registry
- source: docs/polymer-intelligence-tz.md (FR-22, §2.1 source-builder); docs/polymer-intelligence-dev-spec.md (§2.5)
- status: recorded
- decision: Each collection method is a SourceAdapter (type_name, config_schema, fetch(), test()).
  Adapters registered in ingest/registry.py; admin UI builds the add-source form automatically
  from each adapter's pydantic config_schema (GET /admin/source-types). New adapter = one file +
  registration; no migrations, no UI edits. Built-in: telegram_channel, llm_page, html_table, rss,
  and code-shipped specialized: uzex_*, sunsirs, dce, cbu_rates.
- scope: extensibility / admin "no-code" source onboarding

## DEC-test-before-enable — Mandatory dry-run before enabling a source
- source: docs/polymer-intelligence-tz.md (FR-22, §2.1); docs/polymer-intelligence-dev-spec.md (§2.5); docs/polymer-intelligence-db-architecture.md (§2 sources invariant)
- status: recorded (enforced at DB-invariant level)
- decision: A source cannot be enabled (is_enabled=true) until a Test (dry-run fetch+parse,
  preview up to 10 rows, nothing written) has passed at least once. DB invariant:
  is_enabled = true ⇒ last_test_ok_at IS NOT NULL.
- scope: source-builder safety

## DEC-human-in-the-loop-reports — No auto-publish of reports
- source: docs/polymer-intelligence-tz.md (FR-18, §2.2); docs/polymer-intelligence-dev-spec.md (§5); docs/polymer-intelligence-db-architecture.md (§8)
- status: recorded (enforced in code, not just UI)
- decision: Morning/weekly/intraday reports are generated as draft → pending_approval →
  analyst/admin Approve → published → channel delivery. There is NO auto-publish transition
  in the status machine (enforced at code level, not only UI). Every publication footer:
  "По данным uzex.uz" (source attribution requirement).
- scope: content publishing / compliance

## DEC-file-storage — Request files: direct upload to S3/MinIO, telegram_file_id fallback
- source: docs/polymer-intelligence-dev-spec.md (§4.2); docs/polymer-intelligence-db-architecture.md (Open Questions #1, resolved); refines docs/polymer-intelligence-tz.md (assumption 2.3.2)
- status: recorded (clarification of PRD assumption — NOT a contradiction)
- decision: Primary path = direct multipart upload to S3-compatible storage (MinIO bundled in
  docker-compose); MIME validated by magic bytes. telegram_file_id is the fallback for files
  sent to the bot. Schema field storage_path already present in request_files.
  Rationale: better UX than the PRD's original "store as telegram_file_id, download on first open"
  assumption. The DB doc explicitly marks this open question RESOLVED in v1.1.
- scope: request file attachments

## DEC-realtime-sse-not-websocket — SSE + polling fallback, no WebSocket
- source: docs/polymer-intelligence-dev-spec.md (§3.2, §6.1); docs/polymer-intelligence-tz.md (FR-10)
- status: recorded
- decision: Live feed real-time via SSE (GET /feed/stream emits new ids, frontend pulls via REST);
  fallback = 30 s polling. WebSocket deliberately not used (unnecessary infra for one-way updates).
- scope: dashboard real-time

## DEC-auth-split — JWT for dashboard, Telegram initData for Web App
- source: docs/polymer-intelligence-dev-spec.md (§3.2); docs/polymer-intelligence-tz.md (FR-5, §5 NFR security)
- status: recorded
- decision: Dashboard = JWT (access 15 min + refresh 7 d in httpOnly cookie). Web App =
  X-Telegram-Init-Data header, HMAC signature validated against bot token on EVERY request,
  initData TTL 24 h. Never trust client_id/telegram_user_id from request body. Passwords argon2.
- scope: authentication/security

## DEC-tz-handling — UTC in DB, Asia/Tashkent display, market-local observed dates
- source: docs/polymer-intelligence-tz.md (§5 NFR); docs/polymer-intelligence-dev-spec.md (§10 risk 3)
- status: recorded
- decision: All timestamps stored as timestamptz/UTC. Display in Asia/Tashkent. Daily series
  observed_on = market-local date (the `market` field determines TZ). Centralize in a helper.
- scope: time handling

## DEC-deploy-single-vps — Single VPS, docker compose, nginx+TLS
- source: docs/polymer-intelligence-dev-spec.md (§1, §7); docs/polymer-intelligence-tz.md (§3 stack)
- status: recorded
- decision: One VPS (min 4 vCPU / 8 GB / 80 GB SSD), docker compose, nginx with TLS (certbot).
  Migrations applied by api container entrypoint with advisory lock. CI = GitHub Actions
  (ruff, mypy on services/+schemas/, eslint+tsc → tests → image build); deploy via ssh script.
- scope: deployment/ops
