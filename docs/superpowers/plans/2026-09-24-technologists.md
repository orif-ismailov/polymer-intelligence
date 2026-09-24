# Technologists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A two-sided marketplace of independent process technologists inside IMEX: experts apply and publish a moderated profile, verified companies post requests, experts send offers and chat, the company accepts one (contacts revealed), completes and reviews.

**Architecture:** A new bounded context `backend/app/domains/technologists/` (models, catalog, service, schemas, three routers: public, portal, admin), modelled on `domains/logistics` (broadcast pool + per-party thread). A technologist is a `user_accounts` row with `applied_as='technologist'` and NO company; its routes are keyed on the account. Portal gets a public catalog (SSR), an expert cabinet that bypasses `RequireCompany`, and a company-side request flow; the shared `ThreadChat` switches to a server-computed `mine` flag.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Postgres; React 18 + Vite + TanStack Query + i18next (portal, FSD); Next.js dashboard.

**Spec:** `docs/superpowers/specs/2026-09-24-technologists-design.md`

## Global Constraints

- Migration is `0055_technologists.py`, `down_revision = "0054"` (check `alembic heads` first).
- Real-DB tests use `tests/_verification_db.py` helpers and `@requires_real_db`; add every new table to `_TABLES` in FK order (children first).
- Enums: plain `Text` + `CheckConstraint` in SQL, `Literal` in Python (no new PG ENUM types — matches `volume_unit`/`incoterms` precedent, no migration to add a value).
- Domain exceptions without `Error` suffix. `ruff check .`, `mypy app`, full `pytest tests/` must be green; real-DB run compared with the 49-failure baseline.
- i18n: portal `ru`/`uz`/`en`; dashboard `ru`/`uz`/`tr`/`fa`/`zh`.
- Notification kinds are added to `notification_service` AND portal locale `notifications.<kind>.title|body`.
- No Co-Authored-By footer. Commit/push only when the user asks.
- Every user-reachable step verified in a real browser (chrome-devtools) before claiming it works; temp data deleted afterwards; user's real companies/deals untouched.

## File Structure

Backend (new):
- `backend/alembic/versions/0055_technologists.py` — `user_accounts.applied_as` + 7 tables.
- `backend/app/domains/technologists/__init__.py`
- `.../catalog.py` — closed sets (`INDUSTRIES`, `PROCESSES`, `MATERIALS`, `NEED_TYPES`, `URGENCIES`, `REQUEST_FORMATS`, `PROFILE_FORMATS`, `CAPACITY_UNITS`, `CURRENCIES`) + `Literal` aliases.
- `.../models.py` — `TechnologistProfile`, `TechRequest`, `TechRequestInvite`, `TechOffer`, `TechThread`, `TechMessage`, `TechReview`.
- `.../profiles.py` — profile service (get/upsert/submit/photo, moderation, public listing).
- `.../requests.py` — request/offer/invite/thread/message/review service + state machine.
- `.../schemas.py` — all pydantic in/out models.
- `.../api_public.py`, `.../api_portal.py`, `.../api_admin.py`.
- Tests: `tests/test_technologist_profiles_db.py`, `tests/test_tech_requests_db.py`, `tests/test_portal_technologists_api.py`, `tests/test_admin_technologists_api.py`, `tests/test_migration_0055.py`.

Backend (modified): `app/models/__init__.py`, `app/main.py` (3 routers), `app/core/pages.py` (`technologists` page), `app/core/numbering.py` (`LOCK_BASE_TECH_REQUEST`), `app/services/notification_service.py` (6 kinds), `app/services/storage_service.py` (`store_tech_chat_file`, `store_technologist_photo`), `app/domains/accounts/{models,schemas,service,api_portal,api_admin}.py` (`applied_as`), `tests/_verification_db.py`, `tests/test_openapi_errors.py` expectations if needed.

Portal (new): `entities/technologist/` (types, api, hooks, `TechnologistCard`), `entities/tech-request/` (types, api, hooks), `features/tech-offer/` (offer form), `features/tech-request-form/`, `pages/technologists/` (public list + profile), `pages/expert/` (profile editor, feed, request detail), `pages/tech-requests/` (company list, new, detail). Modified: routes, `RequireCompany`, `publicRoutes.ts`, `ssr/prefetch.ts`, `server.js` public patterns, public + cabinet nav, `RegisterForm` (`as=technologist`), `ThreadChat` (`mine`), `entities/account` types, locales.

Dashboard (new): `app/[locale]/(dashboard)/technologists/page.tsx` (+ `[id]/page.tsx`), `lib/api` calls; modified: `lib/nav.ts`, messages ×5, portal-accounts page (applied_as column/filter).

---

### Task 1: Schema — migration 0055 + models + catalog

**Files:**
- Create: `backend/alembic/versions/0055_technologists.py`, `backend/app/domains/technologists/{__init__,catalog,models}.py`
- Modify: `backend/app/models/__init__.py`, `backend/app/domains/accounts/models.py`, `backend/tests/_verification_db.py`
- Test: `backend/tests/test_migration_0055.py`

**Interfaces — Produces:** ORM classes named above; `UserAccount.applied_as: str`; `catalog.PROCESSES: tuple[str, ...]` etc.

- [ ] **Step 1: Failing migration test** — upgrade to head, assert tables exist, `applied_as` default `'company'`, check constraints refuse `applied_as='x'`, `tech_offers` partial unique refuses a second `submitted` offer for (request, profile), `tech_reviews.rating` refuses 6; downgrade to 0054 drops them.

```python
@requires_real_db
def test_0055_tables_and_constraints(engine) -> None:
    insp = sa.inspect(engine)
    for t in ("technologist_profiles", "tech_requests", "tech_request_invites",
              "tech_offers", "tech_threads", "tech_messages", "tech_reviews"):
        assert insp.has_table(t), t
    cols = {c["name"]: c for c in insp.get_columns("user_accounts")}
    assert "applied_as" in cols
    with engine.begin() as c, pytest.raises(sa.exc.IntegrityError):
        c.execute(sa.text("INSERT INTO user_accounts (phone, applied_as) VALUES ('+998900000099','x')"))
```

- [ ] **Step 2:** `pytest tests/test_migration_0055.py -q` → FAIL (tables missing).
- [ ] **Step 3: Migration.** `technologist_profiles` (unique `user_account_id` FK CASCADE; arrays `sa.ARRAY(sa.Text)` NOT NULL default `'{}'`; `status` Text check in 5 values default `draft`; `published_snapshot` JSONB null; `rating_avg` Numeric(3,2) null; `rating_count` int default 0; `reviewed_by` FK `staff_users`); `tech_requests` (`number` unique, `public_id` uuid default `gen_random_uuid()`, `company_id` FK companies, all spec fields, `status` check `open|assigned|completed|cancelled`, `source` check `form|ai`, `assigned_offer_id` BigInteger null — FK added after `tech_offers` exists, `ix_tech_requests_open (status, created_at)`, `ix_tech_requests_company (company_id, status)`); `tech_request_invites` unique (request_id, profile_id); `tech_offers` (check `price > 0`, `duration_days > 0`, status check, partial unique index `uq_tech_offers_active ON (request_id, profile_id) WHERE status IN ('submitted','accepted')`); `tech_threads` unique (request_id, profile_id); `tech_messages` (`author_kind` check, `ck_tech_message_not_empty` like logistics); `tech_reviews` (unique request_id, check rating 1..5). Downgrade drops in reverse + column.
- [ ] **Step 4: Models + catalog** mirroring the migration exactly; register `import app.domains.technologists.models  # noqa: F401` after logistics in `app/models/__init__.py`; add `applied_as` mapped column to `UserAccount`; add the 7 tables to `_TABLES` before `portal_notifications`/`companies` (messages → threads → reviews → offers → invites → requests → profiles; `tech_requests.assigned_offer_id` is nulled by DELETE order because offers go first — so drop `assigned_offer_id` FK as `ondelete="SET NULL"`).
- [ ] **Step 5:** `pytest tests/test_migration_0055.py -q` PASS; `ruff check . && mypy app`.

### Task 2: `applied_as` through the application flow

**Files:** Modify `accounts/schemas.py` (`RegisterIn.applied_as: Literal["company","technologist"] = "company"`; `company_name` becomes optional **only** when technologist — model validator; `AccountOut.applied_as: str = "company"`; admin out schema gains `applied_as`), `accounts/service.py` (`register(..., applied_as)` stores it; `applied_company_name` holds the specialisation text for experts), `accounts/api_portal.py` (pass through), `accounts/api_admin.py` (`list_portal_accounts(applied_as: str | None = Query(None))`).
Test: extend `tests/test_portal_auth_api.py` / `tests/test_admin_portal_accounts_api.py` (whichever holds register/list) — register with `applied_as="technologist"` and no company_name → 202, row has `applied_as='technologist'`; `applied_as="company"` without company_name → 422; admin list `?applied_as=technologist` returns only experts; `/portal/me` exposes `applied_as`.

- [ ] Steps: failing tests → run (FAIL) → implement → PASS → ruff/mypy.

### Task 3: Profile service + moderation + public read

**Files:** Create `technologists/profiles.py`, `technologists/schemas.py` (profile part), `storage_service.store_technologist_photo(account_id, content, filename) -> str` (images only, reuse `validate_upload` + the logo mime set). Test `tests/test_technologist_profiles_db.py`.

**Interfaces — Produces:**
```python
class NotATechnologist(Exception): ...          # account.applied_as != 'technologist' or not active
class ProfileIncomplete(Exception): ...          # args[0] = list[str] of missing fields
class InvalidProfileTransition(Exception): ...
REQUIRED_FIELDS = ("full_name", "title", "country", "years_experience", "processes", "languages", "work_formats")
def get_or_create_own(db, account: UserAccount) -> TechnologistProfile
def update_own(db, account, data: TechnologistProfileIn) -> TechnologistProfile   # published → stays published, marks `has_pending_changes` by moving to pending_review while snapshot keeps serving
def submit_own(db, account) -> TechnologistProfile                                  # draft|rejected|published(with edits) → pending_review; ProfileIncomplete
def approve(db, profile, staff_user_id) -> None                                    # pending_review → published; snapshot = public_card(profile); audit technologist.approve; notify
def reject(db, profile, staff_user_id, reason: str) -> None                        # pending_review → rejected (snapshot untouched — a published expert with rejected edits stays listed)
def suspend(db, profile, staff_user_id, reason: str) -> None                       # published → suspended; snapshot kept but not listed
def public_card(profile) -> dict[str, object]                                      # no contacts
def list_published(db, *, process, material, language, country, q, limit, offset) -> tuple[list[TechnologistProfile], int]
def is_listed(profile) -> bool   # status == published OR (status in (pending_review, rejected) AND snapshot is not None)
```
Listing reads `published_snapshot` (so pending edits never leak), filters with `snapshot->'processes' ? :p` style JSONB containment (`TechnologistProfile.published_snapshot["processes"].contains([p])`), `q` ILIKE on snapshot name/title/bio.

Tests (real DB): non-technologist account → `NotATechnologist`; submit with missing fields → `ProfileIncomplete(["title", ...])`; approve → listed, snapshot has no `contact_phone`; edit after publish → still listed with OLD title until re-approved; reject pending edits of a published profile → still listed with old snapshot; suspend → not listed; filters by process/material/language work; audit rows written.

- [ ] Steps: failing tests → FAIL → implement → PASS → ruff/mypy.

### Task 4: Request/offer/thread/review service + state machine

**Files:** Create `technologists/requests.py`, extend `schemas.py`; `numbering.LOCK_BASE_TECH_REQUEST = 42_000`; `storage_service.store_tech_chat_file` (`_store_chat_file("tech-chat", ...)`); notification kinds in `notification_service`:
`KIND_TECH_REQUEST_NEW="tech_request_new"`, `KIND_TECH_INVITE="tech_invite"`, `KIND_TECH_OFFER_NEW="tech_offer_new"`, `KIND_TECH_OFFER_DECIDED="tech_offer_decided"`, `KIND_TECH_MESSAGE="tech_message"`, `KIND_TECHNOLOGIST_DECIDED="technologist_decided"`.
Test: `tests/test_tech_requests_db.py`.

**Interfaces — Produces:**
```python
class TechRequestNotFound(Exception): ...        # also "not yours / not visible" — one answer
class InvalidTechTransition(Exception): ...
class OfferConflict(Exception): ...              # second active offer
def generate_number(db) -> str                   # IMX-TECH-000001 (global sequence tech_request_seq)
def create_request(db, *, company: Company, account, data: TechRequestIn, source="form") -> TechRequest  # company must be verified (CompanyStatus.verified) else InvalidTechTransition("company_not_verified"); notifies matching published experts (process ∈ snapshot processes) via notify_account(dedup)
def update_request(db, request, data) -> TechRequest     # open and no offers
def cancel_request(db, request, account) -> None         # open|assigned → cancelled; submitted offers → declined
def invite(db, request, profile_id, account) -> TechRequestInvite  # idempotent; profile must be listed; notify
def feed_for(db, profile, *, invited_only=False, limit, offset) -> list[TechRequest]  # open, profile listed
def get_for_expert(db, profile, request_id) -> TechRequest  # open OR has my offer/thread
def company_visible_to(db, request, profile) -> bool      # a thread exists for (request, profile)
def submit_offer(db, request, profile, data: TechOfferIn) -> TechOffer  # request open, profile listed; OfferConflict; opens thread; notify company members
def update_offer / withdraw_offer(db, offer, profile)     # only submitted
def accept_offer(db, request, offer, account) -> None     # open → assigned, offer accepted, others declined; notify all affected experts; audit
def decline_offer(db, request, offer, account) -> None
def complete(db, request, account, rating: int, text: str | None) -> TechReview  # assigned → completed; review; profile.rating_avg/count recomputed
def open_thread(db, request, profile) -> TechThread       # idempotent; expert side (request must be visible) or company side (profile must have an offer or invite)
def get_thread_for_company(db, account, company_id, thread_id) / get_thread_for_expert(db, profile, thread_id) -> tuple[TechThread, TechRequest]
def post_message(db, thread, *, author_kind, account, body, file_content=None, file_name=None) -> TechMessage
def list_messages(db, thread, *, after_id=None, limit=100) -> list[TechMessage]
def contacts_visible(request, profile) -> bool            # status in (assigned, completed) and assigned offer's profile == profile
```
Tests (real DB): unverified company refused; feed shows open only, excludes cancelled/assigned; anonymisation helper false before thread, true after; offer on assigned request refused; second offer → `OfferConflict`; withdraw then re-offer allowed; accept flips statuses (others declined) and `contacts_visible`; complete requires assigned; rating avg after two completed requests = mean; notifications rows created for matching experts only (process filter); message with neither body nor file → ValueError; non-party thread access → `TechRequestNotFound`.

- [ ] Steps: failing tests → FAIL → implement → PASS → ruff/mypy.

### Task 5: Routers — public, portal, admin

**Files:** Create `api_public.py` (`/public/technologists`, `/public/technologists/facets`, `/public/technologists/{profile_id}`), `api_portal.py` (expert: `/portal/me/technologist`, `/submit`, `/photo`, `/requests`, `/requests/{id}`, `/requests/{id}/offer` POST/PUT/DELETE, `/requests/{id}/thread` POST, `/threads`; company: `/portal/companies/{company_id}/tech-requests` list/create, `/{id}` get/put, `/{id}/cancel`, `/{id}/offers`, `/{id}/offers/{offer_id}/accept|decline`, `/{id}/complete`, `/{id}/invites`, `/{id}/threads/{profile_id}` POST (company opens); threads: `/portal/tech-threads/{thread_id}/messages` GET/POST + `/messages/{mid}/file`, where the caller is resolved as expert (own profile) or company member (`?company_id=`)), `api_admin.py` (`require_page("technologists", ...)`: list, get, approve, reject, suspend). Register in `app/main.py` with `responses=errors.PUBLIC|PORTAL|STAFF` like siblings; add `PageSpec("technologists", "counterparties")` in `core/pages.py`.
Message out carries `mine: bool` and `author_kind`; company payloads for the expert omit `company_id`/name unless `company_visible_to`; contacts block present only when `contacts_visible`.
Test: `tests/test_portal_technologists_api.py`, `tests/test_admin_technologists_api.py` — route order (literal before param), anonymous public list has no `contact_phone` key, member of another company → 404 on request, company account hitting `/portal/me/technologist` → 403 `not_a_technologist`, expert feed item has `company: null` before thread, accept → both sides see contacts, admin approve requires page grant (403 without), `test_openapi_errors` stays green.

- [ ] Steps: failing tests → FAIL → implement → PASS → full `pytest tests/ -q` + real-DB run; ruff/mypy.

### Task 6: Portal — `ThreadChat` `mine` + account `applied_as` + routing gate

**Files:** `features/thread-chat/ui/ThreadChat.tsx` (`ThreadMessage.mine?: boolean`; `isMine = m.mine ?? m.author_company_id === companyId`; `companyId` optional), `entities/account` types (`applied_as`), `app/router/RequireCompany.tsx` (an account with `applied_as === "technologist"` → `<Navigate to="/cabinet/expert" />` instead of onboarding), new `RequireTechnologist` guard, `features/register-account/ui/RegisterForm.tsx` (`?as=technologist`: hides company name, shows «Специализация», sends `applied_as`).
Verify: lint/typecheck; existing logistics/lab/manufacturer chats still render mine/theirs in the browser.

### Task 7: Portal — public catalog + profile page (SSR) + menu

**Files:** `entities/technologist/{model/types.ts,model/api.ts,model/hooks.ts,ui/TechnologistCard.tsx,index.ts}`, `pages/technologists/ui/{TechnologistsPage,TechnologistPage}.tsx`, routes `/technologists`, `/technologists/:profileId` in the public block, `SERVER_RENDERED_PATTERNS` + `server.js` literal patterns, `ssr/prefetch.ts` branch, `PublicTopNav`/`PublicMobileNav`/`SideNav` item «Технологи» after laboratories, locales `technologists.*`, `public.nav.technologists`.
Page: hero with two CTAs (spec), filter bar (process, material, language, country, q — URL params like `PublicDirectoryPage`), card grid, pagination; profile page: all public fields, rating, «Пригласить к заявке» (signed-in company member with open requests → select + POST invites).

### Task 8: Portal — expert cabinet

**Files:** `pages/expert/ui/{ExpertProfilePage,ExpertRequestsPage,ExpertRequestPage}.tsx`, `features/tech-offer/ui/TechOfferForm.tsx`, an `ExpertShell` (reuse `AppShell` with a technologist nav variant — prop, not a copy), routes under `/cabinet/expert` behind `RequireTechnologist`.
Profile editor: chips multi-select for closed sets (reuse existing chip/multiselect primitive from `shared/ui`), photo upload, status banner (draft/pending/published/rejected with reason/suspended), «Отправить на проверку». Feed: tabs «Все»/«Приглашения», cards with process/material/capacity/city/format/urgency, company hidden. Request page: details, my offer form/state, chat (`ThreadChat` with the tech-thread api adapter), contacts card when accepted.

### Task 9: Portal — company side

**Files:** `entities/tech-request/*`, `features/tech-request-form/ui/TechRequestForm.tsx`, `pages/tech-requests/ui/{TechRequestsPage,TechRequestNewPage,TechRequestDetailPage}.tsx`, routes `/cabinet/tech-requests{,/new,/:requestId}`, cabinet nav item, `RequireFeature`-free (any verified company).
Detail: request card with status + cancel; offers list (expert card, price, duration, format, scope) with «Принять»/«Отклонить» and «Написать»; per-expert chat drawer; contacts card after accept; «Работа выполнена» dialog with 1–5 rating + text.

### Task 10: Dashboard — moderation + applications

**Files:** `app/[locale]/(dashboard)/technologists/page.tsx` (queue with status tabs), `technologists/[id]/page.tsx` (full profile incl. contacts, approve/reject with reason/suspend), `lib/nav.ts` item under counterparties (`key: "technologists"`), messages ×5, portal-accounts page: `applied_as` badge + filter.
Verify: `npm run lint && npm run typecheck`; nav catalog test.

### Task 11: Notifications i18n + deep links

**Files:** portal locales `notifications.tech_*` + `technologist_decided`; notification-center link resolver: `tech_request` → expert `/cabinet/expert/requests/:id` or company `/cabinet/tech-requests/:id` (by `params.side`), `tech_thread` likewise, `technologist` → `/cabinet/expert`.

### Task 12: Gates + browser loop + docs

- [ ] `cd backend && ruff check . && mypy app && pytest tests/ -q`; real-DB run vs baseline 49.
- [ ] `cd portal && npm run lint && npm run typecheck && npm run build`; `cd dashboard && npm run lint && npm run typecheck`.
- [ ] `make dev`; chrome-devtools loop from the spec's Testing section; confirm rows in Postgres; screenshots of catalog/profile/feed/detail; console clean.
- [ ] Delete temp accounts/companies/requests; `backend/CLAUDE.md` domain count (20 → 21) + a short technologists gotcha; root `CLAUDE.md` domain list; `portal/CLAUDE.md` route note.
- [ ] Report to the user; commit only on request.
