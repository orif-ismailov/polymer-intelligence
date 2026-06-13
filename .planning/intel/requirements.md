# Requirements (Intel)

Requirements extracted from the client PRD (TZ). Domain identifiers (FR-IDs, ENUM values,
endpoint paths, REQ-number format, Incoterms, table names) are preserved verbatim.

Source PRD: docs/polymer-intelligence-tz.md (ТЕХНИЧЕСКОЕ ЗАДАНИЕ v1.0, status "на согласование")

Each requirement keeps its original FR-ID and derives a REQ-{slug}. Acceptance criteria are
drawn from TZ §6 (Критерии приёмки) where applicable; otherwise from the FR text and NFRs.
No competing acceptance variants exist (single-PRD ingest).

Phase tags: P1 = Фаза 1 (MVP), P2 = Фаза 2.

---

## Data collection

### REQ-uzex-parser (FR-1) — P1
- source: docs/polymer-intelligence-tz.md §4.1 FR-1
- description: Parse listed uzex.uz sections (offers in sum/currency/import, quotation lists,
  registry of concluded deals) every 15 min during trading hours (Mon-Fri 09:00-18:00
  Asia/Tashkent) and hourly otherwise. Extract: product name, grade (text), volume, price,
  currency, section, counterparties (if published), datetime. Polymer-relevant positions
  (products + synonyms) create signals; others stored in raw_items with status 'irrelevant'.
  Unrecognized goods go to a manual-classification queue (no source_failure alert).
- acceptance: TZ §6.1.2 — polymer positions from a test trading day present in signals with
  correct fields; control sample ≥50 positions, accuracy ≥95%.
- scope: ingest/uzex

### REQ-telegram-monitoring (FR-2) — P1
- source: docs/polymer-intelligence-tz.md §4.1 FR-2
- description: Userbot (MTProto) reads new messages from 10-20 agreed public channels.
  Each message → raw_items → LLM classify relevant/not → on relevance, extract signal
  structure (type, product, grade, volume, price, counterparty, urgency). Customer-provided
  dedicated account; Telegram-restriction risk borne by customer.
- acceptance: TZ §6.1.3 — control sample of 100 channel messages (customer-prepared):
  relevant-signal detection recall ≥80%, field-extraction precision on detected ≥85%.
  LLM errors beyond these thresholds are NOT defects.
- scope: userbot + parsing

### REQ-international-feed (FR-3) — P2
- source: docs/polymer-intelligence-tz.md §4.1 FR-3
- description: (a) Daily import of SunSirs prices (PP, HDPE, LDPE, LLDPE, PVC, PET — China)
  and DCE futures settlement prices (PP, LLDPE) into price_points. (b) Monitor up to 15 public
  RU/KZ/TR trader Telegram channels in the shared pipeline; extraction works on RU/EN/TR;
  signals tagged with source region. (c) ETS Kazakhstan after verification (assumption 8):
  weekly import of EAEU price indicators for polymer positions. Any external-source outage →
  skip period, alert team, reports publish without that block.
- acceptance: TZ §6.2.7 — when SunSirs unavailable, report publishes without external block, no
  errors. TZ §6.2.8 — control sample of 50 international messages (RU/TR): recall ≥75%,
  precision ≥80% (lower than Phase 1 due to multilingual).
- scope: ingest/sunsirs, ingest/dce, ETS verification, international channels

### REQ-fx-rates (FR-4) — P1
- source: docs/polymer-intelligence-tz.md §4.1 FR-4
- description: Daily import of official CBU RUz (ЦБ РУз) rate; conversion shown in UI next to
  original currency; original always preserved (fx_rates table; conversion computed on read).
- scope: ingest/cbu_rates, fx_rates table

## Web App (client)

### REQ-webapp-auth (FR-5) — P1
- source: docs/polymer-intelligence-tz.md §4.2 FR-5
- description: Authorization via Telegram initData (backend signature verification); first
  login creates a clients row.
- scope: webapp auth

### REQ-request-wizard (FR-6) — P1
- source: docs/polymer-intelligence-tz.md §4.2 FR-6
- description: 4-step request wizard per mockups: (1) product/grade/type, (2) volume + target
  price, (3) delivery terms: Incoterms, country, port/city, desired date, validity, (4) comment
  + files (PDF/Excel/JPG, up to 10 MB, up to 5 files). Confirmation with number
  REQ-ГГГГ-ММ-ДД-NNNNN (REQ-YYYY-MM-DD-NNNNN).
- acceptance: TZ §6.1.1 — request submitted via Web App appears in dashboard ≤10 s.
- scope: webapp wizard, requests table

### REQ-my-requests (FR-7) — P1
- source: docs/polymer-intelligence-tz.md §4.2 FR-7
- description: List of client's requests with current statuses and history; bot push on status change.
- acceptance: TZ §6.1.1 — status change delivers client notification ≤30 s.
- scope: webapp, bot notifications

### REQ-webapp-news (FR-8) — P2
- source: docs/polymer-intelligence-tz.md §4.2 FR-8
- description: Feed of published reports in the Web App.
- scope: webapp, reports (status='published')

### REQ-webapp-i18n (FR-9) — P1
- source: docs/polymer-intelligence-tz.md §4.2 FR-9
- description: RU/UZ languages; toggle in settings; default detected from Telegram language_code
  on first login.
- scope: webapp i18n

## Dashboard (internal)

### REQ-live-feed (FR-10) — P1
- source: docs/polymer-intelligence-tz.md §4.3 FR-10
- description: Unified feed (v_live_feed) with filters: period, product, signal type, source,
  urgency; updates without reload (polling ≤30 s or SSE).
- acceptance: TZ §5 NFR — feed/table API response ≤500 ms at up to 1M signals.
- scope: dashboard feed

### REQ-purchase-requests (FR-11) — P1
- source: docs/polymer-intelligence-tz.md §4.3 FR-11
- description: Requests table + detail card: details, files, AI block (score, target-vs-avg
  price from price_points), actions: status change, assign owner, notes. All actions → audit_log.
  This is the flagship Phase-1 dashboard screen (master-detail).
- scope: dashboard requests, audit_log

### REQ-price-trends (FR-12) — P1/P2
- source: docs/polymer-intelligence-tz.md §4.3 FR-12
- description: Price chart per product/market from price_points; Phase 2: external-index overlay.
- scope: dashboard prices

### REQ-sources-health (FR-13) — P1
- source: docs/polymer-intelligence-tz.md §4.3 FR-13
- description: Source state: last successful fetch, consecutive failure count, enable/disable.
- scope: dashboard sources

### REQ-alerts (FR-14) — P1
- source: docs/polymer-intelligence-tz.md §4.3 FR-14
- description: Alert feed; rules builder (product, volume/price threshold, urgency, delivery channels).
- scope: dashboard alerts, alert_rules

### REQ-roles (FR-15) — P1
- source: docs/polymer-intelligence-tz.md §4.3 FR-15
- description: Roles — admin (all + users), analyst (data + rules + report approval),
  trader (view + work requests), viewer (view only). ENUM staff_role: admin/analyst/trader/viewer.
- scope: authz

## Bot & publishing

### REQ-bot-team (FR-16) — P1
- source: docs/polymer-intelligence-tz.md §4.4 FR-16
- description: Deliver alerts to DM/group per rules; Telegram rate limit respected via queue
  (deliveries table).
- scope: bot, deliveries

### REQ-bot-clients (FR-17) — P1
- source: docs/polymer-intelligence-tz.md §4.4 FR-17
- description: Greeting, Web App button, status notifications to clients.
- scope: bot

### REQ-reports (FR-18) — P2
- source: docs/polymer-intelligence-tz.md §4.4 FR-18
- description: Generate morning report by 08:30 Asia/Tashkent: yesterday's UZEX prices (Δ vs
  prior day), request count/structure, notable signals, external context. Draft appears in
  dashboard; channel publish ONLY after analyst/admin presses "Подтвердить". No auto-publish.
  Each publication includes attribution "По данным uzex.uz" (source requirement).
- acceptance: TZ §6.2.6 — morning draft formed by 08:30; nothing goes to channel without
  confirmation.
- scope: reports, approve-flow

## AI processing

### REQ-ai-extraction (FR-19) — P1
- source: docs/polymer-intelligence-tz.md §4.5 FR-19
- description: Structure channel messages and free-text requests per a fixed JSON schema;
  prompt version and model journaled (parse_runs).
- scope: parsing/llm_extract

### REQ-lead-scoring (FR-20) — P1
- source: docs/polymer-intelligence-tz.md §4.5 FR-20
- description: lead_score (0-1) and HOT/MEDIUM/LOW classification by rules + LLM; formula/prompt
  agreed with customer; stored in signals.ai / requests.ai; recomputed on prompt-version change.
- scope: scoring

### REQ-llm-budget (FR-21) — P1
- source: docs/polymer-intelligence-tz.md §4.5 FR-21
- description: Configurable daily token limit; on exceed extraction degrades to rule-based +
  reprocessing queue, admin alerted.
- scope: cost control (see DEC-llm-budget-degradation)

### REQ-source-builder (FR-22) — P1
- source: docs/polymer-intelligence-tz.md §4.5 FR-22, §2.1
- description: Admin adds a source via a dashboard wizard: pick type (telegram_channel /
  llm_page / html_table / rss) → fill form → test run with extracted-record preview → enable.
  Enabling without a successful test is impossible. AI sources show token spend. New-source data
  flows through the common pipeline (raw layer, dedupe, signals, alerts) without code changes.
  Builder boundaries per assumption 11 (no auth, no JS render, no captcha for no-code types).
- acceptance: TZ §6.1.6 — admin adds a new public site + new Telegram channel without a
  developer; their signals appear in the feed; a source with a failed test cannot be enabled.
- scope: source-builder (see DEC-source-adapter-registry, DEC-test-before-enable)

## Phase-2 additional

### REQ-counterparty-linking — P2
- source: docs/polymer-intelligence-tz.md §2.2
- description: Semi-automatic counterparty linking: candidates by aliases, analyst confirmation
  in dashboard (counterparties + counterparty_aliases; pg_trgm similarity >0.6 → candidate).
- scope: counterparty resolution

### REQ-intraday-channel-alerts — P2
- source: docs/polymer-intelligence-tz.md §2.2
- description: Publish selected alerts to a public channel via a dashboard button.
- scope: alerts → channel publishing

## Non-functional requirements (NFRs)

### REQ-nfr-performance — P1
- source: docs/polymer-intelligence-tz.md §5
- description: Dashboard feed/tables API ≤500 ms at up to 1M signals; Web App first paint ≤3 s on 3G;
  Web App bundle ≤300 KB gzip (dev-spec §6.2).

### REQ-nfr-reliability — P1
- source: docs/polymer-intelligence-tz.md §5; §6.1.4-5
- description: Worker auto-restart; daily PostgreSQL backup (pg_dump) retained 14 days + weekly
  full retained 8 weeks; documented restore procedure. One source's failure must not break others;
  failure alert ≤30 min (TZ §6.1.4). DB restore on a clean server per docs ≤2 hours (TZ §6.1.5).

### REQ-nfr-security — P1
- source: docs/polymer-intelligence-tz.md §5
- description: HTTPS everywhere; secrets in .env outside repo; initData signature verification;
  argon2 password hashing; dashboard access by account only; audit_log on all request changes
  and publications.

### REQ-nfr-observability — P1
- source: docs/polymer-intelligence-tz.md §5
- description: Structured logs; alert when any collector fails >3 consecutive cycles; /health page.

### REQ-nfr-time-localization — P1
- source: docs/polymer-intelligence-tz.md §5
- description: All timestamps UTC in DB, display in Asia/Tashkent.
