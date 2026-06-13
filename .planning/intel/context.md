# Context (Intel)

Running notes keyed by topic, captured verbatim-in-spirit from the DOC-typed design source
(plus cross-cutting non-FR context). Domain identifiers preserved.

Primary source: docs/polymer-intelligence-ui-mockups.md (UI / Design Specification, DOC, English).
Design source of truth remains the original mockup images (docs/photo_2026-06-13 17.57.06.jpeg
and siblings); this doc is the textual contract so design survives ingestion. Per TZ §2.3.7,
design is accepted per the provided mockups — new screens beyond those listed are a scope change.

---

## Topic: Project intent (from TZ §1)
- source: docs/polymer-intelligence-tz.md §1, §1.1
- A unified system to collect, structure, and deliver market information on Uzbekistan's domestic
  polymer market. Five components on one backend + one DB: internal dashboard, Telegram Web App,
  Telegram bot, Telegram channel (auto-publish with manual confirmation), data-collection engine.
- The system TRACKS market events, STRUCTURES them, and EXPLAINS price moves by observable factors
  (incl. external context from Phase 2). It does NOT forecast prices, does NOT give trading advice,
  does NOT guarantee market coverage. AI scores (lead score, urgency) are advisory and may err;
  the human makes the final decision.

## Topic: Design system (shared)
- source: docs/polymer-intelligence-ui-mockups.md §1
- Dark, high-contrast theme. Near-black backgrounds (#0B0F14 / #0E1419), elevated cards a step
  lighter (#141A21), hairline borders (#1E2730). Primary accent green (~#22C55E / emerald) —
  primary buttons, active nav, positive trends, logo. Secondary accents blue/purple/amber for
  multi-series charts and category chips.
- Status & urgency color coding (consistent everywhere): Urgency High=red+flame, Medium=amber+people,
  Low=blue+download. Request status New=green-outline chip, Viewed=grey chip, Active=green (offers).
  Alert severity info/warning/critical → blue/amber/red.
- Typography sans-serif, large bold KPI numerals, small muted captions. Iconography = line icons
  (lucide-style). Localization: dashboard chrome English in mockups; client Web App RU (RU/UZ toggle
  per FR-9). Web App MUST honor Telegram theme vars (var(--tg-theme-*)), not a hardcoded dark theme.

## Topic: Surface A — Public landing page
- source: docs/polymer-intelligence-ui-mockups.md §2
- Marketing entry at public domain root. Top nav: logo "Polymer Intelligence"; links Dashboard,
  Market Insights, Request a Product, About Us, Contact; right Login/Dashboard button (green).
- Hero "Real-time Polymer Market Intelligence" + AI-powered tracking copy across Uzbekistan,
  Central Asia, Turkey, Azerbaijan, Europe; animated globe with region nodes/arcs;
  "AI-POWERED MARKET INTELLIGENCE" tag chip.
- 4 feature cards: Real-time Monitoring, AI-Powered Insights, Global Coverage, Accurate Data.
  CTAs "Go to Dashboard" (green) + "Request a Product" (outline).
- "Request a Product" public lead-capture form: Product*, Grade, Quantity*+unit(MT), Target Price
  (USD), Delivery Terms, Destination Country*, Urgency (Low/Normal/High segmented), Company Name*,
  Your Contact*, Submit Request (green). Web counterpart of the Web App wizard → creates a `requests` row.
- "Sources we monitor" strip lists UZEX, ChemOrbis, Polymerupdate, Argus, Platts, ETS Kazakhstan,
  Petkim, "and more…". NOTE (reconciled in the source doc): paid sources (ChemOrbis/Argus/Platts)
  are out of scope as data inputs per TZ §2.3.5 — shown here as brand/marketing coverage claims only;
  actual Phase-1 ingestion = UZEX + Telegram + free indices. See INGEST-CONFLICTS.md INFO.

## Topic: Surface B — Internal dashboard
- source: docs/polymer-intelligence-ui-mockups.md §3
- Persistent left sidebar, grouped nav: MAIN (Dashboard, Market Overview, Live Market Feed,
  Purchase Requests, Seller Offers, Price Intelligence, Market Analytics, AI Signals),
  REQUESTS (All/My Requests), SOURCES (Exchanges, Websites, Telegram Channels, Data Sources),
  SETTINGS (Alerts, Notifications, Settings). Footer = current user with role.
- Dashboard home: header + date selector + Filters; 5 KPI cards (Total Buyers, Total Sellers,
  Active Requests, Hot Leads with flame, Price Alerts with bell); Live Market Feed panel
  (rows tagged BUYER/SELLER/REQUEST, source v_live_feed); Price Trends (USD/MT) multi-series line
  chart (PP Raffia, HDPE, PET, PVC; source price_points, Recharts); Top Buyer Requests; Top Seller
  Offers; AI Market Signals list.
- Purchase Requests screen (flagship): header + Search/Export/Settings + "● Live Data";
  filter bar (Period, Product, Region, Source, More Filters); 6 KPI cards (Total Requests +
  sparkline, Total Volume MT + sparkline, Avg Target Price + sparkline, Hot Requests, Sources,
  Updated); paginated requests table (10/page) columns Time, Product, Grade/Type, Volume,
  Target Price, Region/Delivery (Incoterm), Source, Urgency chip, Status chip; rows → right detail
  panel. Detail panel: NEW REQUEST badge + ID (e.g. REQ-2024-05-23-00125 "PP Raffia · H030 SG"),
  Request Details (Volume, Target Price, Delivery Terms, Destination, Required Date, Payment Terms,
  Additional Info), Source Information (Source, Posted Time, Detected Time), AI Analysis
  (Match Score 92% + bar, Price Analysis, Demand Level, Recommendation; source requests.ai),
  Actions (Contact Buyer green, Add Note outline, Mark as Processed) all → audit_log per FR-11.
- Other Phase-1 pages (dev-spec §6.1 consistent): /login, /, /requests, /signals (needs_review),
  /offers (signals kind='sell_offer'), /prices, /sources (add-source wizard: pick type → auto-form
  from adapter config_schema → Test with ≤10-row preview → enable; enable blocked until test passes),
  /alerts (+ rules), /admin/users; Phase-2 /reports (approve flow), /counterparties (+ candidates).

## Topic: Surface C — Telegram Web App (clients)
- source: docs/polymer-intelligence-ui-mockups.md §4
- React + Vite + @telegram-apps/sdk; auth via initData; MainButton "Далее/Отправить",
  BackButton for steps; zustand state survives minimize. 5 mockup screens:
  1) Home/welcome (logo, "Добро пожаловать!", Быстро/Удобно/Надёжно value props, "Оставить заявку"
     green + "Мои заявки" secondary).
  2) New request step 1 (product): indicator 1·2·3·4; Продукт*, Марка/Grade, Тип полимера,
     Количество (Объём* + unit MT), Целевая цена (USD).
  3) New request step 2 (delivery): Incoterms*, Страна назначения*, Порт/Город, Желаемая дата,
     Срок действия (default 30 дней).
  4) New request step 3 (extra): Комментарий, Загрузить файлы (PDF/Excel/JPG up to 10 MB).
  5) Confirmation step 4: green check, "Заявка отправлена!", REQ-YYYY-MM-DD-NNNNN, creation date,
     status chip "Новая заявка", buttons "Мои заявки" / "Создать ещё одну".
- Additional screens (FR-7..FR-9): Мои заявки (list + status history), request detail, Уведомления,
  Новости (Phase 2), профиль/язык (RU/UZ).

## Topic: Screen → data mapping (UI consolidated)
- source: docs/polymer-intelligence-ui-mockups.md §5; docs/polymer-intelligence-db-architecture.md (Маппинг на экраны)
- Landing "Request a Product" form → POST → requests (+clients). Live Market Feed → v_live_feed.
  Price Trends → price_points. Top Buyer Requests/Hot Leads → signals/requests ORDER BY
  ai->>'lead_score'. Top Seller Offers → signals WHERE kind='sell_offer'. AI Market Signals →
  signals.ai / alerts. Purchase Requests table+detail → requests + clients + request_files;
  AI from requests.ai. Sources screen → sources (health fields, last_test_ok_at, adapter
  config_schema). Alerts + rules → alerts, alert_rules, deliveries. Web App wizard → requests +
  request_files + request_status_history. Web App "Мои заявки" → requests by client from initData.
  Web App "Новости" (P2) → reports WHERE status='published'.

## Topic: Design-derived planning constraints
- source: docs/polymer-intelligence-ui-mockups.md §6
- Three frontends ship: (A) public Next.js landing, (B) authenticated Next.js dashboard
  (may share the Next.js app with A), (C) separate Telegram Web App (React+Vite).
- Every list/table screen needs real-time refresh (SSE /feed/stream, polling ≤30 s fallback).
  Purchase Requests master-detail is the highest-fidelity Phase-1 dashboard deliverable.
  The add-source wizard (auto-form from adapter config_schema + mandatory Test preview) is a
  first-class UI deliverable (FR-22, dev-spec §2.5/§6.1). Web App bundle ≤300 KB gzip; forms via
  react-hook-form + zod; i18n react-i18next (ru/uz). Money shown per-MT with currency; original
  currency preserved, conversion shown on read.

## Topic: Fixed assumptions / scope boundaries (TZ §2.3, §2.4)
- source: docs/polymer-intelligence-tz.md §2.3, §2.4
- Changing any assumption = scope + estimate change. Key ones:
  1) Client request replies are done manually by a manager in Telegram; system only records status
     change; internal "offers to clients" module is OUT of scope. 2) Request files: original PRD
     said store as telegram_file_id, download to storage on first open — REFINED by dev-spec §4.2
     to direct upload to S3/MinIO with telegram_file_id as fallback (see DEC-file-storage; treated
     as clarification, not contradiction). 3) Reports RU-only in Phases 1-2; UZ version separate
     task. 4) Channel list provided by customer (up to 20 in Phase 1). 5) Paid international sources
     (ChemOrbis, Argus, Platts, Polymerupdate, ETS) fully out of scope. 6) "hot buyers / cycles /
     anomalies" AI = Phase 3, separate estimate after ≥3 months of data. 7) Design per provided
     mockups; new screens = scope change. 8) ETS Kazakhstan: Phase 2 starts with verification;
     if no usable data, component dropped without re-pricing the rest. 9) Turkey limited to public
     TG channels. 10) SOCAR Polymer etc. publish no public price lists. 11) Source-builder no-code
     boundary: public TG channels, public pages without auth/JS, RSS, simple HTML tables only.
- Explicitly out of scope: price forecasting, trading advice, counterparty creditworthiness scoring;
  native iOS/Android apps (Telegram Web App only); 1C/CRM/payment integrations; monitoring private
  channels/chats without owner consent; SLA on external-source availability (best effort).

## Topic: Timeline & risk allocation (TZ §7, §8)
- source: docs/polymer-intelligence-tz.md §7, §8; docs/polymer-intelligence-dev-spec.md §9, §10
- Staged timeline: Stage 0 prep (1 wk), 1 data core (2 wk), 2 client loop (2 wk), 3 dashboard
  (2 wk), 3a source-builder (1 wk), 4 channel monitoring (1.5 wk), Phase-1 acceptance (0.5 wk),
  5 Phase-2 (5-6 wk). Phase 1 ≈ 10 weeks, Phase 2 ≈ +5-6 weeks; valid only if access provided in
  Stage 0 and customer answers ≤2 business days. Support is a mandatory separate monthly contract
  (collector fixes, userbot rotation, prompt tuning, channel additions, monitoring).
- Risk allocation (for contract): data sources limited to open uzex.uz (with mandatory
  attribution), agreed public TG channels, free open indices (SunSirs, DCE), official CBU rates,
  own client data. Userbot account restrictions risk borne by customer (account provided by them).
  Source-layout changes break collectors → fixed under support, not a warranty defect. AI quality
  thresholds fixed in §6; beyond = iterative improvement under support. Published-content
  responsibility lies with the customer who confirms publication.
- Dev epics (dev-spec §9): E1 scaffold, E2 ingest core + UZEX, E3 client loop, E4 dashboard,
  E4a source-builder, E5 TG monitoring, E6 acceptance; Phase 2 E7 reports, E8 external indices,
  E9 international channels, E10 counterparties.

## Topic: Deliverables (TZ §9)
- source: docs/polymer-intelligence-tz.md §9
- Source code (repo), docker-compose for deployment, DB migrations, deployment + restore docs,
  prompt and extraction-JSON-schema descriptions, admin instructions (sources, alert rules,
  report confirmation).
