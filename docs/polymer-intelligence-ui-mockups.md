# Polymer Intelligence — UI / Design Specification

Версия 1.0 · 13.06.2026
Transcribed from the 3 client-provided mockup images (`docs/photo_2026-06-13 17.57.06.jpeg`,
`…08.jpeg`, `…10.jpeg`). This document is the textual contract for the visual design so that
it survives doc ingestion. Source of truth for layout remains the original images; this file
captures structure, components, and the design system for planning. Type: DOC (design). Per
client TZ §2.3.7, design is accepted per the provided mockups — new screens beyond those listed
here are a scope change.

---

## 1. Design system (shared across all surfaces)

- **Theme:** dark, high-contrast. Near-black backgrounds (`#0B0F14` / `#0E1419` range), elevated
  cards a step lighter (`#141A21`), hairline borders (`#1E2730`).
- **Primary accent:** green (`~#22C55E` / emerald) — primary buttons, active nav item, positive
  trends, logo mark.
- **Secondary / data accents:** blue, purple, amber/yellow for multi-series charts and category chips.
- **Status & urgency color coding (consistent everywhere):**
  - Urgency: `High` = red + flame icon, `Medium` = amber + people icon, `Low` = blue + download icon.
  - Request status: `New` = green outline chip, `Viewed` = muted/grey chip; `Active` = green (offers).
  - Alert severity: info / warning / critical map to blue / amber / red.
- **Typography:** sans-serif; large bold numerals for KPI values; small muted captions/labels.
- **Iconography:** line icons (lucide-style) throughout nav and KPI cards.
- **Localization:** dashboard chrome in English in mockups; client Web App in RU (with RU/UZ toggle
  per TZ FR-9). Telegram Web App must honor Telegram theme variables (`var(--tg-theme-*)`), NOT a
  hardcoded dark theme (dev-spec §6.2).
- **Implementation note (dev-spec §6.1):** dashboard = Next.js + Tailwind + shadcn/ui, tables via
  TanStack Table, charts via Recharts. Design tokens (colors) go into Tailwind config at the start —
  do not hardcode colors.

---

## 2. Surface A — Public landing page (mockup 2, top half)

Marketing entry point at the public domain root.

- **Top nav:** logo "Polymer Intelligence"; links: Dashboard, Market Insights, Request a Product,
  About Us, Contact; right-aligned **Login / Dashboard** button (green).
- **Hero:** headline "Real-time Polymer Market Intelligence"; subcopy describing AI-powered tracking
  of buyers, sellers, prices across Uzbekistan, Central Asia, Turkey, Azerbaijan, Europe. Animated
  globe with glowing region nodes (Europe, Uzbekistan, Turkey, Kazakhstan) connected by arcs.
  Tag chip: "AI-POWERED MARKET INTELLIGENCE".
- **Feature cards (4):** Real-time Monitoring (24/7 scanning), AI-Powered Insights (smart analysis
  & alerts), Global Coverage (Central Asia, Turkey, Azerbaijan, Europe), Accurate Data (verified and
  structured).
- **Primary CTAs:** "Go to Dashboard" (green), "Request a Product" (outline).
- **"Request a Product" form (right column, public lead capture):** fields — Product* (select),
  Grade (optional), Quantity* + unit (MT), Target Price (USD, optional), Delivery Terms (select),
  Destination Country* (select), Urgency (Low / Normal / High segmented control), Company Name*,
  Your Contact (Telegram/Email/Phone)*, **Submit Request** (green). This is the web counterpart of
  the Telegram Web App request wizard → creates a `requests` row.
- **"Sources we monitor" strip:** logos/text — UZEX, ChemOrbis, Polymerupdate, Argus, Platts,
  ETS Kazakhstan, Petkim, "and more…". (Note: per TZ §2.3.5 paid sources like ChemOrbis/Argus/Platts
  are out of scope as data inputs — they appear here as brand/marketing coverage claims only; actual
  Phase-1 ingestion is UZEX + Telegram + free indices.)

## 3. Surface B — Internal dashboard (mockups 1 and 2-bottom)

Authenticated team terminal. Persistent **left sidebar** with grouped nav:

- **MAIN:** Dashboard, Market Overview, Live Market Feed, Purchase Requests, Seller Offers,
  Price Intelligence, Market Analytics, AI Signals.
- **REQUESTS:** All Requests, My Requests.
- **SOURCES:** Exchanges, Websites, Telegram Channels, Data Sources.
- **SETTINGS:** Alerts, Notifications, Settings.
- **Footer:** current user (Admin / Administrator) with role.

### 3.1 Dashboard home (mockup 2, bottom half)
- Header "Dashboard — Real-time market overview and intelligence"; date selector; Filters button.
- **KPI cards (5):** Total Buyers (128, +18 today), Total Sellers (215, +24 today), Active Requests
  (32, +7 today), Hot Leads (14, high priority, flame), Price Alerts (8, new alerts, bell).
- **Live Market Feed** panel: rows tagged BUYER / SELLER / REQUEST with product, volume, region,
  target/price, relative time, "View all" link. (Source: `v_live_feed`.)
- **Price Trends (USD/MT)** panel: multi-series line chart (PP Raffia, HDPE, PET, PVC) over a date
  axis, legend, "View all". (Source: `price_points`, Recharts.)
- **Top Buyer Requests** list: ranked product/region/volume/price with urgency chip.
- **Top Seller Offers** list: ranked product/region/volume/price with Active chip.
- **AI Market Signals** list: insight rows (e.g. "High demand detected for PP Raffia in Uzbekistan",
  "Price increase expected for HDPE", "Arbitrage opportunity PP Raffia KZ↔UZ") with icon + time.

### 3.2 Purchase Requests screen (mockup 1) — flagship screen
- Header "Purchase Requests — Real-time buyer requests collected from exchanges, websites and
  channels"; right side: Search, **Export**, Settings; "● Live Data" indicator.
- **Filter bar:** Period (Last 7 days), Product (All Products), Region (All Regions),
  Source (All Sources), **More Filters**.
- **KPI cards (6):** Total Requests (248, +24 today, sparkline), Total Volume (12,540 MT, +1,280 MT,
  sparkline), Avg Target Price ($1,082/MT, −15 vs yesterday, sparkline), Hot Requests (37, high
  priority), Sources (18 active sources), Updated (2 min ago).
- **Requests table** (paginated, 10/page, 248 total): columns — Time (+relative), Product (icon),
  Grade / Type, Volume, Target Price, Region / Delivery (with Incoterm), Source (name + kind),
  Urgency (color chip), Status (chip). Rows clickable → opens right detail panel.
- **Right detail panel** (selected request, e.g. REQ-2024-05-23-00125 "PP Raffia · H030 SG"):
  - Header: NEW REQUEST badge, ID, product title, grade chip, High Priority + New chips, close (×).
  - **Request Details:** Volume, Target Price, Delivery Terms, Destination, Required Date,
    Payment Terms, Additional Info (free text).
  - **Source Information:** Source (name + kind), Posted Time, Detected Time.
  - **AI Analysis:** Match Score (92% with progress bar), Price Analysis (e.g. "3% above market
    average"), Demand Level (High demand), Recommendation (free text). (Source: `requests.ai`.)
  - **Actions:** Contact Buyer (green primary), Add Note (outline), Mark as Processed (full-width).
    All actions write to `audit_log` per TZ FR-11.

### 3.3 Other Phase-1 dashboard screens (from dev-spec §6.1, consistent with above)
`/login`, `/` (home above), `/requests` (above), `/signals` (needs_review filter), `/offers`
(`signals kind='sell_offer'`), `/prices` (Price Trends + Phase-2 external overlay), `/sources`
(health list + **add-source wizard**: pick type → auto-form from adapter `config_schema` → **Test**
button with up-to-10-row preview → enable; enable blocked until a test passes), `/alerts` (+ rules
builder), `/admin/users`. Phase-2: `/reports` (approve flow), `/counterparties` (+ candidates).

## 4. Surface C — Telegram Web App for clients (mockup 3, 5 screens)

React + Vite + `@telegram-apps/sdk`. Auth via Telegram `initData`. Uses Telegram MainButton for
"Далее/Отправить" and BackButton for wizard steps. State in zustand (survives minimize).

1. **Home / welcome:** logo, "Добро пожаловать!", value props (Быстро / Удобно / Надёжно with icons),
   primary "Оставить заявку" (green), secondary "Мои заявки".
2. **New request — step 1 (product):** step indicator 1·2·3·4; "Информация о продукте" —
   Продукт* (select), Марка/Grade (optional), Тип полимера (select), Количество: Объём* + unit (MT),
   Целевая цена (USD, optional). MainButton "Далее".
3. **New request — step 2 (delivery):** "Условия поставки" — Incoterms* (select), Страна назначения*
   (select), Порт/Город (optional), Сроки: Желаемая дата поставки (date), Срок действия заявки
   (default 30 дней). "Далее".
4. **New request — step 3 (extra):** "Дополнительная информация" — Комментарий (optional, textarea),
   Загрузить файлы (optional drag-drop, PDF/Excel/JPG up to 10 MB). "Далее".
5. **Confirmation — step 4:** green check, "Заявка отправлена!", request number (REQ-YYYY-MM-DD-NNNNN),
   creation date, status chip "Новая заявка"; buttons "Мои заявки" and "Создать ещё одну".

Additional Web App screens (TZ FR-7..FR-9): Мои заявки (list + status history), детали заявки,
Уведомления, Новости (Phase 2), профиль/язык (RU/UZ).

---

## 5. Screen → data mapping (consolidated; see db-architecture for full)

| Screen / component | Data source |
|---|---|
| Landing "Request a Product" form | `POST` → `requests` (+ `clients`) |
| Dashboard Live Market Feed | `v_live_feed` |
| Price Trends chart | `price_points` |
| Top Buyer Requests / Hot Leads | `signals`/`requests` ORDER BY `ai->>'lead_score'` |
| Top Seller Offers | `signals WHERE kind='sell_offer'` |
| AI Market Signals | `signals.ai` / `alerts` |
| Purchase Requests table + detail | `requests` + `clients` + `request_files`; AI from `requests.ai` |
| Sources screen (health + wizard) | `sources` (health fields, `last_test_ok_at`, adapter `config_schema`) |
| Alerts + rules | `alerts`, `alert_rules`, `deliveries` |
| Web App request wizard | `requests` + `request_files` + `request_status_history` |
| Web App "Мои заявки" | `requests` by `client` from initData |
| Web App "Новости" (Phase 2) | `reports WHERE status='published'` |

## 6. Design-derived constraints for planning

- Three distinct frontends ship: (A) public Next.js landing, (B) authenticated Next.js dashboard,
  (C) Telegram Web App (React+Vite). Landing + dashboard may share the Next.js app; Web App is separate.
- Every list/table screen needs real-time refresh (SSE `/feed/stream`, polling ≤30 s fallback).
- The Purchase Requests master-detail screen is the highest-fidelity Phase-1 dashboard deliverable.
- The add-source wizard (auto-form from adapter `config_schema` + mandatory Test preview) is a
  first-class UI deliverable, not an afterthought (TZ FR-22, dev-spec §2.5 / §6.1).
- Web App bundle ≤300 KB gzip; forms via react-hook-form + zod; i18n via react-i18next (ru/uz).
- All money shown per-MT with currency; original currency preserved, conversion shown on read.
