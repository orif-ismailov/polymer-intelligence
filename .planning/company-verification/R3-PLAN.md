# R3 — E-IMZO + Contracts (first Deal Lifecycle slice)

> Prereq reading: `00-IMPLEMENTATION-CONTEXT.md`, `ARCHITECTURE.md` §9.6 (E-IMZO flow), §6.2 (person data), §12 (integration gateway), Amendment A2. R1 shipped is a hard prerequisite; R2 is recommended but not required (contracts can reference offers that exist since R1).
> `webapp/` remains frozen.

**Goal — two stages:**
- **Stage A (E-IMZO rails):** company identity confirmation by digital signature — the wizard's "Подтвердить через E-IMZO" button goes live; a signed challenge auto-fills and locks company requisites, auto-passes identity checks, and auto-confirms the signer as owner. Rails = challenge issuing + PKCS#7 verification through the UNICON **e-imzo-server** sidecar.
- **Stage B (Contracts):** a verified company creates a contract from a template with another verified company; both sides sign with E-IMZO; the signed document is stored immutably. This opens the `contracts` bounded context — the seed of the Deal Lifecycle domain.

**Demo script (Definition of Done):** Stage A — new company onboarding: click «Подтвердить через E-IMZO» on desktop → sign challenge via local E-IMZO module → requisites (legal_name, INN, director) fill and lock → case auto-approved (with `verification_auto_approve=on`) without staff touch; audit shows evidence refs. Stage B — company A (seller, has approved offer) → «Создать договор» from the offer → fills terms → sends to company B → B reviews in portal → both sign with E-IMZO → contract `active`; both sides download the signed bundle; staff see the contract in dashboard `/contracts` (read-only oversight); tamper test: modifying stored PDF invalidates hash check.

---

## STAGE A — E-IMZO verification rails

## Wave A1 — e-imzo-server sidecar + gateway adapter

### TA1.1 Sidecar container
Add `eimzo-server` service to `deploy/docker-compose.yml` + `.dev.yml`: UNICON's E-IMZO verification server (Java; obtain distribution per UNICON licensing — **ops prerequisite, flag to the operator if the artifact is not present in the private registry**). Internal-network only (no published ports; API talks to it by service name). Healthcheck. Env: `EIMZO_SERVER_URL` (backend setting, default `http://eimzo-server:8080`), `EIMZO_CHALLENGE_TTL_SECONDS=300`.
Root trust: bundle the production UZ root/intermediate certificates into the sidecar config; document refresh procedure in `deploy/CLAUDE.md`.

### TA1.2 Gateway adapter — `backend/app/integrations/eimzo/`
`client.py`: `verify_pkcs7(pkcs7_b64: str, challenge: str) -> EimzoVerifyResult` — calls sidecar verify endpoint; result: `ok`, `signer` (subject fields parsed: org name, org INN/STIR, person full name, PINFL, position, serial), `cert_valid_from/to`, `revoked: bool | None`, `error`. Timeouts (5 s connect / 15 s read), circuit breaker (open after 5 failures/60 s → callers get `ProviderUnavailable`), call log rows (reuse/introduce `integration_call_log` from ARCHITECTURE §5 — if not yet created, add it in migration 0019). Never raises raw HTTP errors into domain code.

### TA1.3 Migration `0019_eimzo`
- `ALTER TYPE verification_check_type ADD VALUE 'eimzo_signature'` (+ enums.py member; **note:** ADD VALUE cannot run inside a transaction block on old PG — use alembic `op.execute` with autocommit block per project's PG version).
- NEW `signature_evidence` (immutable): id; company_id FK; user_account_id FK (who signed); purpose Text ('company_identity' | 'contract'); challenge Text; pkcs7_storage_path Text (stored in S3 `evidence/eimzo/{company_id}/…` via storage service, not inline in DB); cert_subject JSONB; signed_at; created_at. No UPDATE path — append-only.
- NEW `company_person_data` (ARCHITECTURE §6.2): id; company_id FK; user_account_id FK NULL; full_name_enc BYTEA; pinfl_enc BYTEA; pinfl_last4 CHAR(4); position Text; source Text ('eimzo'); created_at. Encrypted via `crypto.py` (`VERIFICATION_ENC_KEY`).
- `integration_call_log` if absent.
- DB-doc edit same commit.

### TA1.4 Challenge + verify API — `backend/app/api/portal/eimzo.py` + `backend/app/services/eimzo_service.py`
- `POST /portal/companies/{id}/eimzo/challenge` → `{challenge}`: random 32-byte urlsafe token stored in Redis `eimzo:ch:{company_id}:{account_id}` TTL 300 s (single-use).
- `POST /portal/companies/{id}/eimzo/verify` `{pkcs7}`:
  1. pop challenge (missing/expired → `ChallengeExpired`);
  2. adapter verify (sidecar unreachable → `ProviderUnavailable` → 503 typed, frontend offers manual path);
  3. **INN match rule:** cert org INN must equal company.tax_id — mismatch → `CertCompanyMismatch` (422 with both values masked); if company still draft with empty tax_id, adopt cert INN (uniqueness check → `CompanyAlreadyRegistered`);
  4. persist `signature_evidence` (pkcs7 to S3, sha256), `company_person_data` (encrypted PINFL/name, position);
  5. apply to company: fill+lock legal_name (cert org name), director/person data; set flag `identity_locked=true` (new bool column on companies — include in 0019); locked fields reject PATCH;
  6. verification effects: upsert check `eimzo_signature=passed` on the open case (create targeted case if none open); auto-confirm signer's membership as owner; re-run evaluator — with `verification_auto_approve=on` and remaining checks green the case approves without staff;
  7. audit `company.eimzo_verify` + events `COMPANY_EIMZO_CONFIRMED`, standard check-completed event.

### TA1.5 Evaluator & trust-tier integration
`documents_complete` requirements relax when `eimzo_signature=passed` (registration certificate no longer required — the signature supersedes it; bank_letter rule unchanged). Confidence tier recorded in check result payload (`method: eimzo` vs `manual`) — consumed later by trust scoring (P2 scope, just record it now).

**Acceptance Stage A backend:** unit tests with mocked adapter (valid sig; INN mismatch; expired challenge; replayed challenge; revoked cert → failed check with reason; sidecar down → 503 + case still completable manually); PINFL never in logs/responses (masked `****{last4}`); evidence immutability (no update endpoints; storage sha256 check test); migration up/down.

## Wave A2 — Portal frontend for E-IMZO

### TA2.1 Signing feature — `portal/src/features/eimzo-sign/`
Integration with the official **e-imzo.js / CAPIWS** browser API (local WebSocket `wss://127.0.0.1:64443` to the installed E-IMZO module): enumerate certificates → user picks the company key → `createPkcs7(challenge)` → POST to verify endpoint. States: module-not-installed (detect connect failure → instruction screen with download links soliq/e-imzo + retry), no-certificates, signing, success, mismatch/error mapping for every typed backend error.
**Mobile/Mini-browser fallback:** detect no local module → show QR/deep-link screen for the E-IMZO mobile app flow **if** feasibility spike (TA2.0, timeboxed 2 days) confirms it works from an external browser page; otherwise show «подпишите с компьютера» guidance with a copyable magic-link to resume the wizard on desktop (link = signed short-lived token restoring wizard state).

### TA2.2 Wizard integration
Step 1 button goes enabled; success path skips manual identity fields (rendered read-only/locked with «Подтверждено ЭЦП» badge) and jumps to roles step. Verification status screen renders the eimzo check chip with cert holder name + date.

**Acceptance Stage A frontend:** e2e with a stubbed CAPIWS shim (CI has no local E-IMZO): happy path + module-missing path; locked-field UX; i18n ru/uz/en.

---

## STAGE B — Contracts

## Wave B1 — Contracts context: schema + domain

### TB1.1 Migration `0020_contracts`
- Enum `contract_status`: draft, pending_counterparty, pending_signatures, active, declined, cancelled, expired.
- `contract_templates`: id; code UQ (e.g. `SUPPLY_V1`); name_ru/uz/en; body_storage_path (DOCX/HTML template in S3 `contracts/templates/…`); variables_schema JSONB (JSON Schema of required fields); version int; is_active bool. Seeded via `app/seed/` (idempotent) with one initial bilingual supply-contract template (content provided by business/legal — **placeholder lorem template ships for dev; production template is a launch blocker, flag to operator**).
- `contracts`: id; public_id UUID UQ; template_id FK + template_version; initiator_company_id FK; counterparty_company_id FK; offer_id FK NULL (context link); title; variables JSONB (filled values: product, qty, unit, price, currency, incoterms, payment terms, delivery window, special conditions); generated_document_path (rendered PDF in S3); document_sha256; status default draft; created_by_user_account_id FK; sent_at; activated_at; declined_reason; created_at/updated_at. CHECK initiator ≠ counterparty.
- `contract_signatures`: id; contract_id FK; company_id FK; signed_by_user_account_id FK; signature_evidence_id FK (reuses Stage A table, purpose='contract'); signed_at; UNIQUE(contract_id, company_id).
- New bounded-context models file `backend/app/models/contracts.py`; register in `__init__` after verification.
- Events (extend event_types): CONTRACT_CREATED, CONTRACT_SENT, CONTRACT_SIGNED (per side), CONTRACT_ACTIVATED, CONTRACT_DECLINED, CONTRACT_CANCELLED.

### TB1.2 `backend/app/services/contract_service.py`
- `_TRANSITIONS`: draft→{pending_counterparty, cancelled}; pending_counterparty→{pending_signatures (counterparty accepts terms), declined, cancelled (initiator)}; pending_signatures→{active (both signatures present), declined, cancelled, expired (TTL beat)}; terminal: active, declined, cancelled, expired.
- `create_contract(db, initiator_company, account, template, variables, counterparty_company, offer=None)`: both companies must be `verified` (`CompanyNotVerified`); validate variables against template JSON Schema; render document (TB1.3); status draft.
- `send(db, contract, account)` → pending_counterparty + notification to counterparty members (portal_notifications from R2; if R2 not shipped, direct minimal notification insert — the table exists only in R2, so guard: R3-without-R2 falls back to no in-portal notify + prominent «Входящие договоры» page badge computed from query).
- `accept_terms / decline(reason)` by counterparty (any manager/owner member).
- `sign(db, contract, company, account, pkcs7)`: allowed in pending_signatures (and pending_counterparty for the initiator pre-signing? **No — keep strict: signatures only in pending_signatures**, initiator signs after counterparty accepts; simpler audit story); challenge = `contract:{public_id}:{document_sha256}` issued per signer via eimzo challenge flow (purpose='contract'); adapter verify; **cert org INN must match the signing company tax_id**; store signature_evidence + contract_signatures; when both present → active (FOR UPDATE on contract row to avoid double-activation race), emit CONTRACT_ACTIVATED.
- `cancel` by initiator until any signature exists. Edits to variables allowed only in draft; any edit after render regenerates document + sha256.
- Every action → audit + event.

### TB1.3 Document rendering
`backend/app/services/contract_render.py`: template (HTML) + variables + both companies' requisites (legal name, INN, address, director, bank account **masked except in the final document** — full requisites ARE required in a real contract: decrypt bank account for rendering, document access is member/staff-gated) → PDF via `weasyprint` (add pinned dep; system deps in backend Docker image — update Dockerfile) → S3 `contracts/{contract_public_id}/contract_v{n}.pdf` + sha256. Rendered per language (ru primary; uz optional per template availability).

**Acceptance B1:** transition-table tests; both-verified enforcement; variables schema validation errors typed; render golden test (stable input → stable sha256 with frozen timestamps); double-sign race test (two concurrent final signatures → one activation); INN-mismatch signing rejection.

## Wave B2 — APIs

### TB2.1 Portal — `backend/app/api/portal/contracts.py`
- `GET /portal/contract-templates` (active, with variables_schema for form generation)
- `POST /portal/contracts` (initiator side; optional offer_id pre-fills product/price variables)
- `GET /portal/contracts?company_id=&role=initiator|counterparty&status=`
- `GET /portal/contracts/{id}` (both sides; includes signatures state, document download presigned link)
- `POST …/send`, `POST …/accept`, `POST …/decline {reason}`, `POST …/cancel`
- `POST …/sign/challenge` → `{challenge}`; `POST …/sign` `{pkcs7}`
- `GET …/document` → presigned PDF; `GET …/bundle` → zip: PDF + both PKCS#7 + verification info sheet (JSON: sha256, signers, timestamps).
- Counterparty picker: `GET /portal/companies/directory?q=` — verified companies only, public fields (name, INN, roles, verified badge). Rate-limited (20/min), no enumeration of unverified/draft companies.

### TB2.2 Admin — `backend/app/api/admin_contracts.py`
`GET /admin/contracts?status=&q=` + detail (read-only oversight: parties, status timeline from audit, document access `require_analyst_or_admin`). No staff mutation of contracts in R3 (dispute tooling is future Deal work).

**Acceptance B2:** authz matrix (initiator vs counterparty vs third company (404) vs staff); directory hides non-verified; bundle содержит валидные подписи; presigned TTL ≤ 600 s.

## Wave B3 — Frontend + staff surface

### TB3.1 Portal
`pages/contracts` (tabs: все / входящие требуют действия / активные; status chips), `pages/contracts/new` (template select → dynamic form from variables_schema → counterparty picker (directory search) → preview rendered PDF inline → send), `pages/contracts/[id]` (document viewer, timeline, action bar by role/status, sign flow reusing `features/eimzo-sign` with contract challenge). «Создать договор» CTA on own approved offers and (if R2 shipped) on incoming inquiries. Notifications integration (R2 bell) for sent/accepted/signed/declined.

### TB3.2 Dashboard
`(dashboard)/contracts/` — read-only list + detail (oversight), origin/status filters, locale files. Nav entry.

### TB3.3 Telegram (staff)
Optional info card to staff group on CONTRACT_ACTIVATED (no buttons — read-only awareness). Template ru/uz/tr.

**Acceptance B3:** e2e full Stage-B demo with stubbed CAPIWS; PDF preview renders; both-sides sign flow; declined/cancelled paths; i18n ru/uz/en.

## Wave B4 — Hardening, legal, rollout

- **TB4.1** Evidence integrity: nightly beat `verify_contract_integrity` — recompute sha256 of stored PDFs vs `document_sha256`, alert admin channel on mismatch. Signature bundle export documented for legal use.
- **TB4.2** Expiry: `pending_signatures`/`pending_counterparty` older than 30 d (setting `contract_pending_ttl_days`) → expired + notifications.
- **TB4.3** Security: PINFL/bank decrypt only inside render path; contract docs bucket prefix access-gated; challenge single-use + bound to document hash (re-render invalidates issued challenges — test); OWASP pass.
- **TB4.4** Legal sign-off checklist (operator action, launch blocker): production contract template text; ToS clause on electronic contracting; confirmation that E-IMZO PKCS#7 + stored evidence meets Uzbek e-document requirements (Law «Об электронном документообороте» / «Об электронной цифровой подписи»); data-localization confirmation for PINFL storage.
- **TB4.5** Docs + rollout: CLAUDE.md deltas (new sidecar, contracts context), RU admin guide (контракты: оверсайт), DB doc; dev demo → prod (sidecar image, root certs, template upload, DNS unchanged).

## Sequencing

```
Stage A: A1 ─► A2
Stage B: B1 ─► B2 ─► B3 ─► B4     (B1 may start in parallel with A2; B-sign work depends on A1)
```

## Risks

| Risk | Mitigation |
|---|---|
| e-imzo-server distribution/licensing unavailable | Ops prerequisite flagged at TA1.1 kickoff — hard blocker, escalate before any Stage-A code beyond the adapter interface |
| National crypto quirks (O'zDSt) breaking naive verification | ALL verification delegated to the UNICON sidecar; никогда не парсим/не проверяем PKCS#7 сами |
| Mobile signing UX dead-ends in webviews | TA2.0 spike timeboxed; desktop-first with magic-link resume as the guaranteed path |
| Legal insufficiency of stored evidence | TB4.4 checklist is a launch blocker, not a nice-to-have |
| PDF rendering nondeterminism (hash drift) | frozen fonts in image, timestamps injected as variables, golden hash test |
| R3 without R2 (notifications missing) | guarded fallbacks specified in TB1.2; recommend shipping R2 first |
| Contract scope creep toward full deal management | Hard boundary: no payments, no delivery tracking, no disputes in R3 — those are separate Deal Lifecycle phases per ARCHITECTURE §12 |
