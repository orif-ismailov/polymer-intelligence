# Constraints (Intel)

Implementation contracts extracted from the two SPEC documents. Domain identifiers (table names,
ENUM values, endpoint paths, ENV var names, Incoterms) preserved verbatim.

Sources:
- SPEC = docs/polymer-intelligence-dev-spec.md (Developer Implementation Specification v1.0)
- DB   = docs/polymer-intelligence-db-architecture.md (Database Architecture, PostgreSQL 16, v1.1)

Constraint type tags: schema | api-contract | nfr | protocol

---

## C-schema-postgres16 — PostgreSQL 16 schema (locked DDL)
- type: schema
- source: docs/polymer-intelligence-db-architecture.md (§1-§9)
- content:
  Reference tables: products (code UNIQUE, name_ru/name_uz, category, is_active),
  product_grades (product_id FK, code, producer; UNIQUE(product_id,code)),
  fx_rates (PK(rate_date, ccy char(3)), rate numeric(18,6); UZS-per-1-ccy; conversion on read).
  Sources/raw layer: sources (kind source_kind, adapter text, config jsonb, last_test_ok_at,
  last_fetch_at/last_success_at/consecutive_failures; INVARIANT is_enabled ⇒ last_test_ok_at NOT NULL),
  raw_items (immutable; content_hash bytea sha256; UNIQUE(source_id, content_hash);
  parse_status pending/parsed/failed/skipped/irrelevant), parse_runs (model, prompt_version,
  tokens_in/out, result jsonb).
  Counterparties: counterparties (canonical_name, role counterparty_role
  buyer/seller/trader/producer/unknown, tax_id), counterparty_aliases (alias_norm indexed,
  confidence real, UNIQUE(alias_norm, counterparty_id)).
  Signals: signals (kind signal_kind buy_request/sell_offer/deal/price_quote/news, product_id,
  grade_id/grade_text, volume numeric(14,3), volume_unit default 'MT', price numeric(14,2),
  currency char(3), price_basis price_basis EXW/FCA/FOB/CIF/CPT/DAP/DDP/unknown, region,
  counterparty_id nullable, ai jsonb {lead_score,urgency,classification,model,prompt_version},
  urgency urgency low/medium/high, status text new/viewed/processed/archived, event_at timestamptz).
  Clients/requests: clients (telegram_user_id UNIQUE, language char(2) default 'ru'),
  requests (number text UNIQUE 'REQ-YYYY-MM-DD-NNNNN', incoterms price_basis,
  destination_country char(2) default 'UZ', validity_days default 30, status request_status
  new/viewed/in_progress/offer_sent/matched/closed/cancelled, ai jsonb),
  request_files (telegram_file_id, storage_path, mime_type, size_bytes),
  request_status_history (from_status/to_status, changed_by nullable=system/client).
  Derived: price_points (kind deal_avg/offer_avg/index/futures, market text, currency char(3),
  price_avg/min/max, volume_total, deals_count, observed_on date;
  UNIQUE(kind,source_id,product_id,grade_id,market,observed_on); chart UI reads ONLY this).
  Alerts/delivery: alert_rules (kind alert_kind, condition jsonb, channels jsonb),
  alerts (dedupe_key UNIQUE; kind new_hot_request/large_volume/price_spike/below_market_offer/
  new_buyer/source_failure/custom), deliveries (channel delivery_channel
  telegram_dm/telegram_channel/webapp/dashboard, status queued/sent/failed).
  Reports: reports (kind morning/intraday/weekly/custom, status report_status
  draft/pending_approval/approved/published/rejected — human-in-the-loop, data_snapshot jsonb).
  Staff/audit: staff_users (role staff_role admin/analyst/trader/viewer, password_hash argon2,
  email UNIQUE), audit_log (action, entity, entity_id, details jsonb).
  Views: v_live_feed = signals UNION ALL requests.
  Schema-change rule (SPEC §8): only via alembic migration + DB-doc edit in the same PR.

## C-schema-not-in-phase1 — Deliberately deferred schema
- type: schema
- source: docs/polymer-intelligence-db-architecture.md (§Что сознательно НЕ в Фазе 1)
- content: Partitioning of raw_items/signals (add at >1-2M rows); materialized views for
  counterparty stats / "repeated buyer" / cycles (Phase 3); full-text search on raw_items.content
  (pg_trgm/tsvector, add if needed); an `offers` table for internal team responses to client
  requests (deferred until the response business process is defined — note: TZ assumption 2.3.1
  keeps the manager-replies-manually-in-Telegram model, "офферы клиентам" out of scope).

## C-schema-open-questions — Remaining schema open questions
- type: schema
- source: docs/polymer-intelligence-db-architecture.md (§Открытые вопросы)
- content: (#2) Report multilinguality — one record vs three (uz/ru/en)? Per TZ assumption 2.3.3,
  Phase 1-2 reports are RU-only, so single-record is sufficient for now. (#4) raw_items retention —
  decide after how many months to archive `content` (hash + metadata stay). Resolved questions:
  #1 file storage (see DEC-file-storage), #3 fx rates (fx_rates added in v1.1).

## C-pipeline-rules — Mandatory collector pipeline rules
- type: protocol
- source: docs/polymer-intelligence-dev-spec.md (§2)
- content: (1) Collectors do NOT parse meaning — save raw to raw_items and exit; parsing is a
  separate task (exception: table sources UZEX/SunSirs put parsed row structure in payload, but
  the signals/price_points write is still done by the parse task). (2) Dedupe
  sha256(source_id+external_id+content_normalized) → ON CONFLICT DO NOTHING; re-runs create no
  dupes. (3) Any collector error: log + increment sources.consecutive_failures; at 3 → alert
  source_failure (dedupe_key source_failure:{source_id}:{date}); success resets counter.
  (4) HTTP: 30 s timeout, 3 retries with exponential backoff, honest User-Agent, ≥2 s between
  requests to one host. All background tasks idempotent.

## C-uzex-collector — UZEX collector contract
- type: protocol
- source: docs/polymer-intelligence-dev-spec.md (§2.1)
- content: Pages (ASP.NET server-rendered): /Trade/OffersSumNew, /Trade/NewSpotTable,
  /Trade/OffersCurrencyNew, /Trade/OffersImportNew (15-min); /Trade/ContractsSumNew,
  /Trade/ContractsCurrencyNew (+Rubl/Euro/Yuan) and /Trade/List (hourly). Stack httpx + selectolax;
  NO browser automation — if a page needs JS, escalate to lead (no unilateral Playwright).
  Relevance via products + synonyms dictionary (seed migration, admin-extensible); non-match →
  raw_items.parse_status='irrelevant'. Grade extraction by regex ([A-Z]{1,3}\d{2,4}[A-Z]{0,3} +
  known grades); non-match → grade_text filled, grade_id NULL. Selectors live in sources.config,
  not in code. UZEX layout is the top external risk (SPEC §10.1).

## C-userbot-protocol — Userbot operating constraints
- type: protocol
- source: docs/polymer-intelligence-dev-spec.md (§2.2, §4.3, §10)
- content: Telethon, session file in volume (gitignored + pre-commit hook on *.session),
  customer-provided account/API_ID/API_HASH. Subscribe to sources WHERE kind='telegram_channel'
  AND is_enabled; reread list every 10 min (no restart for new channels). New message →
  raw_items → enqueue parse_raw_item; media NOT downloaded in Phase 1 (presence flagged).
  Anti-flood: let Telethon handle FloodWait (log+wait, no manual retry); add channels 1-2/hour;
  history backfill ≤200 messages on first connect. Heartbeat to Redis every 60 s; beat task
  alerts on silence >5 min.

## C-llm-extract-schema — LLM extraction output contract
- type: protocol
- source: docs/polymer-intelligence-dev-spec.md (§2.3, §10.2)
- content: Model claude-haiku-4-5 (configurable); one call = classify + extract. Output strict JSON
  per docs/extraction-schema.json: {relevant, kind(buy_request|sell_offer|price_quote|news),
  product_code, grade_text, volume_mt, price, currency(USD|UZS|CNY|null),
  price_basis(FCA|CIF|...|unknown), region, counterparty_text, contact,
  urgency(low|medium|high), summary_ru, confidence}. Prompts in parsing/prompts/extract_v{N}.md,
  version → parse_runs.prompt_version; never edit old prompt files. confidence<0.5 → signal
  status='needs_review'. Token budget via Redis; over LLM_DAILY_TOKEN_LIMIT → items pending +
  nightly catch-up + admin alert. No multi-message batching; worker parallelism up to 5 concurrent
  calls. Pydantic validation, 1 retry on schema violation, then failed + needs_review — never regex
  "almost-JSON".

## C-source-adapters — Adapter registry contract
- type: api-contract
- source: docs/polymer-intelligence-dev-spec.md (§2.5)
- content: SourceAdapter Protocol (type_name, config_schema: pydantic, async fetch(source),
  async test(config)). Registry ingest/registry.py; GET /admin/source-types returns types +
  config_schema (admin auto-builds the add form). Built-in adapters and code-required level:
  telegram_channel (no code, LLM extract), llm_page (no code; page→text via selectolax→diff with
  prior snapshot→new fragments→LLM; hashed snapshot, no-op when unchanged, per-source 7-day token
  spend shown), html_table (no code; rule-based column mapping → {product_text,grade,volume,price,
  currency,counterparty,date} + date format), rss (no code, LLM extract), uzex_*/sunsirs/dce/
  cbu_rates (code-shipped specialized). Mandatory Test for all types (dry-run, ≤10-row preview,
  no DB write); cannot enable until a test passes (sources.last_test_ok_at). Boundary: auth/JS/
  captcha/non-standard sources = new code adapter (~1 day typical); paid services only with a
  subscription, internal-loop only.

## C-rest-api — REST API contract (/api/v1)
- type: api-contract
- source: docs/polymer-intelligence-dev-spec.md (§3.2)
- content: Web App: POST /webapp/requests, GET /webapp/requests, GET /webapp/requests/{id},
  POST /webapp/requests/{id}/files, GET /webapp/reports (P2), GET/PATCH /webapp/me.
  Dashboard: GET /feed (filters kind, product_id, source_id, urgency, status, date_from/to;
  keyset pagination by (event_at,id)), GET /feed/stream (SSE), GET/PATCH /requests[/{id}]
  (status, assigned_to → audit_log), GET/PATCH /signals[/{id}], GET /prices/series
  (product_id&market&grade_id&from&to), GET/PATCH /sources[/{id}], POST /sources (admin),
  GET /alerts, GET/POST/PATCH /alert-rules, GET /counterparties, POST /counterparties/{id}/merge,
  GET /counterparties/candidates, POST .../confirm, GET /reports, POST /reports/{id}/approve|reject
  (P2, analyst+), POST /auth/login, POST /auth/refresh, GET /admin/users (CRUD admin),
  GET /health, POST /telegram/webhook/{secret}.
  Auth: dashboard JWT (access 15 min + refresh 7 d httpOnly); Web App X-Telegram-Init-Data,
  HMAC validation per request, initData TTL 24 h. SSE for live, polling 30 s fallback, no WebSocket.

## C-alert-engine — Alert engine contract
- type: protocol
- source: docs/polymer-intelligence-dev-spec.md (§3.3)
- content: evaluate_alert_rules(signal_id|request_id) after entity creation. Rule = JSONB
  condition, hardcoded interpreter (NOT eval); Phase-1 predicates: kind[], product_id[],
  volume_gte, urgency_in[], lead_score_gte, source_kind[]. Match → alerts
  (dedupe_key rule:{rule_id}:{entity}:{id}) → deliveries → send_delivery. Rate limit: global token
  bucket 25 msg/s per bot, 1 msg/s per chat_id. price_spike (P2): beat task after nightly
  aggregation, |Δ day/day| over price_points > rule threshold.

## C-celery-schedule — Celery queues and beat schedule
- type: protocol
- source: docs/polymer-intelligence-dev-spec.md (§3.4)
- content: Queues ingest, parse (concurrency 5), notify, default. Beat (Asia/Tashkent):
  */15 9-18 * * 1-5 uzex_fetch_offers; 0 * * * * uzex_fetch_contracts + uzex_fetch_deals;
  0 7 * * * fetch_cbu_rates; 30 7 * * * fetch_sunsirs + fetch_dce (P2);
  0 2 * * * aggregate_price_points (yesterday); */5 * * * * check_source_health +
  check_userbot_heartbeat; 0 3 * * * retry_failed_parses (parse_attempts<3);
  0 8 * * 1-5 generate_morning_report (P2). All idempotent (DB-level dedupe).
  Nightly aggregation idempotency: DELETE WHERE observed_on=X AND kind='deal_avg' + recompute in
  one transaction (SPEC §10.4).

## C-report-pipeline — Morning report generation contract
- type: protocol
- source: docs/polymer-intelligence-dev-spec.md (§5)
- content: generate_morning_report: (1) SQL facts for yesterday → data_snapshot jsonb;
  (2) snapshot → Sonnet-class LLM with strict "use ONLY numbers from snapshot" prompt;
  (3) post-validation: every number in text must appear in snapshot (regex) — failure → status
  'draft' + flag (NOT pending_approval); (4) pending_approval → analyst notify → Approve/Reject →
  publish → deliveries to channel; footer always "По данным uzex.uz". No auto-publish transition
  exists in the status machine (code-level, not just UI).

## C-services-layer — Service-layer contracts
- type: protocol
- source: docs/polymer-intelligence-dev-spec.md (§3.1)
- content: request_service (REQ-YYYY-MM-DD-NNNNN via date sequence; status machine
  new→viewed→in_progress→{offer_sent,closed,cancelled}, matched from in_progress/offer_sent;
  history; client notify), signal_service (create from parse, needs_review queue),
  price_service (chart downsampling in SQL: daily points as-is, >1 year → weekly aggregation;
  nightly deals→price_points), counterparty_service (alias_norm normalization: lower, strip
  ООО/MCHJ/ИП/quotes, collapse spaces, uz-lat↔cyr translit; exact → autolink, pg_trgm
  similarity>0.6 → candidate), report_service (P2).

## C-frontend — Frontend constraints
- type: nfr
- source: docs/polymer-intelligence-dev-spec.md (§6); docs/polymer-intelligence-ui-mockups.md (§6)
- content: Dashboard = Next.js (app router), TypeScript strict, TanStack Query, TanStack Table,
  Recharts, shadcn/ui, dark theme per mockups, design tokens in tailwind config (no hardcoded
  colors). Phase-1 pages: /login, /, /requests, /signals, /offers, /prices, /sources (+ add-source
  wizard), /alerts, /admin/users; Phase-2: /reports, /counterparties. SSE hook with
  reconnect/backoff. Web App = React + Vite + @telegram-apps/sdk, honor Telegram theme vars
  (var(--tg-theme-*), NOT hardcoded dark), MainButton/BackButton, zustand state survives minimize,
  react-i18next ru/uz (no full phrases in code), bundle ≤300 KB gzip, react-hook-form + zod.
  Three frontends: public Next.js landing + authenticated Next.js dashboard (may share Next.js app)
  + separate Telegram Web App. UI is the security boundary at the API, not the frontend.

## C-deploy-ops — Deployment & ops constraints
- type: nfr
- source: docs/polymer-intelligence-dev-spec.md (§1, §7)
- content: Containers api, worker, beat, userbot, dashboard, postgres, redis, nginx; Web App built
  as static, served by nginx. ENV (deploy/.env.example): DATABASE_URL, REDIS_URL,
  ANTHROPIC_API_KEY, LLM_EXTRACT_MODEL, LLM_REPORT_MODEL, LLM_DAILY_TOKEN_LIMIT, BOT_TOKEN,
  WEBHOOK_SECRET, TG_API_ID, TG_API_HASH, JWT_SECRET, S3_*, TZ_DISPLAY=Asia/Tashkent, SENTRY_DSN.
  Single VPS (≥4 vCPU/8 GB/80 GB SSD), docker compose, nginx + TLS (certbot). Logs structlog JSON
  → stdout (+ opt Loki); errors → Sentry. Backups pg_dump -Fc daily 03:30, rotate 14 d, weekly
  offsite, restore script deploy/restore.sh (restore test is an acceptance item). CI GitHub Actions
  (ruff, mypy services/+schemas/, eslint+tsc → tests → build); deploy via ssh script
  (docker compose pull && up -d). Alembic via api entrypoint with advisory lock.

## C-testing — Testing strategy constraints
- type: nfr
- source: docs/polymer-intelligence-dev-spec.md (§8)
- content: Unit 90%+ on status machine, alert-rule interpreter, alias normalization, initData
  validation, number generation. UZEX parsers tested on saved HTML fixtures
  (tests/fixtures/uzex/*.html). LLM extraction golden-set tests/fixtures/extraction/*.json via
  `make eval-extraction` (not in CI — costs money); acceptance control samples (TZ §6.3, §6.8)
  run with the same tool. Integration: docker-compose test of raw_item→signal→alert→delivery
  (Telegram + LLM mocked). E2E webapp via Playwright with fake initData (DEV middleware only).
  DoD: code + tests + green CI + updated docs on API/schema-contract changes.
