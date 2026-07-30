# R1 — Portal foundation: accounts, companies, verification, offers

> Prereq reading: `00-IMPLEMENTATION-CONTEXT.md` (binding conventions), `ARCHITECTURE.md` §5 (schema), §6 (state machines + locking), §9 (workflows), Amendments A1/A2.
> Supersedes P1-PLAN.md. No gov APIs in R1. `webapp/` is frozen.

**Goal:** a person registers in the new `portal/` app by phone (SMS OTP via Eskiz), creates one or more companies, submits each through verification (manual path; E-IMZO button slot reserved, disabled), staff decide cases in the dashboard or via Telegram inline buttons, and a **verified** company publishes offers from the portal that flow through the existing offer-moderation pipeline into the public market with a verified badge.

**Demo script (Definition of Done):** on the dev stack — register by phone (console SMS driver prints the code in worker logs) → create 2 companies → submit both → approve one from dashboard `/verification`, the other via Telegram group buttons → bot posts case cards; approvals write audit rows → in the portal, switch active company to the verified one → create an offer → offer appears in dashboard moderation queue → approve → offer visible in public market API with `company_verified: true` and the company name. Second registration from another phone confirms multi-account isolation (cannot see the first account's companies — 404, not 403).

---

## Wave 1 — Schema, enums, models, crypto, config

### T1.1 Enums — `backend/app/models/enums.py`
Add `(str, Enum)` classes (PG enum type name in parens):
- `AccountStatus(account_status)`: active, blocked
- `CompanyStatus(company_status)`: draft, pending_verification, verified, rejected, suspended, liquidated
- `CompanyMemberRole(company_member_role)`: owner, manager, member
- `CompanyMemberStatus(company_member_status)`: active, invited, removed
- `CompanyBusinessRole(company_business_role)`: manufacturer, importer, trader, logistics_provider, distributor, laboratory, insurance_provider
- `BusinessRoleStatus(business_role_status)`: declared, confirmed, revoked
- `BankAccountStatus(bank_account_status)`: unverified, pending, verified, failed, archived
- `BankVerificationMethod(bank_verification_method)`: document, e_invoice_crosscheck, bank_api, manual
- `VerificationCaseType(verification_case_type)`: onboarding, reverification, targeted
- `VerificationCaseStatus(verification_case_status)`: draft, submitted, checks_running, needs_info, pending_review, approved, rejected, cancelled
- `VerificationCheckType(verification_check_type)`: tax_id_format, bank_requisites, documents_complete, manual_kyb   *(R3 adds eimzo_signature via ALTER TYPE ADD VALUE; P2 adds gov_registry/tax_status/vat_status)*
- `VerificationCheckStatus(verification_check_status)`: pending, running, passed, warning, failed, unavailable, waived
- `VerificationDocumentKind(verification_document_kind)`: registration_certificate, director_id, bank_letter, license, permit, certificate, power_of_attorney, other
- `DocumentReviewStatus(document_review_status)`: pending_review, accepted, rejected

### T1.2 Models
**`backend/app/models/accounts.py`** — `UserAccount`: id BigInt PK; phone Text UNIQUE NOT NULL (E.164); name Text NULL; language String(2) default 'ru'; status AccountStatus default active; telegram_user_id BigInteger NULL UNIQUE (dormant bridge); created_at; last_login_at. `SmsSendLog`: id; phone; purpose Text ('otp'); provider Text; provider_msg_id Text NULL; status Text; created_at. Index on (phone, created_at) for daily-cap queries.

**`backend/app/models/companies.py`** — per ARCHITECTURE §5 with the A1 change: `Company` (public_id UUID unique server-default gen_random_uuid(); jurisdiction CHAR(2) default 'UZ'; tax_id; legal_name; short_name; legal_form; legal_address; director_name; registration_date; registry_status NULL; status CompanyStatus default draft; verified_at; reverification_due_at; counterparty_id FK NULL; created_by_user_account_id FK NOT NULL; created_at/updated_at; UNIQUE(jurisdiction, tax_id)); `CompanyMember` (company_id FK, **user_account_id FK**, member_role, status, invited_by_user_account_id NULL, created_at, UNIQUE(company_id, user_account_id)); `CompanyBusinessRole` (UNIQUE(company_id, role)); `CompanyBankAccount` (bank_mfo CHAR(5); bank_name; account_number_enc LargeBinary NOT NULL; account_last4 CHAR(4); currency CHAR(3) default 'UZS'; status; verification_method NULL; evidence_document_id FK NULL; verified_at; verified_by FK staff_users NULL; created_at).

**`backend/app/models/verification.py`** — `VerificationCase` (company_id FK; case_type; status default draft; submitted_at; decided_at; decided_by FK staff_users NULL; decision_note; created_at); `VerificationCheck` (case_id FK; check_type; status default pending; result JSONB NULL; attempts int default 0; last_error; started_at; finished_at; waived_by FK NULL; waive_reason; UNIQUE(case_id, check_type)); `VerificationDocument` (company_id FK; case_id FK NULL; kind; storage_path; mime_type; size_bytes; sha256 Text NOT NULL; uploaded_by_user_account_id FK; status default pending_review; review_note; reviewed_by FK staff_users NULL; reviewed_at; expires_at NULL; created_at).

**`backend/app/models/events.py`** — `DomainEvent`: id BigInt PK; event_type Text; aggregate_type Text; aggregate_id Text; payload JSONB; occurred_at default now(); published_at NULL; attempts int default 0.

Register in `backend/app/models/__init__.py` in order: accounts → companies → verification → events (after existing counterparties/staff imports).

### T1.3 Migration `0017_company_verification`
All enums above; all tables above; indexes: partial unique `ux_open_case ON verification_cases(company_id) WHERE status NOT IN ('approved','rejected','cancelled')`; `ix_outbox_unpublished ON domain_events(id) WHERE published_at IS NULL`. Marketplace alters: `seller_offers ADD company_id BIGINT NULL FK companies`, `ADD created_by_user_account_id BIGINT NULL FK user_accounts`, `ALTER seller_id DROP NOT NULL`, `ADD CONSTRAINT ck_offer_origin CHECK (seller_id IS NOT NULL OR company_id IS NOT NULL)`; `sellers ADD company_id NULL FK`, `clients ADD company_id NULL FK` (dormant). Downgrade reverses everything (restore seller_id NOT NULL only after asserting no NULL rows).

### T1.4 Crypto + config
`backend/app/core/crypto.py`: `encrypt_pii(plain: str) -> bytes`, `decrypt_pii(token: bytes) -> str` using Fernet with key = `settings.VERIFICATION_ENC_KEY`. Settings additions in `backend/app/core/config.py`: `VERIFICATION_ENC_KEY` (required, min length validated), `SMS_PROVIDER` default `"console"`, `ESKIZ_EMAIL`/`ESKIZ_PASSWORD` default `""` + model validator requiring them when `SMS_PROVIDER == "eskiz"`, OTP tunables and `PORTAL_SESSION_TTL_DAYS` (defaults per 00-CONTEXT), optional `VERIFICATION_NOTIFY_CHAT_ID: int | None = None`. Add `cryptography` to `backend/pyproject.toml`, run `uv lock`. Same commit: `deploy/.env.example`, CI placeholder envs (all backend jobs + e2e job), Makefile smoke env if it injects placeholders.

### T1.5 DB docs
Extend the DB architecture doc in `docs/` with every new table, column, enum, index (same commit as 0017).

**Acceptance W1:** upgrade/downgrade clean on dev DB copy; `uv run python -c "import app.models"` ok; full existing suite green; existing offer create/moderate tests still pass (nullable seller_id regression).

## Wave 2 — Outbox + `verify` queue

### T2.1 `backend/app/services/event_service.py` + `event_types.py`
`emit(db: Session, event_type: str, aggregate_type: str, aggregate_id: str | int, payload: dict) -> None` — constructs DomainEvent, `db.add`, `db.flush()`. Never commits. `event_types.py`: string constants — `COMPANY_REGISTERED`, `COMPANY_PROFILE_UPDATED`, `VERIFICATION_CASE_SUBMITTED`, `VERIFICATION_CHECK_COMPLETED`, `VERIFICATION_CASE_NEEDS_INFO`, `VERIFICATION_CASE_APPROVED`, `VERIFICATION_CASE_REJECTED`, `COMPANY_VERIFIED`, `COMPANY_SUSPENDED`, `COMPANY_REINSTATED`, `OFFER_PUBLISHED_BY_COMPANY` (R1 set; R2/R3 extend).

### T2.2 `backend/app/tasks/events.py`
Beat task `dispatch_domain_events` (name `app.tasks.events.dispatch_domain_events`, every 15 s in `schedule.py`): select batch 200 `WHERE published_at IS NULL ORDER BY id FOR UPDATE SKIP LOCKED`; for each, route via `CONSUMERS: dict[str, list[celery task signature]]` mapping event_type → tasks (dispatched with event id + payload); set `published_at`, commit batch. Consumers must be idempotent — every consumer task starts by checking natural state (e.g., notification tasks accept re-delivery; state mutations are status-guarded). Add module to `_TASK_MODULES`.

### T2.3 `verify` queue
`celery_app.py`: add `Queue("verify")` to `task_queues`; route `app.tasks.verification.*` → verify in `task_routes`. Compose: extend both `-Q` flags to `ingest,parse,notify,default,verify` (`deploy/docker-compose.yml:207`, `deploy/docker-compose.dev.yml:131`). Update queue contract in `deploy/CLAUDE.md`.

**Acceptance W2:** test — emit inside rolled-back tx leaves nothing; two dispatchers running concurrently publish each event exactly once (SKIP LOCKED); unknown event_type is skipped with warning, not crash; worker boots with 5 queues.

## Wave 3 — Accounts & OTP auth (parallel with W2 after W1)

### T3.1 SMS port — `backend/app/integrations/__init__.py` + `backend/app/integrations/sms/`
`base.py`: `class SmsProvider(Protocol): provider_name: str; async def send(self, phone: str, text: str) -> SmsSendResult` (`SmsSendResult`: ok, provider_msg_id, error). `console.py`: logs `OTP for {phone}: {text}` at INFO, returns ok (dev/CI). `eskiz.py`: auth `POST https://notify.eskiz.uz/api/auth/login` (email/password → JWT, cache in module state, refresh on 401), send `POST /api/message/sms/send` (fields: mobile_phone digits, message, from). `get_sms_provider()` factory reads `settings.SMS_PROVIDER`. Every send → `SmsSendLog` row (separate short transaction).

### T3.2 `backend/app/services/otp_service.py`
- `request_code(db, redis, phone, ip) -> None`: normalize to E.164 (uz default +998, accept international), validate; enforce: cooldown key `otp:cd:{phone}` (60 s), daily counters `otp:day:{phone}` and `otp:day:ip:{ip}` (TTL to midnight UTC, max 5); generate 6-digit code (`secrets.randbelow`), store `otp:code:{phone}` = sha256(code) with TTL 300 s and attempts counter reset; enqueue `send_sms` notify task (fail-soft). Always returns None (uniform); over-limit raises `OtpRateLimited` mapped to 429 with retry-after.
- `verify_code(db, redis, phone, code) -> UserAccount`: fetch hash; missing/expired → `OtpInvalid`; increment attempts, >5 → delete key + `OtpLocked`; constant-time compare; success → delete key, upsert UserAccount by phone (create active, set last_login_at), return.
- Codes never logged (console provider is the only place a code is printed, and only there).

### T3.3 Portal auth API + dep
`backend/app/api/portal/__init__.py`, `auth.py` router (mounted under `/api/v1/portal` in `create_app`):
- `POST /portal/auth/otp/request` `{phone}` → 204 (or 429)
- `POST /portal/auth/otp/verify` `{phone, code}` → sets httpOnly refresh cookie `portal_session` (30 d, Secure, SameSite=Lax, path=/api/v1/portal) + returns `{access_token (JWT HS256, aud="portal", sub=account.id, exp=15m), account: {...}}`
- `POST /portal/auth/refresh` → rotates cookie, new access token
- `POST /portal/auth/logout` → clears cookie
- `GET /portal/me` / `PATCH /portal/me` `{name?, language?}`
Dep `get_current_account` in `backend/app/api/deps.py`: decode Bearer, require `aud=="portal"`, load UserAccount, 401 unknown/expired, 403 blocked. Staff/webapp tokens must fail here and vice versa (audience checks on both sides).
Schemas: `backend/app/schemas/portal.py`.

**Acceptance W3:** tests — cooldown 429; daily cap; attempt lockout; wrong code uniform error; success path issues working token; audience isolation both directions; blocked account 403; refresh rotation invalidates old cookie; `SmsSendLog` written; code absent from logs (assert on caplog).

## Wave 4 — Company & verification domain

### T4.1 `backend/app/services/company_service.py`
API (all typed, mypy-strict): `create_company(db, account, jurisdiction, tax_id) -> Company` (STIR format check: UZ = 9 digits; IntegrityError on (jurisdiction,tax_id) → `CompanyAlreadyRegistered`; creator becomes owner member; emit COMPANY_REGISTERED; audit `company.create`); `list_my_companies(db, account)`; `get_company_for(db, account, company_id)` → membership check, else `CompanyNotFound` (404 semantics — do not reveal existence); `update_profile(...)` allowed only in status draft|needs_info-case-open, emits COMPANY_PROFILE_UPDATED; `set_business_roles(...)`; `add_bank_account(...)` (encrypt via crypto, store last4; MFO must be 5 digits); `company transitions` via module-level `_TRANSITIONS: dict[CompanyStatus, set[CompanyStatus]]` + `transition(db, company, to, actor)` writing audit. Owner guard: cannot remove/demote last active owner (`LastOwnerRemoval`).

### T4.2 `backend/app/services/verification_service.py` + `verification_checks.py`
- `open_case(db, company, case_type=onboarding)`: company must be draft|rejected; IntegrityError on partial index → `CaseAlreadyOpen`; sets company → pending_verification.
- `submit_case(db, company, account)`: create VerificationCheck rows (all four P1 types), case → submitted → checks_running, emit VERIFICATION_CASE_SUBMITTED, dispatch `run_verification_checks.apply_async(args=[case.id], queue="verify")` fail-soft.
- `verification_checks.py` pure functions returning `CheckResult(status, result_payload)`: `check_tax_id_format(company)`; `check_bank_requisites(company, accounts)` (5-digit MFO, 20-digit account, at least one account present → passed; none → warning); `check_documents_complete(company, documents, declared_roles)` (registration_certificate required always; bank_letter required iff bank account added; missing → failed with missing-kinds list); `check_manual_kyb()` → always `pending` (human item shown in admin UI as checklist).
- Evaluator `on_check_completed(db, case_id)`: `SELECT … FOR UPDATE` case; if any check failed → case needs_info (emit VERIFICATION_CASE_NEEDS_INFO); elif all in {passed, warning, waived} and manual_kyb decided → auto path: if `settings_service.get(db,'verification_auto_approve')` → approve(system) else pending_review (emit + notify); else stay checks_running.
- Decisions: `approve/reject/request_info(db, case, staff_user | telegram_actor)`: optimistic `UPDATE verification_cases SET status=… WHERE id=… AND status='pending_review'`; rowcount 0 → `AlreadyDecided` (idempotent no-op for TG). Approve → company verified (verified_at, reverification_due_at=+365 d), emit VERIFICATION_CASE_APPROVED + COMPANY_VERIFIED; audit `vercase.approve` etc. `waive_check(db, check, admin, reason)` — require reason, audit, re-run evaluator.

### T4.3 Document vault — extend `backend/app/services/storage_service.py`
`upload_verification_document(db, company, account, kind, content, filename) -> VerificationDocument`: extend `MAGIC_BYTES` with PNG (`\x89PNG\r\n\x1a\n`); allowed: pdf, jpeg, png; 10 MB; max 20 docs/company; key `verification/{company_id}/{token}-{safe_basename}`; sha256 stored. `presign_verification_document(document, ttl=600)` — used by both portal (member) and dashboard (staff) endpoints.

### T4.4 `backend/app/tasks/verification.py`
Tasks (queue verify): `run_verification_checks(case_id)` → dispatch `run_single_check(check_id)` per pending check; `run_single_check` sets running → executes pure function → writes result → emits VERIFICATION_CHECK_COMPLETED → calls evaluator task. Retry policy for `unavailable`: `self.retry(countdown=60*attempts, max_retries=5)` (P1 checks can't be unavailable, but the path is load-bearing for P2/R3 — implement + test it). Add to `_TASK_MODULES`.

**Acceptance W4:** transition-table tests (every legal/illegal case + company transition); double-approve concurrency test (two sessions); evaluator race test (two checks complete simultaneously → one evaluation); docs-complete matrix by role; membership isolation (account B → 404 on account A company); mypy clean.

## Wave 5 — Portal & admin APIs, offers from companies

### T5.1 `backend/app/api/portal/companies.py`
All under `get_current_account`; company-scoped routes resolve через `get_company_for` (404 on non-membership):
- `POST /portal/companies` `{jurisdiction?, tax_id}` → company draft + auto case
- `GET /portal/companies` → list w/ status, active case summary
- `GET /portal/companies/{id}` → full profile, roles, masked bank accounts (`****{last4}`), documents meta, case + checks (user-safe: check_type, status, human-readable requirements; no reviewer identity, no internals)
- `PATCH /portal/companies/{id}`; `PUT /portal/companies/{id}/roles` `{roles: []}`
- `POST /portal/companies/{id}/bank-accounts`; `DELETE …/bank-accounts/{aid}` (archive)
- `POST /portal/companies/{id}/documents` (multipart: kind + file) / `GET …/documents/{did}/download` (presigned redirect) / `DELETE` (only while pending_review)
- `POST /portal/companies/{id}/verification/submit`; `GET /portal/companies/{id}/verification`

### T5.2 `backend/app/api/portal/offers.py` + `offer_service` extension
`offer_service.create_company_offer(db, company, account, payload)` — company.status must be verified (`CompanyNotVerified` → 403 typed body `{code:"company_not_verified"}`); creates SellerOffer with company_id, created_by_user_account_id, seller_id NULL, status pending_moderation — **existing** moderation machine, zero lifecycle changes. `update_company_offer` re-enters pending_moderation on edit of approved/rejected (mirror existing `update_offer` semantics). Routes: `GET /portal/companies/{id}/offers`, `POST …/offers`, `GET/PATCH …/offers/{oid}`, `POST …/offers/{oid}/archive`, file upload via existing `upload_offer_file`. Offer payload fields mirror mini-app 1:1: product_id, grade, price (nullable), currency, qty_available (nullable), availability, incoterms, country, description, files.

### T5.3 Dual-origin offer surfaces
Audit every consumer of `offer.seller`: `offer_service.list_pending` serializer, dashboard moderation API payloads, `send_offer_to_group` template, public market serializers (webapp market endpoints — **read path only, no webapp code changes**: the serializer lives in backend). Add `origin` ("seller"|"company"), `display_name` (company short/legal name or seller company_name), `company_verified: bool`. Golden test: a seller-origin offer's serialized payloads byte-identical to pre-R1 fixtures.

### T5.4 Admin API + settings
`backend/app/api/admin_verification.py`: `GET /admin/verification/cases?status=` (FIFO), `GET /admin/verification/cases/{id}` (checks, documents+presigned, company profile, audit trail extract), `POST …/approve|reject|request-info` (require_analyst_or_admin; body `{note?}`), `POST /admin/verification/checks/{id}/waive` (require_admin, `{reason}` required), `GET /admin/companies?status=&q=`, `GET /admin/companies/{id}`, `POST /admin/companies/{id}/suspend|reinstate` (require_admin; suspend archives company's approved offers via event). `_SPECS` additions: `verification_auto_approve` (bool,false), `bank_verification_required` (bool,false), `verification_required_for_publish` (bool,false — reserved for the frozen TG path, not consumed in R1 logic beyond existing plan).

**Acceptance W5:** authz matrix tests per endpoint (anon/account-nonmember/member/manager/owner/staff-viewer/analyst/admin); unverified company offer → 403 typed; company offer end-to-end through moderation to public payload; golden TG-path test; suspend → offers archived event consumed.

## Wave 6 — Staff surfaces: notify, Telegram, dashboard (parallel with W7)

### T6.1 Notify tasks (`app/tasks/notify.py`)
- `send_verification_case_to_group(case_id)`: card (company name, INN, roles, docs count, checks summary) + inline keyboard `[✅ Одобрить] [❌ Отклонить] [✋ Запросить инфо]`, callback data `vercase:approve|reject|info:{case_id}`; chat = `VERIFICATION_NOTIFY_CHAT_ID or REQUEST_NOTIFY_CHAT_ID`; skip if neither set.
- Wire consumers: VERIFICATION_CASE_SUBMITTED → group card. Client-facing decision notifications in R1 = in-portal status only (no SMS, no TG DM).

### T6.2 Telegram handlers
New `telegram/handlers/verification.py` (router registered where moderation router is): parse `vercase:{action}:{id}`; authz = presser is admin/creator of the notify group (same check as offer moderation); call `verification_service` decision with telegram actor (`staff_user_id=None`, telegram id in audit details); edit the card message with outcome + actor mention; idempotent (AlreadyDecided → answer callback "уже обработано"). `request-info` asks for a reason via force-reply or applies default note. Templates in `telegram/` locales ru/uz/tr.

### T6.3 Dashboard pages
`dashboard/app/[locale]/(dashboard)/verification/page.tsx` — queue table (submitted_at, company, INN, type, checks chips) + detail drawer/route `verification/[id]` (declared profile, per-check status with result payloads, documents list with preview links, decision buttons incl. waive for admin, decision note field, audit trail). `(dashboard)/companies/` — list with status filter + detail with suspend/reinstate. TanStack Query hooks per existing patterns; nav items; all 5 locale message files; `npx next typegen` before typecheck.

**Acceptance W6:** callback idempotency test; task never-raise tests; dashboard e2e (Playwright, existing live-API job): open queue → approve case → status chip flips.

## Wave 7 — Portal frontend (`portal/`, new top-level app)

### T7.1 Scaffold
Vite (latest) + React (latest) + TS strict + Tailwind + shadcn/ui (init with neutral theme) + TanStack Query v5 + react-router-dom v7 + zustand + i18next (ru/uz/en). FSD:
```
portal/src/
  app/        providers (QueryClient, i18n, router, theme), route tree, guards
  pages/      login, otp, dashboard(home), companies, company-create(wizard), company-view,
              verification-status, documents, offers, offer-edit, settings
  widgets/    app-shell (sidebar/topbar + company switcher), case-status-panel, doc-manager
  features/   auth-by-otp, company-wizard, submit-verification, upload-document,
              switch-company, offer-form
  entities/   account, company, verification, offer  (types + api hooks + model)
  shared/     api (fetch client: baseURL /api/v1, auth header, 401→refresh→retry-once),
              ui (shadcn re-exports), lib (phone mask E.164, formatters), config, i18n
```
ESLint flat config `--max-warnings 0`, `npm run lint|typecheck|build|e2e`. **CI:** add `portal` job to `.github/workflows/ci.yml` (npm ci → lint → typecheck → build). npm lockfile: generate with `npx npm@10 install` (npm 11 lockfiles break Docker `npm ci` in this repo).

### T7.2 Auth flow
`/login` phone input (+998 mask, intl allowed) → `/login/code` 6-digit OTP input with resend countdown (uses 429 retry-after) → home. Zustand `authStore` (access token in memory only; refresh via cookie on 401/boot `GET /portal/me`). Route guard redirects anon → /login.

### T7.3 Company cabinet
- Companies list (status badges) + empty-state CTA.
- Create wizard, 4 steps + confirm (URL-addressable steps, zustand draft store): 1) identity — jurisdiction, tax_id, legal_name, legal_form, address, director; **primary button slot "Подтвердить через E-IMZO" rendered disabled with tooltip "скоро" (R3 enables it)**; 2) business roles multi-select; 3) bank account (MFO select/autocomplete + account input, "пропустить" allowed); 4) documents upload per required kinds (kind-labeled dropzones; requirement hints match `check_documents_complete` rules) → confirm & submit.
- Verification status screen: per-check chips (passed/warning/failed/pending/waived + human explanations), `needs_info` banner deep-linking to the offending wizard step with preserved data.
- Company switcher in app shell (persisted active company id).

### T7.4 Offers
List (status chips mirroring moderation states), create/edit form (fields per T5.2, product select from `GET /api/v1/products` reference, file uploads), archive action. Locked state with explainer when active company is not verified.

### T7.5 Deploy
nginx server block `cabinet.ai-imex.com` (dev: `cabinet.localhost` or port): static `portal_static` volume + `location /api/ { proxy_pass http://api:8000; }` same-origin (no CORS changes). `make portal-bundle` mirroring `webapp-bundle`; dev compose service or documented `npm run dev` with `/api` proxy in `vite.config.ts`. Ops note: DNS + TLS cert on host front door (prod host nginx terminates TLS → docker nginx :8080 — see deploy/CLAUDE.md topology).

**Acceptance W7:** CI portal job green; Playwright e2e vs live API (console SMS driver; test hook endpoint or log-scrape for the code in CI — implement `GET /portal/auth/otp/peek?phone=` **only when `SMS_PROVIDER=console` AND DEBUG=true**, 404 otherwise): register → wizard → submit → API-approve → offer create; i18n keys complete for ru/uz/en; company switcher isolates data between two companies.

## Wave 8 — Hardening, docs, rollout

- **T8.1** Redis rate buckets: company create (5/day/account), document upload (30/day/account), offer create (20/day/company). 429 with retry-after.
- **T8.2** Security pass checklist: `account_number_enc`/codes never in responses/logs (grep + tests); presigned TTL ≤600 s; JWT audience isolation re-tested; OWASP pass over portal endpoints (upload, IDOR, injection, SSRF n/a); `sms_send_log` daily-cost query documented.
- **T8.3** Docs: new `portal/CLAUDE.md` (commands, FSD layout, conventions); update root `CLAUDE.md` (monorepo table + component guide link), `backend/CLAUDE.md` (new contexts, queue, endpoints), `deploy/CLAUDE.md` (5 queues, portal vhost, new envs), DB doc final pass, RU admin guide (очередь верификации: как решать кейсы, что значит waive).
- **T8.4** Rollout: merge to dev → dev stack auto-deploys → run demo script → prod prep: Eskiz creds + `VERIFICATION_ENC_KEY` + `SMS_PROVIDER=eskiz` in prod `../.env`, DNS `cabinet.`, cert. Enforcement flags remain false. Announce badge-only mode.

## Sequencing

```
W1 ─► W2 ─► W4 ─► W5 ─► W6 ─► W8
  └─► W3 ───────┘  └──► W7 ──┘
```
One commit per task id; CI green each commit; migration 0017 is the single serialization point.

## Risks

| Risk | Mitigation |
|---|---|
| nullable `seller_id` ripples | T5.3 audit + golden byte-identical test; CHECK constraint |
| SMS abuse = money | hashed codes, cooldowns, caps, sms_send_log, console driver outside prod |
| OTP peek endpoint leaking to prod | double-gated (console driver AND DEBUG), 404 otherwise, test asserts prod-config 404 |
| new required secret breaks envs | T1.4 same-commit rule; deploy checklist in T8.4 |
| double-approve races | optimistic guard + FOR UPDATE evaluator + tests |
| portal a11y/UX debt rushed | shadcn primitives only, no custom CSS framework; e2e on the critical path |
