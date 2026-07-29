# R2 — Mini App parity in the portal: market, purchase requests, inquiries, news, notifications

> Prereq reading: `00-IMPLEMENTATION-CONTEXT.md`, `ARCHITECTURE.md` (Amendments A1/A2), `R1-PLAN.md` (must be fully shipped first).
> **`webapp/` remains frozen — R2 adds portal twins, it never modifies or removes Mini App functionality.** The Telegram Mini App keeps working unchanged for its audience throughout.

**Goal:** the portal becomes a full working cabinet: browse the market, send per-offer inquiries, create purchase (buy) requests, read news, and receive in-portal notifications — all **company-scoped** (B2B): a buyer acts on behalf of a selected company (verified not required for buying; required only for selling — unchanged from R1).

**Demo script (Definition of Done):** portal account with company A (verified, has approved offer) and second account with company B (unverified) → B browses market, opens A's offer, sends an inquiry → inquiry passes existing staff moderation → notification appears in A's portal notification center AND (unchanged) via existing seller channels for TG offers → B creates a purchase request through the 4-step wizard → request appears in dashboard `/requests` exactly like TG-originated ones, team processes it, status change produces an in-portal notification for B → B reads news feed in the portal. Mini App regression suite still green, zero diffs in `webapp/`.

---

## Wave 1 — Dual-origin schema for requests & inquiries

### T1.1 Migration `0018_portal_parity`
- `requests`: ADD `company_id BIGINT NULL FK companies`, ADD `created_by_user_account_id BIGINT NULL FK user_accounts`, ALTER `client_id` DROP NOT NULL (verify current nullability first), ADD CHECK `ck_request_origin (client_id IS NOT NULL OR created_by_user_account_id IS NOT NULL)`.
- `offer_requests` (inquiries): same trio — `company_id NULL`, `created_by_user_account_id NULL`, relax the client FK, CHECK constraint.
- NEW `portal_notifications`: id BigInt PK; user_account_id FK NOT NULL; kind Text (e.g. `request_status`, `inquiry_approved`, `inquiry_reply`, `verification_decided`, `offer_moderated`, `news_breaking` — extensible, no enum: plain Text by design); title_key Text; body_key Text; params JSONB (i18n interpolation values); entity Text NULL; entity_id Text NULL (deep-link target); read_at NULL; created_at. Index `(user_account_id, read_at, id DESC)`.
- DB-doc edit same commit.

### T1.2 Enum/status audit (no schema change expected)
`RequestStatus`, `OfferRequestStatus` machines stay as-is. Confirm `CLIENT_STATUS_MAP` (`request_service.py:134`) is reusable for portal display labels — reuse, don't fork.

**Acceptance:** upgrade/downgrade clean; all existing request/inquiry tests green (origin-relaxation regression); TG-origin request serialization byte-identical golden test.

## Wave 2 — Services: dual-origin requests & inquiries + notification service

### T2.1 `request_service` extension
`create_company_request(db, company, account, payload) -> Request` — same wizard payload as the Mini App path (product, grade, qty, unit, price expectations, urgency, delivery, comment, files), sets company_id + created_by_user_account_id, client_id NULL, initial status `new`, enters the **existing** status machine + `request_status_history` untouched. Notification consumer change: `send_status_change_notification` currently DMs the TG client — extend the dispatch point: if request has `created_by_user_account_id` → create `portal_notification` instead of TG DM (task in W2.3); TG path unchanged.

### T2.2 `offer_request_service` extension
`create_company_inquiry(db, company, account, offer, payload)` — pending → existing moderation; on approve, the "forward to seller" step must handle **both seller origins**: TG-seller offer → existing bot DM path unchanged; company-origin offer (R1) → `portal_notification` to all active members of the selling company (kind `inquiry_approved`, contact exchange per existing withholding rules). Buyer-side edits re-enter pending (mirror existing semantics).

### T2.3 `backend/app/services/notification_service.py` + consumers
`notify_account(db, account_id, kind, title_key, body_key, params, entity, entity_id)` — insert row (flush-only). Event consumers (extend `app/tasks/events.py` routing): VERIFICATION_CASE_APPROVED/REJECTED/NEEDS_INFO → members of the company; offer moderation outcomes for company-origin offers → members; request status changes (portal-origin) → creator; inquiry approvals → both sides as applicable. `mark_read(db, account, ids | all)`. Unread count query. Retention: beat task `prune_portal_notifications` (delete read > 90 d, unread > 365 d) in `schedule.py`.

**Acceptance:** origin-routing matrix test (TG request → TG DM only; portal request → portal notification only; company offer inquiry → portal; TG offer inquiry → TG); notification rows carry i18n keys+params, никогда pre-rendered text.

## Wave 3 — Portal APIs

All under `get_current_account`; company-scoped writes resolve membership via `get_company_for`.

### T3.1 Market (read) — `backend/app/api/portal/market.py`
- `GET /portal/market` — approved offers, filters: product, availability, country, origin-agnostic; pagination; card fields = webapp market parity (product, grade, price/«по запросу», qty, availability, country, display_name, company_verified badge, files count, published_at).
- `GET /portal/market/{offer_id}` — full card + files (presigned) + "my company's relationship" block (my inquiries to this offer).
- Reuse the same query/serializer layer the webapp market endpoints use (extract shared functions into the service if currently router-local — refactor allowed in backend, forbidden in webapp).

### T3.2 Inquiries — `backend/app/api/portal/inquiries.py`
- `POST /portal/market/{offer_id}/inquiries` `{company_id, message, qty?, …}` (mirror webapp inquiry fields)
- `GET /portal/inquiries?company_id=` (sent by my company) + `GET /portal/inquiries/incoming?company_id=` (received on my company's offers, post-moderation)
- `GET /portal/inquiries/{id}`, `PATCH` (buyer edit → re-moderation), same status visibility rules as Mini App (moderation internals hidden).

### T3.3 Purchase requests — `backend/app/api/portal/requests.py`
- `POST /portal/requests` `{company_id, …wizard payload…}` + file upload endpoint (reuse `upload_request_file` storage path pattern)
- `GET /portal/requests?company_id=`, `GET /portal/requests/{id}` — status via `CLIENT_STATUS_MAP` labels + history timeline (client-safe subset)
- `POST /portal/requests/{id}/cancel` (allowed from client-visible non-terminal states — mirror Mini App rules).

### T3.4 News — `backend/app/api/portal/news.py`
`GET /portal/news/articles` + `GET /portal/news/articles/{id}` — twin of `GET /webapp/news/articles` (same service/serializer, portal auth). Include breaking flag, published reports list if the webapp exposes them (match its surface exactly — parity, not redesign).

### T3.5 Notifications — `backend/app/api/portal/notifications.py`
`GET /portal/notifications?unread_only=&cursor=`, `POST /portal/notifications/read` `{ids|all}`, `GET /portal/notifications/unread-count`. Polling model (30 s frontend interval); SSE deferred (note for R4+; dashboard SSE pattern exists if wanted later).

**Acceptance:** authz matrix incl. cross-company isolation (member of A cannot list B's inquiries — 404); parity contract tests: for each twin endpoint, field-set equality with the webapp counterpart fixture (names may not drift); pagination + cursor stability tests.

## Wave 4 — Staff surface deltas

### T4.1 Dashboard
- `/requests` and `/offer-requests` pages: add origin column/badge («TG» / «Портал: {company}») and company link where applicable; filters by origin. No workflow changes.
- `/moderation`: inquiry cards for company-origin buyers show company name + verified badge (moderators need buyer context).

### T4.2 Telegram group cards
`send_request_to_group` / `send_offer_request_to_group`: include origin + company line for portal-originated items (template edit ru/uz/tr). Buttons/behavior unchanged.

**Acceptance:** dashboard e2e touch: origin badge renders; template snapshot tests updated.

## Wave 5 — Portal frontend

FSD additions (entities exist from R1 scaffolding discipline):

### T5.1 Market
`pages/market` (grid/list, filters, search, pagination), `pages/market/[id]` (gallery, specs, seller trust block, «Отправить запрос» CTA → inquiry modal/form; disabled with hint when no company selected). `entities/offer` read models shared with R1 offer management.

### T5.2 Inquiries
`pages/inquiries` two tabs: «Отправленные» / «Входящие» (incoming only for companies that have offers), thread-style detail `pages/inquiries/[id]` with edit-resubmit flow and status chips.

### T5.3 Purchase requests
`features/request-wizard` — 4 steps + confirm, port of the Mini App wizard UX (product select, specs/qty, delivery+urgency, contacts/comment, files) with company context header; `pages/requests` list + `pages/requests/[id]` status timeline (CLIENT_STATUS_MAP labels, localized).

### T5.4 News
`pages/news` feed + article view; breaking badge; source attribution line (match Mini App presentation).

### T5.5 Notification center
Bell + unread badge in app shell (30 s polling via TanStack Query refetchInterval + on window focus); dropdown latest 10 + `pages/notifications` full list; click → deep link via entity/entity_id map; mark-read on view; i18n rendering from title_key/body_key + params (ru/uz/en).

### T5.6 Home dashboard
`pages/home`: cards — company verification status, unread notifications, my active requests, my offers stats, latest news. (First screen after login; keep it assembled from existing entities, no new endpoints.)

**Acceptance:** portal CI green; Playwright e2e: the full R2 demo script; empty states for every list; i18n complete ru/uz/en; keyboard-accessible wizard.

## Wave 6 — Hardening & rollout

- **T6.1** Rate limits: inquiries (10/day/company), requests (10/day/company); notification endpoints excluded from limits.
- **T6.2** Load sanity: market list query plans (indexes on seller_offers(status, published_at), verify with EXPLAIN on dev-sized data); notification prune task verified.
- **T6.3** Docs: portal/backend/deploy CLAUDE.md deltas, RU admin guide (origin badges), DB doc.
- **T6.4** Rollout: dev demo → prod deploy. No flags to flip (buying never required verification; selling gate unchanged from R1).

## Sequencing

```
W1 ─► W2 ─► W3 ─► W5 ─► W6
             └─► W4 ──┘        (W4 parallel with W5)
```

## Risks

| Risk | Mitigation |
|---|---|
| Relaxing `client_id` breaks TG request flows | golden serialization tests + full regression before merge; CHECK constraint keeps origin invariant |
| Parity drift (portal endpoints diverge from webapp semantics) | parity contract tests pinned to webapp fixtures; shared service-layer serializers |
| Notification spam / unbounded growth | kind-level dedup (skip if identical unread kind+entity exists), prune beat task |
| Buyer company context confusion (multi-company accounts) | every write carries explicit company_id; UI shows active-company header in wizard/inquiry forms |
| Moderation team confusion over origins | origin badges in dashboard + TG cards (W4) ship before portal GA of R2 features |
