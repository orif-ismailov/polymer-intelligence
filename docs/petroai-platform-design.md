# PetroAI Platform — Design & Architecture

> Status: **proposal / v2 direction**. This document maps the "PetroAI — вся платформа
> в одном приложении" vision (buyer + seller marketplace, news bot, internal AI broker
> dashboard) onto the existing Polymer Intelligence codebase. It marks every piece as
> **REUSE** (already built), **EXTEND** (small change to existing), or **NEW** (net-new
> subsystem) so scope is honest.

## 1. Vision in one paragraph

PetroAI is **not** an Alibaba-style open marketplace. It is an **AI-assisted petrochemical
broker + market-intelligence system** for Uzbekistan / Central Asia, delivered through one
Telegram Mini App, a Telegram news channel + bot, and an internal AI dashboard for the sales
team. Buyers submit **private** purchase requests; sellers publish **moderated, public**
catalog offers; AI runs a daily market-intelligence report and, per buyer request, an internal
**supplier tender** following a fixed business-priority waterfall. The sales team closes deals.

## 2. How it maps to what already exists

| Capability | Status | Where |
|---|---|---|
| Ingest engine (UZEX, CBU FX, RSS, Telegram channels, HTML/LLM pages) | **REUSE** | `backend/app/ingest/`, Celery `ingest`/`parse` |
| Normalized `signals` stream incl. `sell_offer`/`buy_request`/`deal`/`price_quote`/`news` | **REUSE** | `app/models/signals.py`, `enums.py` |
| LLM extraction + daily token budget + nightly catch-up | **REUSE** | `backend/parsing/`, `LLM_REPORT_MODEL=claude-sonnet-4-5` already set |
| Price series + FX conversion + price analysis | **REUSE** | `services/price_analysis_service.py`, `fx_service.py`, `prices.py` |
| **News engine** (reports: draft→pending→approved→published, `content_md`, human-in-loop) | **REUSE/EXTEND** | `app/models/reports.py` — exactly the daily-report model |
| Buyer requests (table, status machine, AI analysis JSONB, files, SLA) | **REUSE/EXTEND** | `app/models/requests.py`, `services/request_analysis_service.py` |
| Counterparties with `buyer/seller/trader/producer` roles + alias resolution | **REUSE** | `app/models/counterparties.py` |
| File storage (S3/MinIO, TDS/cert uploads) | **REUSE** | `services/storage_service.py`, `api/webapp/files.py` |
| aiogram bot + webhook + templates (ru/uz/tr) | **REUSE/EXTEND** | `telegram/` |
| Internal dashboard (Next.js, live feed/SSE, alerts, prices, requests) | **REUSE/EXTEND** | `dashboard/` |
| Telegram Web App wizard (buyer request submission) | **EXTEND** | `webapp/` — becomes one tab of the unified app |
| RBAC staff auth + Telegram initData auth | **REUSE** | `api/deps.py`, `core/security.py` |
| **Seller accounts + published offers + moderation** | **NEW** | §6 `sellers`, `seller_offers` |
| **Public marketplace catalog** (browse/search/product card) | **NEW** | §7 API + §8 Mini App screens |
| **Internal inventory** | **NEW** | §6 `inventory_items` |
| **AI sourcing/tender engine** (priority waterfall) | **NEW** | §10 |
| **Market-intelligence analytics** (spread, supply-demand gap) | **EXTEND** | builds on `dashboard_summary_service.py` |
| **News channel auto-publish + subscription** | **NEW/EXTEND** | §11 |

**Bottom line:** the intelligence half is largely done. The net-new work is the **seller
marketplace**, **internal inventory + sourcing waterfall**, and the **unified Mini App shell**.

## 3. Information architecture (unified Mini App)

Per IMG_0046 the Mini App is one app with a **bottom tab bar**:

```
┌ Маркет ─ Заявки ─ [ Продать ] ─ Новости ─ Профиль ┐
   catalog   buyer-req  seller-offer  news-feed  profile
```

- **Маркет (Market):** public seller-offer catalog — search, category chips
  (HDPE/PP/LDPE/PVC/PET), product cards with price, qty, seller, location, contacts.
- **Заявки (Requests):** the buyer's own purchase requests (private) + the submit wizard.
- **Продать (Sell):** the seller listing wizard (5 steps → moderation).
- **Новости (News):** daily AI market reports rendered in-app (same content as the channel).
- **Профиль (Profile):** company/contact info, language (ru/uz/en), role preference.

**Reconciling "choose user type on the first screen":** first run shows a lightweight
**role hint** (Buyer / Seller) that sets the default landing tab and what we surface first.
It is *not* a hard gate — every tab stays reachable, matching "вся платформа в одном
приложении". The choice is stored on the client profile (`clients.role_pref`).

## 4. Roles & visibility rules (load-bearing)

- **Buyer requests are PRIVATE** — visible only to internal staff + AI dashboard. Sellers
  never see them. (Enforced server-side: no buyer-request data on any public/seller endpoint.)
- **Seller offers are PUBLIC after moderation** — visible to all Mini App users, contacts
  included (industry norm; spec §4).
- **News channel is news-only** — no buyer requests or seller offers are ever published there.
- Internal sourcing results (inventory, partner/import pricing, margins) are **staff-only**.

## 5. Full user flows

### 5.1 Buyer
1. Open Mini App → (first run: pick "Buyer") → **Заявки** tab → "Оставить заявку".
2. Wizard (5 steps, per IMG_0046 — extends today's 3-step wizard):
   1. Product info — product (or **free-text** if not in catalog), grade, type, volume+unit.
   2. Delivery terms — delivery city, required date, urgency (срочно 1–3 / week / month / import 14–25).
   3. Contact — company, contact person, **phone (mandatory)**, Telegram (auto from initData), city, legal address.
   4. Additional — desired price (optional), **TDS upload** (optional), comment.
   5. Confirm → submit.
3. Confirmation screen: "Заявка принята. AI проанализирует рынок и проведёт внутренний тендер…"
4. Request enters internal dashboard as `status=new`; AI sourcing runs (§10); sales contacts buyer.

### 5.2 Seller
1. Open Mini App → (first run: "Seller") → **Продать** tab → listing wizard (5 steps):
   product/grade → qty available, price, currency → photos + TDS/cert + description → contact + min order → **submit to moderation**.
2. Offer `status=pending_moderation`. Staff approve/reject in dashboard.
3. Approved → appears in **Маркет** catalog; seller sees it in their profile.

### 5.3 News subscriber
1. Subscribe to the channel / start the bot → receive the daily branded report automatically.
2. Tap "Открыть Mini App" / "Оставить заявку" inline buttons → deep-link into the app.

### 5.4 Internal sales (dashboard)
1. New buyer request arrives → AI sourcing waterfall produces ranked options (§10).
2. Manager reviews inventory vs partner vs marketplace vs import, picks an option, contacts buyer, advances request status.

## 6. Database structure

All new tables follow existing conventions: SQLAlchemy 2 ORM in `app/models/`, registered in
`app/models/__init__.py` (FK order), `(str, Enum)` PG enums in `enums.py`, Alembic migration
`0006_petroai_marketplace.py`. **Extends** are additive columns (nullable / server_default).

### EXTEND existing
- `clients`: add `role_pref ENUM(buyer,seller,both) NULL`, `legal_address TEXT NULL`.
- `requests`: snapshot `company_name`, `contact_name`, `phone` at submit time (today they live
  only on `clients`); add `product_text TEXT NULL` for free-typed products not in the catalog;
  `delivery_city` already covered by `port_or_city`. The `ai` JSONB already holds match/sourcing output.

### NEW tables
```
sellers
  id, counterparty_id FK→counterparties NULL,  -- link into intelligence loop
  telegram_user_id BIGINT, company_name, contact_name, phone, telegram_username,
  country CHAR(2), is_verified BOOL, is_blocked BOOL, created_at

seller_offers                                   -- moderated public listings
  id, seller_id FK→sellers, product_id FK→products NULL, product_text NULL,
  grade_text, polymer_type, qty_available NUMERIC, qty_unit,
  price NUMERIC, currency CHAR(3), incoterms price_basis, warehouse_city, country CHAR(2),
  min_order_qty NUMERIC NULL, description TEXT NULL,
  status ENUM(draft,pending_moderation,approved,rejected,archived),
  moderated_by FK→staff_users NULL, moderation_note TEXT NULL,
  published_at, created_at, updated_at
  -- on approve: also emit a signals row (kind=sell_offer) for analytics parity

seller_offer_files                              -- images, TDS, quality cert
  id, offer_id FK→seller_offers, kind ENUM(image,tds,certificate,other),
  file_name, mime_type, size_bytes, storage_path, created_at

inventory_items                                 -- our own stock (sourcing priority #1)
  id, product_id FK→products, grade_text, qty_on_hand NUMERIC, qty_unit,
  cost_price NUMERIC, currency, warehouse_city, updated_at

partner_suppliers                               -- known partner pricing (priority #2)
  id, counterparty_id FK→counterparties, product_id FK→products NULL,
  indicative_price NUMERIC, currency, lead_time_days, incoterms, notes, updated_at

sourcing_runs                                   -- audit of each AI tender for a request
  id, request_id FK→requests, prompt_version, model,
  result JSONB,  -- ranked options: inventory/partner/marketplace/import + market avgs
  created_at
```
New enums: `SellerOfferStatus`, `OfferFileKind`, `ClientRolePref`. (Reuse `PriceBasis`,
`PricePointKind`, `ReportKind/Status`.)

### Marketplace ↔ intelligence bridge
An approved `seller_offer` also writes a `signals` row (`kind=sell_offer`, linked back) so the
existing analytics/alerts/price-series machinery counts user offers automatically — no parallel
analytics stack.

## 7. API architecture

All under `/api/v1`, new routers in `app/api/` (mounted in `create_app()`), Pydantic schemas in
`app/schemas/`. Auth as today: staff = JWT/RBAC; Mini App = `X-Telegram-Init-Data` HMAC.

### Public / Mini App (initData auth)
```
GET    /webapp/market/offers           # catalog: filters product/category/city/price, paginated
GET    /webapp/market/offers/{id}      # product card (public, contacts included)
GET    /webapp/market/categories       # category chips + counts
POST   /webapp/requests                # EXTEND existing buyer-request create (5-step payload)
GET    /webapp/requests                # caller's own requests (private)
GET    /webapp/requests/{id}           # own request detail + status history
POST   /webapp/seller/offers           # create draft → submit to moderation
GET    /webapp/seller/offers           # caller's own offers (any status)
PATCH  /webapp/seller/offers/{id}      # edit while draft/rejected
POST   /webapp/seller/offers/{id}/files
GET    /webapp/news                    # published reports (news feed)
GET    /webapp/news/{id}
GET/PATCH /webapp/me                   # profile incl. role_pref, language
```
### Internal dashboard (JWT/RBAC)
```
GET    /admin/moderation/offers        # queue of pending_moderation
POST   /admin/moderation/offers/{id}/approve | /reject
GET    /admin/requests                 # all buyer requests (private) + sourcing result
POST   /admin/requests/{id}/source     # (re)run AI sourcing waterfall → sourcing_runs
GET    /admin/inventory  POST/PATCH …  # inventory CRUD
GET    /admin/partners   POST/PATCH …  # partner-supplier CRUD
GET    /admin/intel/market             # spread / supply-demand gap / popular products
GET    /admin/reports  POST /admin/reports/{id}/approve|publish   # EXTEND news engine
```

## 8. Mini App screens (wireframe specs)

Visual reference = the three provided mockups. Build in `webapp/` (Vite + react-router +
zustand + i18next). New route stacks under the tab shell:

- `MarketTab`: `MarketList` (search bar, category chips, offer cards) → `OfferDetail` (gallery,
  specs table, seller block, TDS download, "Запросить предложение" → prefilled buyer wizard).
- `RequestsTab`: `MyRequests` (existing) + `RequestWizard` (extend store to 5 steps + new fields).
- `SellTab`: `SellWizard` (5 steps) + `MySellerOffers` (status badges: на модерации/опубликовано/отклонено).
- `NewsTab`: `NewsFeed` (report list) → `ReportView` (markdown render of `content_md`).
- `ProfileTab`: company/contact/legal address, language switch, role preference.
- `AppShell`: bottom tab bar + first-run role hint modal.

State: extend `wizardStore` (buyer) + add `sellWizardStore`; persist `role_pref` locally.
i18n: add ru/uz/**en** strings (spec adds English to the existing ru/uz/tr set).

## 9. Internal dashboard screens (Next.js)

Extend `dashboard/app/[locale]/(dashboard)/`:
- `sourcing/` — buyer request + AI sourcing result side-by-side (inventory / Seller A,B /
  import option / market averages), "best option" highlighted, contact + advance-status actions.
- `moderation/` — seller-offer approval queue (approve/reject + note).
- `inventory/`, `partners/` — CRUD tables.
- `intel/` — market-intelligence board (Bloomberg-terminal feel): per-product buyers/sellers
  counts, avg seller price, avg buyer target, **spread**, supply-demand gap, trends — extends
  `dashboard_summary_service.py` + `price_analysis_service.py`.
- `reports/` — news report review/approve/publish (extends existing reports/human-in-loop).

## 10. AI workflow

### 10.1 Daily news report (REUSE reports + LLM)
Beat task `generate_daily_report` (new, queue `parse`): aggregate last-24h `prices`/`signals`
per tracked product+region → build `data_snapshot` → `LLM_REPORT_MODEL` (claude-sonnet-4-5,
versioned prompt `report_vN.md`) writes branded `content_md` → `reports` row `status=draft`.
Human approves in dashboard → `publish_report` task posts to the Telegram channel (§11).
Track ~15–30 key products (config-driven list). External providers (Argus/ICIS/ChemOrbis) slot
in later as additional `ingest` adapters — no pipeline change.

### 10.2 Per-request supplier tender (NEW — the broker core)
On new buyer request, `source_request` task runs the **business-priority waterfall** (spec §6):
1. **Own inventory** (`inventory_items`) — match product+grade, qty, cost.
2. **Partner suppliers** (`partner_suppliers`) — indicative price + lead time.
3. **Marketplace** (`seller_offers` approved) — matching live offers.
4. **Import** (manufacturer estimate from intelligence: China/Iran avg + logistics + ~14–25d).
Augment with market context: avg UZ price, avg China price (from `signals`/`prices`). LLM
(claude-haiku for cost, budget-gated like the extractor) ranks + explains; result → `sourcing_runs.result`
and `requests.ai`. Rule-based fallback when budget exhausted (mirrors `parsing/fallback.py`).
**Deterministic priority is enforced in code**, not left to the LLM — AI explains/ranks within
the fixed waterfall.

### 10.3 Market intelligence (EXTEND)
Scheduled rollups → per-product: #buyers (requests), #sellers (offers), avg seller price, avg
buyer target, spread, supply-demand gap, popular products, opportunities. Powers `/admin/intel/market`.

## 11. Telegram bot / channel flow (EXTEND telegram/)

- **Channel:** `publish_report` posts approved reports in the branded format (HTML templates in
  `telegram/templates/{ru,uz,en}/report.txt`) with inline buttons: *Цены на сырьё*, *Аналитика
  рынка*, *Оставить заявку*, *Открыть Mini App* (deep-link, per IMG_0046 right panel).
- **Bot:** `/start` → subscribe to daily intel + WebApp menu button (exists). New: subscription
  prefs, "Открыть Mini App" → Market/Requests deep-link. Outbound buyer status-change DMs already
  exist via the `notify` queue.
- No requests/offers ever posted to the channel (visibility rule §4).

## 12. Phased delivery (suggested)

1. **Unified shell + buyer extension** — tab nav, role hint, 5-step buyer wizard, English locale.
   (Mostly EXTEND; lowest risk.)
2. **Seller marketplace** — `sellers`/`seller_offers`/files, sell wizard, moderation queue,
   public catalog API + Market tab. (Largest NEW chunk.)
3. **News engine surfacing** — daily report generator + channel publish + News tab. (Reuses reports.)
4. **AI broker dashboard** — inventory/partners, sourcing waterfall, market-intel board.

Each phase ships behind the existing CI gates (ruff · mypy · pytest · eslint · tsc · e2e) and
follows repo conventions (immutable raw pipeline, versioned prompts, UTC-store/Tashkent-display,
secrets-from-env). New Celery tasks must be added to `_TASK_MODULES`; new adapters imported in
both `app/main.py` and `app/tasks/ingest.py`.

## 13. Open decisions (need product input)

1. **Seller identity & trust** — self-serve open registration vs. verified-only (`is_verified`
   gate before a seller can publish)?
2. **Buyer↔seller contact** — does the buyer wizard's "Запросить предложение" stay fully
   AI-brokered (private), or also allow direct contact from a public offer card? (Spec says
   requests are private but offer contacts are public — both can coexist.)
3. **English vs Turkish** — spec lists ru/uz/**en**; current stack is ru/uz/**tr**. Add `en`,
   keep `tr`, or replace?
4. **Inventory source of truth** — manual entry in dashboard, or import from an external ERP/1C?
5. **Tracked products list** — the 15–30 products for daily reports: config file or DB-managed?
6. **Channel cadence/format** — one daily report, or also intraday (the `ReportKind` enum already
   has `morning/intraday/weekly`)?
