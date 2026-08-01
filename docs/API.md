<!-- generated-by: gsd-doc-writer -->
# API Reference

Polymer Intelligence exposes one FastAPI application (`backend/app/main.py`, `create_app()`).
Every route is mounted under the **`/api/v1`** prefix. This document enumerates every router
registered in `create_app()` — there is no sampling or truncation below; each group lists every
route defined in its router module(s) as of this writing.

For architecture and data-flow context, see [`docs/ARCHITECTURE.md`](ARCHITECTURE.md). For the
env/runtime-settings contract referenced by some endpoints below, see
[`docs/CONFIGURATION.md`](CONFIGURATION.md).

> **Always-current reference:** when `DEBUG=true` (local/dev only — verified in
> `backend/app/main.py`, `create_app()`), the live OpenAPI schema is served at
> `/docs` (Swagger UI), `/redoc` (ReDoc), and `/openapi.json`. In production `DEBUG` is false and
> all three are `None` — the full schema (endpoints, request/response models, security
> requirements) is deliberately not publicly exposed (`WR-03`). This document is the reference of
> record for production.

## Contents

- [Authentication surfaces](#authentication-surfaces)
- [Health](#health)
- [Staff auth](#staff-auth)
- [Public marketplace (anonymous)](#public-marketplace-anonymous)
- [Staff / dashboard — signal feed, requests, sources, alerts, prices](#staff--dashboard--signal-feed-requests-sources-alerts-prices)
- [Staff / admin — users, products, settings, news moderation](#staff--admin--users-products-settings-news-moderation)
- [Staff / admin — marketplace moderation & sourcing](#staff--admin--marketplace-moderation--sourcing)
- [Staff / admin — reports](#staff--admin--reports)
- [Staff / admin — company verification](#staff--admin--company-verification)
- [Staff / admin — contracts, deals, escrow (Deal Lifecycle)](#staff--admin--contracts-deals-escrow-deal-lifecycle)
- [Staff / admin — compliance (substances & licenses)](#staff--admin--compliance-substances--licenses)
- [Staff / admin — lab orders & partners](#staff--admin--lab-orders--partners)
- [Telegram Web App (Mini App) surface](#telegram-web-app-mini-app-surface)
- [Portal (client cabinet) surface](#portal-client-cabinet-surface)
- [Webhooks & bot integration (unauthenticated schema)](#webhooks--bot-integration-unauthenticated-schema)
- [Error format](#error-format)

## Authentication surfaces

The API has **five independent identity mechanisms**, implemented in `backend/app/api/deps.py`
(unless noted). A route depends on exactly one of these — there is no shared session concept
across staff, webapp clients, and portal accounts.

| Mechanism | Dependency | Identity | Notes |
|---|---|---|---|
| Staff JWT | `get_current_staff_user` / `get_current_staff_user_sse` | `StaffUser` | Bearer access token (HS256, 15 min TTL, `ACCESS_TOKEN_EXPIRE_MINUTES` in `core/security.py`), issued by `POST /api/v1/auth/login`; refreshed via an httpOnly refresh cookie (`REFRESH_TOKEN_EXPIRE_DAYS` = 7). Token `sub` = staff user id, type must be `access`. The SSE variant also accepts the token as an `access_token` query param since `EventSource` cannot set headers. |
| Staff RBAC | `require_role(*roles)`, `require_admin`, `require_analyst_or_admin` | `StaffUser` with role check | Wraps `get_current_staff_user`; returns 403 if `current_user.role` is not in the allowed set. Roles: `admin`, `analyst`, `trader`, `viewer` (`StaffRole`). |
| Telegram Web App | `get_current_client` | `Client` | Two paths, first success wins: (A) `X-Telegram-Init-Data` header — Telegram Mini App initData, HMAC-verified constant-time, TTL-bound; (B) `client_session` httpOnly cookie — browser Telegram Login Widget session, issued by `POST /api/v1/webapp/auth/telegram`. Every failure returns a generic 401 ("Authentication required") without revealing which check failed. |
| Portal account | `get_current_account` | `UserAccount` | Bearer `portal_access` JWT (audience-isolated by a `type` claim — `portal_access`/`portal_refresh` — never a JWT `aud` claim, so a staff `access` or webapp `client_session` token cannot be replayed here and vice versa). Issued by `POST /api/v1/portal/auth/otp/verify`; refreshed via an httpOnly `portal_session` cookie. 403 if the account is not `active`. |
| Shared-secret webhook | inline `hmac.compare_digest` checks | none (system caller) | Used only by `POST /api/v1/telegram/webhook/{secret}` and `POST /api/v1/webhooks/escrow/{provider}` — see [Webhooks](#webhooks--bot-integration-unauthenticated-schema). |

Company-scoped portal routes additionally re-check membership in the request path
(`company_service.get_company_for` / equivalent helpers) — an authenticated account that is not a
member of `{company_id}` gets a 404, not a 403, so membership is never leaked.

---

## Health

Router: `app/api/health.py` — no prefix, no auth.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/health` | none | Postgres + Redis connectivity and schema migration status. |

## Staff auth

Router: `app/api/auth.py` — prefix `/auth`, tag `auth`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/login` | none (issues token) | Staff email/password login → `TokenResponse` (access token) + refresh cookie. |
| POST | `/api/v1/auth/logout` | staff refresh cookie | Clears the refresh cookie. 204 No Content. |
| POST | `/api/v1/auth/refresh` | staff refresh cookie | Exchanges a valid refresh cookie for a new access token. |

## Public marketplace (anonymous)

Router: `app/api/public.py` — prefix `/public`, tag `public`. **No authentication on any route** —
this is the server-rendered, search-indexable storefront (portal SSR shell reads from it).

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/public/offers` | none | Public offer catalog (`PublicOfferListOut`), filterable by product/query. |
| GET | `/api/v1/public/offers/{offer_id}` | none | Public offer detail page (`PublicOfferDetail`). |
| GET | `/api/v1/public/categories` | none | Category tiles with offer counts (`PublicCategoryOut`). |
| GET | `/api/v1/public/directories/{slug}` | none | A public company directory — manufacturers / traders / logistics / laboratories (`PublicCompanyListOut`). |
| GET | `/api/v1/public/directories/{slug}/{company_id}` | none | A company's public profile within that directory (`PublicCompanyDetail`). |
| GET | `/api/v1/public/stats` | none | Live platform figures for the hero strip / directory tile counts (`PublicStatsOut`). |
| GET | `/api/v1/public/prices` | none | Market price rail (`PublicQuoteOut[]`). |
| GET | `/api/v1/public/news` | none | Published industry news cards (`NewsArticleCard[]`). |
| GET | `/api/v1/public/sitemap` | none | Every crawlable detail URL with `lastmod`, for `sitemap.xml` generation (`PublicSitemapOut`). |

## Staff / dashboard — signal feed, requests, sources, alerts, prices

Routers: `feed.py` (prefix `/feed`), `dashboard.py` (prefix `/dashboard`),
`dashboard_requests.py` (prefix `/requests`), `sources.py` (prefix `/sources`),
`alert_rules.py` (two routers: prefix `/alert-rules` and prefix `/alerts`), `prices.py`
(prefix `/prices`). All require a staff Bearer token; RBAC noted per row (blank = any
authenticated staff role).

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/feed` | staff | Live market feed, keyset pagination (`FeedPage`). |
| GET | `/api/v1/feed/stream` | staff (SSE — header or `access_token` query param) | SSE stream of new entity IDs on the live feed. |
| GET | `/api/v1/dashboard/summary` | staff | Dashboard home overview — KPIs + top panels (`DashboardSummary`). |
| GET | `/api/v1/requests` | staff | List all purchase requests (`RequestListOut[]`). |
| GET | `/api/v1/requests/export` | staff | Export purchase requests as a CSV stream. |
| GET | `/api/v1/requests/{request_id}` | staff | Request detail with price analysis (`RequestDetailOut`). |
| PATCH | `/api/v1/requests/{request_id}` | staff | Change status / assign / add note. |
| POST | `/api/v1/requests/{request_id}/note` | staff | Add a team note to a request. |
| POST | `/api/v1/requests/{request_id}/assign` | staff | Assign an owner to a request. |
| POST | `/api/v1/requests/{request_id}/contact` | staff | "Contact buyer" deep-link action. |
| POST | `/api/v1/requests/{request_id}/analyze` | staff | Run (or re-run) LLM AI analysis for a request. |
| GET | `/api/v1/requests/{request_id}/pushed-suppliers` | staff | Suppliers this RFQ was pushed to (read-only, `PushedSupplierOut[]`). |
| GET | `/api/v1/sources` | staff | List sources (health only, `SourceHealthItem[]`). |
| GET | `/api/v1/sources/{source_id}` | `require_admin` | Single source with full config, for editing (`SourceDetail`). |
| POST | `/api/v1/sources` | `require_admin` | Create a source (no-code adapter wizard). |
| POST | `/api/v1/sources/{source_id}/test` | `require_admin` | Test a source by running its adapter's `test()`. |
| PATCH | `/api/v1/sources/{source_id}` | `require_admin` | Update a source (enable/disable, config). |
| GET | `/api/v1/alert-rules` | staff | List alert rules (`AlertRuleOut[]`). |
| POST | `/api/v1/alert-rules` | `require_admin` | Create an alert rule. |
| PATCH | `/api/v1/alert-rules/{rule_id}` | `require_admin` | Update an alert rule. |
| DELETE | `/api/v1/alert-rules/{rule_id}` | `require_admin` | Delete an alert rule. |
| GET | `/api/v1/alerts` | staff | List fired alerts (`AlertOut[]`). |
| GET | `/api/v1/prices/series` | staff | Price series for a product/market (`PriceSeriesOut[]`). |

## Staff / admin — users, products, settings, news moderation

Routers: `admin_users.py`, `admin_products.py`, `admin_settings.py`, `admin_sources.py` — all
prefix `/admin`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/admin/users` | `require_admin` | List staff users (`StaffUserItem[]`). |
| GET | `/api/v1/admin/products` | `require_admin` | List all products (`ProductOut[]`). |
| POST | `/api/v1/admin/products` | `require_admin` | Create a product. |
| PATCH | `/api/v1/admin/products/{product_id}` | `require_admin` | Update a product. |
| GET | `/api/v1/admin/settings` | `require_admin` | List runtime settings (`SettingItem[]`, `app_settings` table). |
| PUT | `/api/v1/admin/settings` | `require_admin` | Update runtime settings. |
| GET | `/api/v1/admin/news/stats` | `require_analyst_or_admin` | News-ops dashboard stats (`NewsStats`). |
| POST | `/api/v1/admin/news/run-parser` | `require_admin` | Trigger a news scan/parse now. |
| GET | `/api/v1/admin/news/activity` | `require_analyst_or_admin` | Per-source scan activity (`SourceActivity[]`). |
| GET | `/api/v1/admin/news/pending` | `require_analyst_or_admin` | News articles awaiting approval (`PendingNewsItem[]`). |
| POST | `/api/v1/admin/news/{signal_id}/approve` | `require_analyst_or_admin` | Approve a pending news article. |
| POST | `/api/v1/admin/news/{signal_id}/reject` | `require_analyst_or_admin` | Reject a pending news article. |
| GET | `/api/v1/admin/source-types` | `require_admin` | Registered adapter types with config schemas (`SourceTypeItem[]`). |
| GET | `/api/v1/admin/sources/health` | `require_admin` | Per-source health status (`SourceHealthItem[]`). |
| POST | `/api/v1/admin/sources/{source_id}/reprocess` | `require_admin` | Re-parse a source's previously-dropped `raw_items`. |
| GET | `/api/v1/admin/llm-spend` | `require_admin` | Today's LLM token budget usage + per-model cost breakdown (`LlmSpendResponse`). |
| GET | `/api/v1/admin/source-groups` | `require_analyst_or_admin` | List source groups (`SourceGroup[]`). |
| GET | `/api/v1/admin/sources/brief` | `require_analyst_or_admin` | List sources with identity + group (`SourceBrief[]`). |
| PUT | `/api/v1/admin/sources/{source_id}/group` | `require_admin` | Assign a source's group. |

## Staff / admin — marketplace moderation & sourcing

Routers: `moderation.py` (prefix `/admin/moderation`), `offer_requests.py`
(prefix `/admin/offer-requests`), `sourcing.py` (prefix `/admin`).

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/admin/moderation/offers` | `require_analyst_or_admin` | List seller offers awaiting moderation (`ModerationOfferOut[]`). |
| POST | `/api/v1/admin/moderation/offers/{offer_id}/approve` | `require_analyst_or_admin` | Approve a seller offer (makes it public). |
| POST | `/api/v1/admin/moderation/offers/{offer_id}/reject` | `require_analyst_or_admin` | Reject a seller offer (with a note). |
| GET | `/api/v1/admin/offer-requests` | `require_analyst_or_admin` | List pending buyer inquiries awaiting review (`AdminOfferRequestOut[]`). |
| POST | `/api/v1/admin/offer-requests/{offer_request_id}/approve` | `require_analyst_or_admin` | Approve an inquiry → forward to the seller. |
| POST | `/api/v1/admin/offer-requests/{offer_request_id}/reject` | `require_analyst_or_admin` | Reject an inquiry (with an optional note). |
| GET | `/api/v1/admin/inventory` | `require_analyst_or_admin` | List broker inventory items (`InventoryItemOut[]`). |
| POST | `/api/v1/admin/inventory` | `require_analyst_or_admin` | Create an inventory item. |
| PATCH | `/api/v1/admin/inventory/{item_id}` | `require_analyst_or_admin` | Update an inventory item. |
| DELETE | `/api/v1/admin/inventory/{item_id}` | `require_analyst_or_admin` | Delete an inventory item. |
| GET | `/api/v1/admin/partners` | `require_analyst_or_admin` | List partner suppliers (`PartnerSupplierOut[]`). |
| POST | `/api/v1/admin/partners` | `require_analyst_or_admin` | Create a partner supplier. |
| PATCH | `/api/v1/admin/partners/{partner_id}` | `require_analyst_or_admin` | Update a partner supplier. |
| DELETE | `/api/v1/admin/partners/{partner_id}` | `require_analyst_or_admin` | Delete a partner supplier. |
| POST | `/api/v1/admin/requests/{request_id}/source` | `require_analyst_or_admin` | Run AI sourcing for a purchase request (`SourcingRunOut`). |
| GET | `/api/v1/admin/requests/{request_id}/sourcing` | `require_analyst_or_admin` | Get the sourcing run result for a request. |
| GET | `/api/v1/admin/intel/market` | `require_analyst_or_admin` | Market intelligence rows for the broker dashboard (`MarketIntelRow[]`). |

## Staff / admin — reports

Router: `reports.py` — prefix `/admin/reports`. News-engine daily/evening report review pipeline
(`draft → pending_approval → approved → published`).

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/admin/reports` | `require_analyst_or_admin` | List reports for review (`ReportAdminOut[]`). |
| POST | `/api/v1/admin/reports/generate` | `require_analyst_or_admin` | Generate today's report now. |
| POST | `/api/v1/admin/reports/{report_id}/approve` | `require_analyst_or_admin` | Approve a report. |
| POST | `/api/v1/admin/reports/{report_id}/publish` | `require_analyst_or_admin` | Publish a report (dispatches channel delivery tasks). |
| POST | `/api/v1/admin/reports/{report_id}/reject` | `require_analyst_or_admin` | Reject a report. |

## Staff / admin — company verification

Router: `admin_verification.py` — prefix `/admin`. Backs the staff verification-case queue for
`portal/` company onboarding (R1).

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/admin/verification/cases` | `require_analyst_or_admin` | List verification cases, optional status filter. |
| GET | `/api/v1/admin/verification/cases/{case_id}` | `require_analyst_or_admin` | Verification case detail with its checks. |
| POST | `/api/v1/admin/verification/cases/{case_id}/registry-check` | `require_analyst_or_admin` | Record a manual government-registry/VAT check result (multipart form). |
| POST | `/api/v1/admin/verification/cases/{case_id}/approve` | `require_analyst_or_admin` | Approve a verification case → company becomes `verified`. |
| POST | `/api/v1/admin/verification/cases/{case_id}/reject` | `require_analyst_or_admin` | Reject a verification case. |
| POST | `/api/v1/admin/verification/cases/{case_id}/request-info` | `require_analyst_or_admin` | Ask the applicant for more information. |
| POST | `/api/v1/admin/verification/checks/{check_id}/waive` | `require_admin` | Waive one automated check on a case. |
| GET | `/api/v1/admin/companies` | `require_analyst_or_admin` | List companies, optional status/query filter. |
| GET | `/api/v1/admin/companies/{company_id}` | `require_analyst_or_admin` | Company detail (staff view). |
| POST | `/api/v1/admin/companies/{company_id}/suspend` | `require_admin` | Suspend a company. |
| POST | `/api/v1/admin/companies/{company_id}/reinstate` | `require_admin` | Reinstate a suspended company. |

## Staff / admin — contracts, deals, escrow (Deal Lifecycle)

Routers: `admin_contracts.py` (read-only oversight), `admin_deals.py`, `admin_escrow.py` — all
prefix `/admin`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/admin/contracts` | `require_analyst_or_admin` | List contracts, optional status/query filter (`AdminContractOut[]`). |
| GET | `/api/v1/admin/contracts/{contract_id}` | `require_analyst_or_admin` | Contract detail (staff oversight view). |
| GET | `/api/v1/admin/contracts/{contract_id}/document` | `require_analyst_or_admin` | Signed contract document — redirect or inline (`as` query param). |
| GET | `/api/v1/admin/deals` | `require_analyst_or_admin` | List deals, optional status/query filter (`AdminDealListOut`). |
| GET | `/api/v1/admin/deals/{deal_id}` | `require_analyst_or_admin` | Deal detail (staff oversight view). |
| GET | `/api/v1/admin/deals/{deal_id}/messages` | `require_analyst_or_admin` | Paged deal message thread. |
| POST | `/api/v1/admin/deals/{deal_id}/resolve-dispute` | `require_admin` | Resolve a disputed deal. |
| GET | `/api/v1/admin/escrow` | `require_analyst_or_admin` | List escrow payments, optional status filter (`EscrowListOut`). |
| GET | `/api/v1/admin/escrow/provider-events` | `require_analyst_or_admin` | Held/unmatched provider callback events awaiting operator action (`ProviderHoldListOut`). |
| GET | `/api/v1/admin/escrow/{payment_id}` | `require_analyst_or_admin` | Escrow payment detail. |
| POST | `/api/v1/admin/escrow/{payment_id}/mark` | `require_admin` | Manually mark an escrow payment's state. |

## Staff / admin — compliance (substances & licenses)

Routers: `admin_substances.py` (prefix `/admin/substances`, tag `compliance`), `admin_licenses.py`
(prefix `/admin`, tag `compliance`). Chemical-compliance registry — `substances` is the system's
source of truth since no unified national registry exists.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/admin/substances` | `require_analyst_or_admin` | List substances, optional query/regulation-level filter. |
| POST | `/api/v1/admin/substances` | `require_admin` | Create a substance. |
| GET | `/api/v1/admin/substances/{substance_id}` | `require_analyst_or_admin` | One substance. |
| PATCH | `/api/v1/admin/substances/{substance_id}` | `require_admin` | Edit a substance. |
| POST | `/api/v1/admin/substances/{substance_id}/deactivate` | `require_admin` | Retire a substance. |
| POST | `/api/v1/admin/substances/{substance_id}/activate` | `require_admin` | Restore a retired substance. |
| GET | `/api/v1/admin/companies/{company_id}/licenses` | `require_analyst_or_admin` | Licences a company holds, including revoked/expired. |
| POST | `/api/v1/admin/companies/{company_id}/licenses` | `require_admin` | Issue a licence to a company. |
| POST | `/api/v1/admin/licenses/{license_id}/revoke` | `require_admin` | Revoke a licence (takes effect immediately). |

## Staff / admin — lab orders & partners

Router: `admin_lab.py` — prefix `/admin`. Manual partner-lab analysis workflow (P6) — every
`lab_orders` status transition is staff-driven.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/admin/lab-orders` | `require_analyst_or_admin` | List lab orders, optional status filter (`LabOrderListOut`). |
| GET | `/api/v1/admin/lab-orders/{order_id}` | `require_analyst_or_admin` | Lab order detail (`LabOrderAdminOut`). |
| POST | `/api/v1/admin/lab-orders/{order_id}/transition` | `require_analyst_or_admin` | Move a lab order through its status machine. |
| POST | `/api/v1/admin/lab-orders/{order_id}/result` | `require_analyst_or_admin` | Upload the result PDF and complete the order (`lab_verified` set here only). |
| POST | `/api/v1/admin/lab-orders/{order_id}/partner` | `require_analyst_or_admin` | Assign a lab partner to an order. |
| GET | `/api/v1/admin/lab-partners` | `require_analyst_or_admin` | List lab partners (`LabPartnerOut[]`). |
| POST | `/api/v1/admin/lab-partners` | `require_admin` | Create a lab partner. |
| PATCH | `/api/v1/admin/lab-partners/{partner_id}` | `require_admin` | Update a lab partner. |
| POST | `/api/v1/admin/lab-partners/{partner_id}/deactivate` | `require_admin` | Deactivate a lab partner. |
| POST | `/api/v1/admin/lab-partners/{partner_id}/activate` | `require_admin` | Reactivate a lab partner. |

---

## Telegram Web App (Mini App) surface

Routers under `app/api/webapp/`. All prefixed `/webapp` (or `/webapp/<sub-area>`). Auth is
`get_current_client` (Telegram initData or `client_session` cookie) unless noted as public.

### Auth — `auth.py` (prefix `/webapp/auth`, tag `webapp-auth`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/webapp/auth/config` | none | Public config the static bundle needs to render the Telegram Login Widget (bot handle). |
| POST | `/api/v1/webapp/auth/telegram` | none (issues session) | Authenticate a browser visitor via the Telegram Login Widget → sets `client_session` cookie. |
| POST | `/api/v1/webapp/auth/logout` | none | Clear the `client_session` cookie. |

### Client profile — `me.py` (prefix `/webapp`, tag `webapp`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/webapp/me` | client | Authenticated client profile (`ClientProfileOut`). |
| PATCH | `/api/v1/webapp/me` | client | Update profile (language, name). |

### Request wizard & files — `requests.py`, `files.py` (prefix `/webapp`, tag `webapp`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/webapp/requests` | client | Create a purchase request (`RequestOut`). |
| GET | `/api/v1/webapp/requests` | client | List the authenticated client's requests. |
| GET | `/api/v1/webapp/requests/{request_id}` | client | Request detail (own requests only). |
| POST | `/api/v1/webapp/requests/{request_id}/files` | client | Attach a file to a request (`RequestFileOut`). |
| GET | `/api/v1/webapp/requests/{request_id}/files/{file_id}` | client (owner-only) | Stream/download a request file. |

### Reference data — `reference.py` (prefix `/webapp/reference`, tag `webapp-reference`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/webapp/reference/products` | client | Active polymer products for the request/offer selectors. |

### Seller offers — `seller.py` (prefix `/webapp/seller`, tag `webapp-seller`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/webapp/seller/offers` | client | Create a seller offer (`SellerOfferOut`). |
| GET | `/api/v1/webapp/seller/offers` | client | List the authenticated seller's own offers. |
| GET | `/api/v1/webapp/seller/offers/{offer_id}` | client | Get one of the caller's own offers (any status). |
| PATCH | `/api/v1/webapp/seller/offers/{offer_id}` | client | Edit one's own offer (re-enters moderation if it was already public). |
| POST | `/api/v1/webapp/seller/offers/{offer_id}/submit` | client | Finalize an offer (uploads done) → notify the team group. |
| POST | `/api/v1/webapp/seller/offers/{offer_id}/files` | client | Attach a file to an offer (`OfferFileRef`). |

### Public catalog & buyer inquiries — `market.py` (prefix `/webapp/market`, tag `webapp-market`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/webapp/market/featured` | **none** | Featured approved offers for the anonymous marketing landing (omits seller contact). |
| GET | `/api/v1/webapp/market/offers` | client | Approved-offer catalog, filterable (excludes the caller's own listings). |
| GET | `/api/v1/webapp/market/categories` | client | Per-product approved-offer counts (own excluded). |
| GET | `/api/v1/webapp/market/offers/{offer_id}` | client | A single approved offer, or 404; flags `is_own`. |
| GET | `/api/v1/webapp/market/offers/{offer_id}/images/{file_id}` | **none** | Stream an approved offer's image bytes (public, for `<img>` tags). |
| GET | `/api/v1/webapp/market/companies/{company_id}/logo` | **none** | Stream a company logo (public, for `<img>` tags). |
| POST | `/api/v1/webapp/market/offers/{offer_id}/request` | client | Create a buyer inquiry on an offer → staff review queue. |
| GET | `/api/v1/webapp/market/my-requests` | client | List the authenticated buyer's own offer inquiries. |
| GET | `/api/v1/webapp/market/my-requests/{offer_request_id}` | client | One of the buyer's own inquiries (detail). |
| PATCH | `/api/v1/webapp/market/my-requests/{offer_request_id}` | client | Edit the buyer's own inquiry (re-enters review). |

### News reader — `news.py` (prefix `/webapp/news`, tag `webapp-news`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/webapp/news/articles` | client | List news article cards (`NewsArticleCard[]`). |
| GET | `/api/v1/webapp/news/articles/filters` | client | News filter facets (`NewsFilterOptions`). |
| GET | `/api/v1/webapp/news/articles/{signal_id}` | client | Single news article (`NewsArticleDetail`). |
| GET | `/api/v1/webapp/news` | client | List published daily/evening reports (`ReportPublicSummary[]`). |
| GET | `/api/v1/webapp/news/{report_id}` | client | A published report (`ReportPublicOut`). |

---

## Portal (client cabinet) surface

Routers under `app/api/portal/`. All prefixed `/portal` (or `/portal/<sub-area>`). Auth is
`get_current_account` (portal `Bearer` access token) on every route except the OTP request/verify
endpoints themselves. Company-scoped routes (`{company_id}` in the path) additionally require
the caller's account to be a member of that company (404 otherwise) — most write actions further
require the acting member to hold an admin role on the company (`_require_company_admin`).

### Auth & profile — `auth.py` (prefix `/portal`, tag `portal-auth`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/portal/auth/otp/request` | none | Request an OTP SMS to a phone number. 204 always for a valid number; 429 when rate-limited. |
| GET | `/api/v1/portal/auth/otp/peek` | none, but **404 unless `DEBUG=true` and `SMS_PROVIDER=console`** | E2E test hook — returns the pending OTP code. Never reachable in production. |
| POST | `/api/v1/portal/auth/otp/verify` | none (issues token) | Verify the OTP → `PortalTokenResponse` (access token) + `portal_session` cookie. |
| POST | `/api/v1/portal/auth/refresh` | `portal_session` cookie | Exchange the refresh cookie for a new access token. |
| POST | `/api/v1/portal/auth/logout` | none | Clear the `portal_session` cookie. |
| GET | `/api/v1/portal/me` | account | Authenticated account profile (`AccountOut`). |
| PATCH | `/api/v1/portal/me` | account | Update account profile. |

### Companies & verification — `companies.py` (prefix `/portal/companies`, tag `portal-companies`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/portal/companies` | account | Register a new company. |
| GET | `/api/v1/portal/companies` | account | List companies the caller belongs to (`CompanySummaryOut[]`). |
| GET | `/api/v1/portal/companies/{company_id}` | account (member) | Company detail (`CompanyDetailOut`). |
| PATCH | `/api/v1/portal/companies/{company_id}` | account (member) | Update company profile. |
| PUT | `/api/v1/portal/companies/{company_id}/roles` | account (member) | Set business roles (manufacturer/trader/logistics/laboratory). |
| POST | `/api/v1/portal/companies/{company_id}/bank-accounts` | account (member) | Add a bank account. |
| DELETE | `/api/v1/portal/companies/{company_id}/bank-accounts/{account_id}` | account (member) | Archive a bank account. |
| POST | `/api/v1/portal/companies/{company_id}/logo` | account (member) | Upload or replace the company logo. |
| DELETE | `/api/v1/portal/companies/{company_id}/logo` | account (member) | Remove the company logo. |
| POST | `/api/v1/portal/companies/{company_id}/documents` | account (member) | Upload a verification document (multipart). |
| GET | `/api/v1/portal/companies/{company_id}/documents/{document_id}/download` | account (member) | Download a verification document. |
| DELETE | `/api/v1/portal/companies/{company_id}/documents/{document_id}` | account (member) | Delete a verification document. |
| POST | `/api/v1/portal/companies/{company_id}/verification/submit` | account (member) | Submit the company for staff verification (`CaseOut`). |
| GET | `/api/v1/portal/companies/{company_id}/verification` | account (member) | Current verification case status (`CaseOut`). |

### E-IMZO digital signature — `eimzo.py` (prefix `/portal/companies`, tag `portal-eimzo`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/portal/companies/{company_id}/eimzo/challenge` | account (member) | Start an E-IMZO signing challenge (`ChallengeOut`). |
| POST | `/api/v1/portal/companies/{company_id}/eimzo/verify` | account (member) | Verify the E-IMZO PKCS#7 response → identity lock + evidence (`VerifyOut`). |

### Compliance — `compliance.py` (prefix `/portal/companies`, tag `portal-compliance`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/portal/companies/{company_id}/licenses` | account (member) | Licences this company holds. |
| GET | `/api/v1/portal/companies/{company_id}/offers/{offer_id}/compliance` | account (member) | What this offer still needs to be published (`ComplianceOut`). |
| POST | `/api/v1/portal/companies/{company_id}/substance-suggestions` | account (member) | Ask the AI which substance an offer's free text refers to. |
| POST | `/api/v1/portal/companies/{company_id}/substance-suggestions/{suggestion_id}/decision` | account (member) | Confirm or reject an AI substance hint. |

### Substances reference — `substances.py` (prefix `/portal/substances`, tag `portal-compliance`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/portal/substances` | account | Search the substance registry (`SubstanceBrief[]`). |

### Seller offers — `offers.py` (prefix `/portal/companies`, tag `portal-offers`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/portal/companies/{company_id}/offers` | account (member) | List the company's offers (`CompanyOfferOut[]`). |
| POST | `/api/v1/portal/companies/{company_id}/offers` | account (member) | Create an offer. |
| GET | `/api/v1/portal/companies/{company_id}/offers/{offer_id}` | account (member) | Offer detail. |
| PATCH | `/api/v1/portal/companies/{company_id}/offers/{offer_id}` | account (member) | Edit an offer. |
| POST | `/api/v1/portal/companies/{company_id}/offers/{offer_id}/archive` | account (member) | Archive an offer. |
| POST | `/api/v1/portal/companies/{company_id}/offers/{offer_id}/files` | account (member) | Upload an offer file/image. |
| GET | `/api/v1/portal/companies/{company_id}/offers/{offer_id}/files/{file_id}` | account (owner-scoped) | Offer file bytes. |
| DELETE | `/api/v1/portal/companies/{company_id}/offers/{offer_id}/files/{file_id}` | account (member) | Delete an offer file. |

### Market browsing & favorites — `market.py` (prefix `/portal/market`, tag `portal-market`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/portal/market` | account | Browse approved offers (`PortalMarketOfferOut[]`). |
| GET | `/api/v1/portal/market/favorites` | account | This account's starred offers. |
| POST | `/api/v1/portal/market/offers/{offer_id}/favorite` | account | Star an offer. |
| DELETE | `/api/v1/portal/market/offers/{offer_id}/favorite` | account | Unstar an offer. |
| GET | `/api/v1/portal/market/companies/{company_id}` | account | Public seller company profile (`PublicCompanyProfileOut`). |
| GET | `/api/v1/portal/market/{offer_id}` | account | Offer detail + my company's inquiries on it (`PortalMarketOfferDetail`). |

### Inquiries — `inquiries.py` (prefix `/portal`, tag `portal-inquiries`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/portal/market/{offer_id}/inquiries` | account | Send an inquiry on an offer, as a company. |
| GET | `/api/v1/portal/inquiries` | account | Inquiries my company has sent. |
| GET | `/api/v1/portal/inquiries/incoming` | account | Approved inquiries received on my company's offers. |
| GET | `/api/v1/portal/inquiries/{inquiry_id}` | account (sender, or offer owner if approved) | One inquiry. |
| PATCH | `/api/v1/portal/inquiries/{inquiry_id}` | account | Revise a sent inquiry (re-enters moderation). |

### Purchase requests — `requests.py` (prefix `/portal/requests`, tag `portal-requests`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/portal/requests` | account | Create a purchase request, as a company. |
| POST | `/api/v1/portal/requests/{request_id}/files` | account | Attach a file to a request. |
| GET | `/api/v1/portal/requests` | account | List my company's requests. |
| GET | `/api/v1/portal/requests/{request_id}` | account | Request detail + status timeline. |
| POST | `/api/v1/portal/requests/{request_id}/cancel` | account | Cancel a request (client-visible non-terminal states only). |

### Manufacturers directory, factory RFQs & chat — `manufacturers.py` (prefix `/portal/manufacturers`, tag `portal-manufacturers`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/portal/manufacturers` | account | Manufacturers directory (`ManufacturerListOut`). |
| GET | `/api/v1/portal/manufacturers/rfqs` | account | Factory RFQs for my company. |
| GET | `/api/v1/portal/manufacturers/rfqs/{rfq_id}` | account | Factory RFQ detail. |
| POST | `/api/v1/portal/manufacturers/rfqs/{rfq_id}/documents` | account | Upload a factory-RFQ document. |
| GET | `/api/v1/portal/manufacturers/threads` | account | My manufacturer chat threads. |
| GET | `/api/v1/portal/manufacturers/threads/{thread_id}/messages` | account | Manufacturer chat messages (paged). |
| POST | `/api/v1/portal/manufacturers/threads/{thread_id}/messages` | account | Post a manufacturer chat message. |
| GET | `/api/v1/portal/manufacturers/threads/{thread_id}/messages/{message_id}/file` | account | Presigned URL for a chat attachment. |
| POST | `/api/v1/portal/manufacturers/{manufacturer_id}/threads` | account | Open (or get) a chat thread with a manufacturer. |
| POST | `/api/v1/portal/manufacturers/{manufacturer_id}/rfqs` | account | Submit a factory RFQ. |

### Contracts (E-IMZO e-signature) — `contracts.py` (prefix `/portal`, tag `portal-contracts`)

Registered **before** `portal/companies` in `create_app()` so its literal
`/portal/companies/directory` path wins over `portal/companies`'s `/portal/companies/{company_id}`
parametrized route.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/portal/contract-templates` | account | List available contract templates (`TemplateOut[]`). |
| GET | `/api/v1/portal/companies/directory` | account | Search verified companies to contract with (`DirectoryCompanyOut[]`). |
| POST | `/api/v1/portal/contracts` | account | Create a contract draft between two companies. |
| GET | `/api/v1/portal/contracts` | account | List contracts (filterable by company/role/status). |
| GET | `/api/v1/portal/contracts/{contract_id}` | account (party) | Contract detail (`ContractDetailOut`). |
| PATCH | `/api/v1/portal/contracts/{contract_id}` | account (party) | Update contract template variables (draft only). |
| POST | `/api/v1/portal/contracts/{contract_id}/send` | account (party) | Send the contract to the counterparty. |
| POST | `/api/v1/portal/contracts/{contract_id}/accept` | account (party) | Accept a received contract. |
| POST | `/api/v1/portal/contracts/{contract_id}/decline` | account (party) | Decline a received contract. |
| POST | `/api/v1/portal/contracts/{contract_id}/cancel` | account (party) | Cancel a contract before both sides have signed. |
| POST | `/api/v1/portal/contracts/{contract_id}/sign/challenge` | account (party) | Start an E-IMZO signing challenge for this contract. |
| POST | `/api/v1/portal/contracts/{contract_id}/sign` | account (party) | Submit the E-IMZO signature. |
| GET | `/api/v1/portal/contracts/{contract_id}/document` | account (party) | Signed contract document — redirect or inline. |
| GET | `/api/v1/portal/contracts/{contract_id}/bundle` | account (party) | Full signed evidence bundle (document + signatures). |

### Deals, messaging, documents & RFQ responses — `deals.py` (prefix `/portal`, tag `portal-deals`)

Registered before `portal/companies` for the same literal-vs-parametrized-route reason as
contracts.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/portal/companies/{company_id}/deals` | account (member) | List deals for this company, filterable by role/status (`DealListOut`). |
| GET | `/api/v1/portal/companies/{company_id}/deals/{deal_id}` | account (member, party) | Deal detail (`DealDetailOut`). |
| POST | `/api/v1/portal/companies/{company_id}/deals/{deal_id}/transition` | account (member, party) | Move a deal through its status machine. |
| GET | `/api/v1/portal/companies/{company_id}/deals/{deal_id}/messages` | account (member, party) | Paged deal message thread. |
| POST | `/api/v1/portal/companies/{company_id}/deals/{deal_id}/messages` | account (member, party) | Post a deal message. |
| GET | `/api/v1/portal/companies/{company_id}/deals/{deal_id}/messages/{message_id}/file` | account (member, party) | Download a message attachment. |
| POST | `/api/v1/portal/companies/{company_id}/deals/{deal_id}/documents` | account (member, party) | Attach a document to a deal. |
| GET | `/api/v1/portal/companies/{company_id}/deals/{deal_id}/documents/{document_id}` | account (member, party) | Get a deal document. |
| POST | `/api/v1/portal/companies/{company_id}/deals/{deal_id}/documents/{document_id}/revoke` | account (member, party) | Revoke a previously attached deal document. |
| POST | `/api/v1/portal/companies/{company_id}/requests/{request_id}/responses` | account (member) | Submit an RFQ response to a purchase request. |
| GET | `/api/v1/portal/companies/{company_id}/requests/{request_id}/responses` | account (member) | List RFQ responses on a request (`RfqResponseListOut`). |
| POST | `/api/v1/portal/companies/{company_id}/requests/{request_id}/responses/{response_id}/accept` | account (member) | Accept an RFQ response → creates a deal (`DealDetailOut`). |
| POST | `/api/v1/portal/companies/{company_id}/requests/{request_id}/responses/{response_id}/withdraw` | account (member) | Withdraw a submitted RFQ response. |
| GET | `/api/v1/portal/market/requests` | account | Browse open market purchase requests to respond to (`MarketRequestListOut`). |

### Lab orders — `lab.py` (prefix `/portal/companies`, tag `portal-lab`)

Registered before `portal/companies` for the same literal-route reason.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/portal/companies/{company_id}/lab-orders` | account (member) | List lab orders for this company (`LabOrderOut[]`). |
| POST | `/api/v1/portal/companies/{company_id}/lab-orders` | account (member) | Request a lab order for an offer. |
| GET | `/api/v1/portal/companies/{company_id}/lab-orders/{order_id}` | account (member) | Lab order detail. |

### Sample requests — `samples.py` (prefix `/portal`, tag `portal-samples`)

Registered before `portal/companies` for the same literal-route reason.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/portal/companies/{company_id}/samples` | account (member) | List sample requests (`side=incoming\|sent`). |
| POST | `/api/v1/portal/market/offers/{offer_id}/samples` | account | Request a physical sample of an offer. |
| POST | `/api/v1/portal/samples/{sample_id}/transition` | account | Move a sample request through its two-party status machine. |

### Reference data — `reference.py` (prefix `/portal/reference`, tag `portal-reference`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/portal/reference/products` | account | Active polymer products for the offer selectors. |

### News reader — `news.py` (prefix `/portal/news`, tag `portal-news`)

Twin of the webapp news surface, scoped to portal auth.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/portal/news/articles` | account | List news article cards. |
| GET | `/api/v1/portal/news/articles/filters` | account | News filter facets. |
| GET | `/api/v1/portal/news/articles/{signal_id}` | account | Single news article. |
| GET | `/api/v1/portal/news` | account | List published reports. |
| GET | `/api/v1/portal/news/{report_id}` | account | A published report. |

### Notifications — `notifications.py` (prefix `/portal/notifications`, tag `portal-notifications`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/portal/notifications` | account | Paged notification list (keyset `cursor`, `unread_only` filter). |
| GET | `/api/v1/portal/notifications/unread-count` | account | Unread notification count. |
| POST | `/api/v1/portal/notifications/read` | account | Mark notifications read (by ids, or all). |

---

## Webhooks & bot integration (unauthenticated schema)

These two routes are excluded from the OpenAPI schema (`include_in_schema=False` on the escrow
one; the Telegram one carries no staff/client/account dependency at all) because they are called
by external systems, not by any of the three frontends, and are authenticated by a shared secret
rather than a JWT.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/telegram/webhook/{secret}` | path secret **and** `X-Telegram-Bot-Api-Secret-Token` header, both compared constant-time to `WEBHOOK_SECRET` | Receives Telegram bot updates (webhook mode). Mismatch on either check → 403. |
| POST | `/api/v1/webhooks/escrow/{provider}` | `X-Escrow-Token` header, constant-time compared to `ESCROW_WEBHOOK_SECRET` | Escrow payment-provider callback inbox. No configured secret → 404 (hides the rail's existence); bad token → 401. Records the callback and enqueues async interpretation; never blocks on parsing the payload. |

## Demo RBAC probes

Defined inline in `create_app()` (not in a router module) — exist only to prove the
`require_role` guard works end-to-end; not part of the product surface.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/admin/whoami` | `require_admin` | Returns the caller's id/email/role, or 403 for non-admin roles. |
| GET | `/api/v1/analyst/whoami` | `require_analyst_or_admin` | Returns the caller's id/email/role, or 403 for trader/viewer roles. |

## Error format

FastAPI's default validation-error and `HTTPException` shapes are used throughout — there is no
project-specific error envelope layer. A typical error response:

```json
{
  "detail": "Authentication required"
}
```

Validation errors (422, from Pydantic request-model parsing) use FastAPI's standard shape:

```json
{
  "detail": [
    {
      "loc": ["body", "phone"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

Common status codes across the API: `401` (missing/invalid/expired credential — always a generic
message on the webapp `get_current_client` path, per `T-03-03`, to avoid leaking which check
failed), `403` (authenticated but not authorized — wrong role, inactive/blocked account, or not a
company member), `404` (not found — also used deliberately in place of `403` for
company-membership checks, so a non-member cannot distinguish "doesn't exist" from "not yours"),
`422` (request validation or a domain `ValueError` translated to a client error), `429` (OTP /
rate-limited endpoints, with a `Retry-After` header).

<!-- VERIFY: production base URL for the API (e.g. https://api.ai-imex.com or the cabinet/webapp origin's /api/v1 path) is deployment-specific and not established from repository contents alone. -->
