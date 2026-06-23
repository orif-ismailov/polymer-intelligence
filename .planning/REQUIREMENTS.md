# Requirements: Polymer Intelligence

**Defined:** 2026-06-13
**Core Value:** Every relevant market event lands accurately and quickly in a single normalized stream the team can see, filter, and act on — with no single source able to take the others down.

> **Current milestone = Client Phase 1 (domestic-market MVP).** All requirements below are registered. Phase-2 international-loop items are tagged **Future Milestone** and are intentionally NOT mapped to any roadmap phase. Domain identifiers (FR-IDs, ENUM values, endpoint paths, table names, Incoterms, REQ-number format) are preserved verbatim.

## v1 Requirements (Client Phase 1)

### Data Collection

- [x] **REQ-uzex-parser** (FR-1): Parse listed uzex.uz sections (offers in sum/currency/import, quotation lists, registry of concluded deals) every 15 min during trading hours (Mon–Fri 09:00–18:00 Asia/Tashkent) and hourly otherwise. Extract product, grade (text), volume, price, currency, section, counterparties (if published), datetime. Polymer-relevant positions → `signals`; others → `raw_items` with status 'irrelevant'; unrecognized goods → manual-classification queue (no source_failure alert). *Acceptance (TZ §6.1.2): control sample ≥50 positions, field accuracy ≥95%.*
- [x] **REQ-fx-rates** (FR-4): Daily import of official CBU RUz rate into `fx_rates`; conversion shown in UI next to original currency; original always preserved (conversion computed on read).

### Web App (Client)

- [x] **REQ-webapp-auth** (FR-5): Authorization via Telegram initData (backend HMAC signature verification per request); first login creates a `clients` row.
- [x] **REQ-request-wizard** (FR-6): 4-step request wizard per mockups — (1) product/grade/type, (2) volume + target price, (3) Incoterms/country/port/date/validity, (4) comment + files (PDF/Excel/JPG, ≤10 MB, ≤5 files). Confirmation with number REQ-YYYY-MM-DD-NNNNN. *Acceptance (TZ §6.1.1): request appears in dashboard ≤10 s.*
- [x] **REQ-my-requests** (FR-7): Client's request list with current statuses + history; bot push on status change. *Acceptance (TZ §6.1.1): status change notification delivered ≤30 s.*
- [x] **REQ-webapp-i18n** (FR-9): RU/UZ languages; toggle in settings; default detected from Telegram language_code on first login.

### Dashboard (Internal)

- [x] **REQ-live-feed** (FR-10): Unified feed (`v_live_feed`) with filters (period, product, signal type, source, urgency); updates without reload (SSE or ≤30 s polling). *Acceptance (TZ §5 NFR): feed/table API ≤500 ms at up to 1M signals.*
- [x] **REQ-purchase-requests** (FR-11): Requests table + detail card (details, files, AI block — score, target-vs-avg price from price_points) + actions (status change, assign owner, notes); all actions → `audit_log`. Flagship Phase-1 master-detail screen.
- [x] **REQ-price-trends** (FR-12): Price chart per product/market from `price_points` (external-index overlay deferred to Phase 2).
- [x] **REQ-sources-health** (FR-13): Source state — last successful fetch, consecutive failure count, enable/disable.
- [x] **REQ-alerts** (FR-14): Alert feed + rules builder (product, volume/price threshold, urgency, delivery channels).
- [x] **REQ-roles** (FR-15): Roles admin / analyst / trader / viewer (ENUM staff_role). admin = all + users; analyst = data + rules + report approval; trader = view + work requests; viewer = view only.

### Bot & Publishing

- [x] **REQ-bot-team** (FR-16): Deliver alerts to DM/group per rules; Telegram rate limit respected via queue (`deliveries` table).
- [x] **REQ-bot-clients** (FR-17): Greeting, Web App button, status notifications to clients.

### AI Processing

- [x] **REQ-ai-extraction** (FR-19): Structure channel messages and free-text requests per a fixed JSON schema; prompt version and model journaled in `parse_runs`.
- [x] **REQ-lead-scoring** (FR-20): lead_score (0–1) and HOT/MEDIUM/LOW by rules + LLM; stored in signals.ai / requests.ai; recomputed on prompt-version change.
- [x] **REQ-llm-budget** (FR-21): Configurable daily token limit (Redis counter); on exceed, extraction degrades to rule-based + reprocessing queue; admin alerted; per-source 7-day token spend visible for AI sources.
- [x] **REQ-source-builder** (FR-22): Admin adds a source via dashboard wizard — pick type (telegram_channel / llm_page / html_table / rss) → auto-built form from adapter config_schema → Test run with extracted-record preview → enable. Enabling without a passing test is impossible; AI sources show token spend; new-source data flows through the common pipeline with no code changes. *Acceptance (TZ §6.1.6): admin adds a public site + Telegram channel with no developer; signals appear in feed; failed-test source cannot be enabled.*

### Telegram Monitoring

- [x] **REQ-telegram-monitoring** (FR-2): Userbot (MTProto) reads new messages from 10–20 agreed public channels → `raw_items` → LLM classify relevant/not → on relevance extract signal structure (type, product, grade, volume, price, counterparty, urgency). *Acceptance (TZ §6.1.3): 100-message control sample — relevant-signal recall ≥80%, field precision on detected ≥85%.*

### Non-Functional Requirements

- [x] **REQ-nfr-performance**: Dashboard feed/tables API ≤500 ms at up to 1M signals; Web App first paint ≤3 s on 3G; Web App bundle ≤300 KB gzip.
- [x] **REQ-nfr-reliability**: Worker auto-restart; daily pg_dump retained 14 d + weekly full retained 8 wk; documented restore. One source's failure must not break others; failure alert ≤30 min (TZ §6.1.4); DB restore on a clean server per docs ≤2 h (TZ §6.1.5).
- [x] **REQ-nfr-security**: HTTPS everywhere; secrets in .env outside repo; initData signature verification; argon2 password hashing; dashboard access by account only; audit_log on all request changes + publications.
- [x] **REQ-nfr-observability**: Structured logs; alert when any collector fails >3 consecutive cycles; /health page.
- [x] **REQ-nfr-time-localization**: All timestamps UTC in DB; display in Asia/Tashkent.

## Future Milestone — Phase 2 (deferred; NOT in current roadmap)

Scoped and acknowledged, but excluded from the current milestone. Moving any of these into scope requires a roadmap update.

### International Content Loop

- **REQ-international-feed** (FR-3): (a) Daily SunSirs + DCE index import into price_points; (b) up to 15 public RU/KZ/TR trader channels in the shared pipeline (RU/EN/TR extraction, region-tagged signals); (c) ETS Kazakhstan weekly import after verification. *Acceptance: TZ §6.2.7–6.2.8 (recall ≥75%, precision ≥80%).*
- **REQ-webapp-news** (FR-8): Feed of published reports in the Web App (reports WHERE status='published').
- **REQ-reports** (FR-18): Morning/weekly report generation; draft → pending_approval → analyst/admin Approve → published → channel delivery (no auto-publish; footer "По данным uzex.uz"). *Acceptance: TZ §6.2.6.*
- **REQ-counterparty-linking**: Semi-automatic counterparty linking — alias candidates (pg_trgm similarity >0.6), analyst confirmation in dashboard.
- **REQ-intraday-channel-alerts**: Publish selected alerts to a public channel via a dashboard button.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Price forecasting / trading advice | System explains observed factors only; AI advisory (TZ §1.1) |
| Counterparty creditworthiness scoring | Not a product goal (TZ §2.4) |
| "Offers to clients" module | Managers reply manually in Telegram; only status recorded (TZ §2.3.1) |
| Native iOS/Android apps | Telegram Web App only (TZ §2.4) |
| Paid sources as data inputs (ChemOrbis, Argus, Platts, Polymerupdate, ETS) | Out of scope; landing strip is marketing only (TZ §2.3.5) |
| 1C / CRM / payment integrations | Out of scope (TZ §2.4) |
| Monitoring private channels without consent | Only agreed public channels (TZ §2.4) |
| SLA on external-source availability | Best-effort only (TZ §2.4) |
| Browser automation (Playwright) for collectors | Escalate to lead if a page needs JS; no unilateral adoption (SPEC §2.1) |
| "Hot buyers / cycles / anomalies" AI analytics | Phase 3, separate estimate after ≥3 months of data (TZ §2.3.6) |

## Traceability

Current milestone (Client Phase 1). Each v1 requirement maps to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-roles | Phase 1 | Complete |
| REQ-nfr-security | Phase 1 | Complete |
| REQ-nfr-observability | Phase 1 | Complete |
| REQ-nfr-time-localization | Phase 1 | Complete |
| REQ-uzex-parser | Phase 2 | Complete |
| REQ-fx-rates | Phase 2 | Complete |
| REQ-sources-health | Phase 2 | Complete |
| REQ-nfr-reliability | Phase 2 | Complete |
| REQ-webapp-auth | Phase 3 | Complete |
| REQ-request-wizard | Phase 3 | Complete |
| REQ-my-requests | Phase 3 | Complete |
| REQ-webapp-i18n | Phase 3 | Complete |
| REQ-bot-clients | Phase 3 | Complete |
| REQ-nfr-performance | Phase 3 | Complete |
| REQ-live-feed | Phase 4 | Complete |
| REQ-purchase-requests | Phase 4 | Complete |
| REQ-price-trends | Phase 4 | Complete |
| REQ-alerts | Phase 4 | Complete |
| REQ-bot-team | Phase 4 | Complete |
| REQ-source-builder | Phase 4 | Complete |
| REQ-telegram-monitoring | Phase 5 | Complete |
| REQ-ai-extraction | Phase 5 | Complete |
| REQ-lead-scoring | Phase 5 | Complete |
| REQ-llm-budget | Phase 5 | Complete |

**Coverage:**

- v1 requirements (Client Phase 1): 24 total (19 functional + 5 NFR)
- Mapped to phases: 24
- Unmapped: 0 ✓
- Phase 6 (Acceptance & Handover) is cross-cutting verification of the above — no net-new requirements.

**Future Milestone (deferred, unmapped by design):** REQ-international-feed, REQ-webapp-news, REQ-reports, REQ-counterparty-linking, REQ-intraday-channel-alerts.

---
*Requirements defined: 2026-06-13*
*Last updated: 2026-06-13 after ingest bootstrap*
