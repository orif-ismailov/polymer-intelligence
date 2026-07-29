# IMEX Company Verification — Architecture

**Status:** Proposal v1 (2026-07-23)
**Scope:** Company Verification module for the IMEX marketplace (this repo), designed as the identity/compliance foundation for the future Deal Lifecycle module.
**Method:** DDD bounded contexts + Clean Architecture layering inside the existing modular monolith, event-driven via a transactional outbox, microservice-*ready* (not microservice-*now*).

---

## 0. Position statement — challenged assumptions

Before the deliverables, three deliberate deviations from the brief, with rationale:

### 0.1 Modular monolith, not microservices (now)

The brief asks for "microservice decomposition". The correct decomposition is designed below — but **deploying it as microservices today would be a mistake** for this codebase:

- The platform is a FastAPI + Celery + Postgres + Redis modular monolith with a small team, modest traffic, and one database. Splitting it now buys network partitions, distributed transactions, and per-service ops cost, and buys nothing else.
- The existing invariant — *"no single source can take the others down"* — is already achieved in-process via adapter isolation, queue separation, and graceful degradation. Verification follows the same pattern.
- **What we do instead:** each bounded context is a Python package with hard import rules (context A never imports context B's models — only its service facade or events), its own tables (prefixed), and all cross-context communication via domain events through a transactional **outbox** table. That makes each context extractable to a service later by (1) moving the package, (2) pointing the outbox at a real broker (Kafka/NATS), (3) replacing facade calls with HTTP/gRPC. No rewrite.

### 0.2 "Can this company legally sell chemical X?" is compliance *guidance*, not a legal verdict

The platform must not silently assume liability for legal determinations. The compliance engine below produces an **eligibility decision with reasons and rule versions**, enforced as a *platform policy* ("IMEX requires license L for category C"), and every decision is journaled. The rule content (which license types map to which chemical categories under Uzbek law) is **data maintained by compliance staff**, not code — because it will be wrong at launch and will change. This needs legal sign-off (see Open Questions).

### 0.3 Bank account *ownership* verification has no clean API path in Uzbekistan today

There is no open-banking standard in UZ; penny-drop is not an established rail. The design therefore treats bank verification as a **pluggable strategy** (document-based → e-invoice cross-check → direct bank API when partnerships exist) rather than promising API verification that doesn't exist. MVP: structural validation (MFO directory + account format) + bank reference letter upload + manual review. The interface stays stable as stronger methods arrive.

### 0.4 As-is architecture review (what the module builds on)

Current shape: modular monolith — FastAPI API + Celery worker (`ingest`/`parse`/`notify`/`default` queues) + beat + Telethon userbot behind a host-nginx TLS front door, over Postgres/Redis/MinIO; clients are the Next.js dashboard, the Telegram Mini App, and the aiogram bot/channel.

**Strengths reused directly:** immutable ingest (`raw_items` dedup) → `registry_snapshots`; HITL moderation state machine with dashboard + Telegram dual actioning → verification case review; `SourceAdapter` registry → `VerificationProvider` gateway; append-only `audit_log`; `_SPECS` runtime settings; `storage_service` upload validation.

**Gaps the module closes:**
1. **No company identity** — business identity is split across `sellers`/`clients`/`counterparties`; only trust signal is the manual `sellers.is_verified` boolean. → first-class `Company` aggregate + bridging FKs.
2. **No event backbone** — cross-feature effects are direct calls + fire-and-forget notify tasks. → transactional `domain_events` outbox (the one new infrastructure piece).
3. **No outbound verification integrations** — the adapter registry only ingests market data. → integration gateway (new `verify` Celery queue so slow gov APIs never starve ingest/notify).
4. **No PII-grade storage** — no encryption-at-app-layer anywhere. → encrypted bank account fields + private `verification/` document area.

---

## Amendment A1 (2026-07-23) — Accounts, phone-OTP auth, and the client portal

Supersedes the identity assumptions in the sections below wherever they conflict.

**Identity model v2:**
- New **Account** entity (`user_accounts`): a person, keyed by phone number (E.164, unique). Registration/login = passwordless SMS OTP (provider: **Eskiz.uz**, behind an `SmsProvider` port in the Integration Gateway; `console` driver for dev/CI). No password store exists. Long-lived refresh cookie + short access JWT (`aud=portal`, same HS256 machinery as staff auth, separate dependency `get_current_account`).
- **One account → many companies** via `company_members.user_account_id` (replaces `telegram_user_id` as the membership key everywhere in §5). Each company is verified independently (E-IMZO path §9.6 or manual + checks). Active-company selector in the portal; all company-scoped actions carry the selected `company_id`, authorized через membership.
- `user_accounts.telegram_user_id` (nullable, unique) is the **future** bridge to the Mini App world — not built now.

**Surface model v3 — three frontends, existing ones untouched:**
| Surface | Audience | Scope | Status |
|---|---|---|---|
| **`portal/` (new)** — Vite + React + TS + Tailwind + shadcn/ui + TanStack Query + react-router-dom + zustand, **Feature-Sliced Design** | Companies (clients) | Phone-OTP auth, multi-company cabinet, verification wizard, documents, statuses, **offer publishing on behalf of a verified company** | build new |
| `dashboard/` | Staff | + verification queue, companies, rules (unchanged plan) | extend |
| `webapp/` Mini App | Current TG buyers/sellers | Marketplace as-is | **frozen — do not touch** |

Portal is served same-origin on its own host (recommended `cabinet.ai-imex.com`) with nginx proxying `/api/*` — no CORS. Backend stays the monolith; portal endpoints live under `/api/v1/portal/*`.

**Marketplace consequence:** `seller_offers` gains `company_id` + `created_by_user_account_id` (nullable) and `seller_id` becomes nullable — an offer originates either from a TG seller (mini app, as today) or from a company via the portal. Moderation, notify templates, and public cards must handle both origins; portal-created offers require a verified company by construction (independent of the `verification_required_for_publish` flag, which governs only the legacy TG path).

**OTP security baseline:** codes stored as hashes in Redis with 5-min TTL; 60-s resend cooldown; ≤5 sends/phone/day + per-IP limits; ≤5 verify attempts per code; uniform responses (no phone enumeration); SMS sends logged (`sms_send_log`) for cost + abuse tracking; Eskiz creds are secrets required only when `SMS_PROVIDER=eskiz`.

## Amendment A2 (2026-07-23) — Portal is the primary client product; release roadmap

The portal is not a "verification module UI" — it is the platform's primary client product, absorbing all Mini App functionality over time plus contracts. Decisions:

- **Iterative releases:**
  - **R1** (= P1-PLAN v2): phone-OTP auth, multi-company cabinet, verification, document vault, **offer publishing** by verified companies.
  - **R2** (Mini App parity): market browsing, buyer purchase requests, per-offer inquiries, news reader, in-portal notifications. Buyer flows become company-scoped (B2B) — exact rules defined at R2 planning. Requires portal-auth twins of the relevant `/webapp/*` read/write endpoints (`/portal/market`, `/portal/requests`, …) reusing the same services.
  - **R3** (first Deal Lifecycle slice): **contract constructor** between two verified companies — template + requisites of both parties → E-IMZO signing by both sides (rails from P2 §9.6) → signed PKCS#7 stored in the Document Vault as immutable evidence. New `contracts` bounded context opens the Deal Lifecycle domain; escrow/e-invoice/customs attach to it later per §12.
- **Mini App: frozen indefinitely.** No changes, no deprecation work, no account-bridge work scheduled. It keeps serving its current Telegram audience as-is; the `user_accounts.telegram_user_id` column remains a dormant hook.

---

## 1. Domain analysis

### Core problem

A company must prove, once, that it (a) legally exists, (b) is who it claims, (c) is in good standing, (d) may legally trade the product categories it wants to trade, and (e) is controlled by the Telegram user(s) operating it on the platform. The result must be **durable** (survives onboarding), **fresh** (re-verified on triggers), **auditable** (every fact traceable to evidence), and **consumable** by other contexts (marketplace publish gate today, deal lifecycle tomorrow).

### Ubiquitous language

| Term | Meaning |
|---|---|
| **Company** | A legal entity (keyed by STIR/INN + jurisdiction) registered on the platform. Distinct from users. |
| **Member** | A Telegram user attached to a company with a role (owner/manager/member). |
| **Verification Case** | One run of the verification workflow (onboarding, re-verification, targeted). |
| **Check** | One atomic verification item inside a case (gov registry, tax, VAT, bank, license, manual KYB). |
| **Evidence Snapshot** | Immutable stored payload from an external registry at a point in time. |
| **License** | A company-held permit/certificate of a catalogued type, with validity window. |
| **Requirement Rule** | "Product category C (+ optional hazard class/role) requires license type L in jurisdiction J, effective D1–D2." |
| **Eligibility** | Materialized decision: may company X trade category C on IMEX, and why. |
| **Trust Profile** | Computed score + badges derived from a trust event ledger. |

### Key domain invariants

1. A company is uniquely identified by `(jurisdiction, tax_id)` — one platform record per legal entity.
2. `raw evidence is immutable` — registry responses are stored append-only (same philosophy as `raw_items`).
3. A verification decision always references the evidence and rule versions it was based on.
4. Verification state is owned by the Verification context; Marketplace only *reads* it (via facade/events), never writes it.
5. Trust score is derived, never hand-edited; manual adjustments are events in the ledger, not field updates.

---

## 2. Bounded contexts

```
┌────────────────────────────────────────────────────────────────────────────┐
│                            EXISTING PLATFORM                               │
│  Signals/Intelligence   Marketplace (offers/requests)   News Engine        │
└───────────────▲───────────────────▲───────────────────────▲────────────────┘
                │ counterparty_id   │ publish-gate reads     │
                │ bridge            │ + events               │
┌───────────────┴───────────────────┴────────────────────────┴────────────────┐
│                        NEW: COMPANY & COMPLIANCE CORE                        │
│                                                                              │
│  ┌──────────────────┐   ┌──────────────────┐   ┌───────────────────────┐    │
│  │ Company Registry │   │   Verification   │   │ Compliance & Licensing│    │
│  │ (companies,      │◄──│ (cases, checks,  │──►│ (licenses, rules,     │    │
│  │  members, roles) │   │  state machine)  │   │  eligibility engine)  │    │
│  └────────┬─────────┘   └────────┬─────────┘   └───────────┬───────────┘    │
│           │                      │                         │                │
│           ▼                      ▼                         ▼                │
│  ┌──────────────────┐   ┌──────────────────┐   ┌───────────────────────┐    │
│  │ Trust &          │   │ Integration      │   │ Document Vault        │    │
│  │ Reputation       │   │ Gateway (ACL)    │   │ (S3/MinIO, reuses     │    │
│  │ (ledger + score) │   │ gov/bank adapters│   │  storage_service)     │    │
│  └──────────────────┘   └──────────────────┘   └───────────────────────┘    │
│                                                                              │
│            all cross-context communication: domain_events outbox            │
└──────────────────────────────────────────────────────────────────────────────┘
                │ stable contracts: company_id, eligibility API, trust API,
                ▼ event catalog, integration gateway
┌──────────────────────────────────────────────────────────────────────────────┐
│  FUTURE: Deal Lifecycle (escrow, e-invoice, e-contract, customs, T&T, …)     │
└──────────────────────────────────────────────────────────────────────────────┘
```

Six new contexts, each a package under `backend/app/`:

| Context | Package | Owns | Never touches |
|---|---|---|---|
| **Company Registry** | `app/models/companies.py`, `app/services/company_service.py` | companies, members, business roles, lifecycle status | verification internals |
| **Verification** | `app/models/verification.py`, `app/services/verification_service.py` | cases, checks, decisions, re-verification schedule | marketplace tables |
| **Compliance & Licensing** | `app/models/licensing.py`, `app/services/compliance_service.py`, `license_service.py` | license catalog, company licenses, requirement rules, eligibility | trust internals |
| **Trust & Reputation** | `app/models/trust.py`, `app/services/trust_service.py` | trust event ledger, profiles, badges, scoring config | writes to any other context |
| **Integration Gateway** | `app/integrations/` (new top-level pkg) | provider adapters, snapshots, circuit breakers, call log | domain tables (returns DTOs only) |
| **Document Vault** | extends `app/services/storage_service.py` | verification document storage/validation | — |

**Anti-corruption layer:** the Integration Gateway is the only code that knows provider payload shapes. It returns normalized DTOs (`GovRegistryRecord`, `TaxStatusRecord`, `LicenseRegistryRecord`, `BankAccountProbe`) and persists raw payloads as immutable snapshots. Domain code never parses soliq.uz JSON.

### Relationship to existing identity (bridging, not big-bang)

Today identity is split: `clients` (buyers), `sellers` (sellers), `counterparties` (intelligence). We do **not** merge them. Instead:

- `companies.counterparty_id` (nullable FK) bridges to the intelligence loop — a verified company enriches the counterparty graph (verified `tax_id`, canonical name).
- `sellers.company_id` and `clients.company_id` (nullable FKs, new migration) let existing rows attach to a company once its owner verifies it. Matching hint: same `telegram_user_id` as a company owner/member.
- Marketplace keeps working for unattached sellers during rollout; the publish gate tightens via a runtime setting (see §11).

---

## 3. Microservice decomposition (future extraction map)

If/when extraction is justified (traffic, team size, org boundaries), the seams are:

1. **`company-service`** — Company Registry + Verification + Document Vault (they share the KYB transaction boundary; splitting them buys nothing).
2. **`compliance-service`** — Licensing + rules + eligibility. Extract when rule volume/jurisdictions grow or a regulator integration demands isolation.
3. **`trust-service`** — pure event consumer, easiest extraction, zero synchronous dependencies.
4. **`integration-gateway`** — extract *first* if gov/bank API load or credential isolation demands it; it is already stateless-ish (snapshots can move with it).

Extraction preconditions built in from day one: no cross-context FK *constraints* across seam lines except IDs (company_id is copied, not joined-through, in trust/compliance read models where practical), outbox-based events, facade-only synchronous calls.

---

## 4. Domain model & core aggregates

### Aggregate: `Company` (Company Registry)
- **Root:** Company (id, jurisdiction, tax_id, legal_name, status…)
- **Entities:** CompanyMember, CompanyBusinessRole, CompanyBankAccount
- **Invariants:** unique (jurisdiction, tax_id); exactly ≥1 active owner member; status transitions only via defined machine; bank account mutations only while company not suspended.

### Aggregate: `VerificationCase` (Verification)
- **Root:** VerificationCase (company_id, case_type, status…)
- **Entities:** VerificationCheck (one per check type per case)
- **Invariants:** at most one open case per company; case can be decided only when all non-waived checks are terminal; every decision records actor + evidence refs; checks reference immutable snapshots, never live payloads.

### Aggregate: `CompanyLicense` (Compliance)
- **Root:** CompanyLicense (type, number, validity, status, evidence)
- **Invariants:** status transitions via machine; `active` requires accepted evidence (document or registry snapshot); expiry is computed, never manually set to bypass.

### Aggregate: `RequirementRuleSet` (Compliance)
- **Root:** versioned set of LicenseRequirement rules (effective-dated). Rules are append-only per version; eligibility decisions pin the version they used.

### Aggregate: `TrustProfile` (Trust)
- **Root:** TrustProfile (company_id, score, grade, components, scoring_version)
- **Ledger:** TrustEvent append-only. Profile is a projection; recomputable from ledger at any scoring version.

### Value objects
`TaxId` (jurisdiction-aware format validation: UZ STIR = 9 digits), `Mfo` (5-digit UZ bank code, validated against CBU directory), `AccountNumber` (masked in all read models), `LicenseNumber`, `HazardClass`, `Money` (future deal reuse).

---

## 5. Database schema (migration 0017+)

Conventions follow the codebase: SQLAlchemy 2, `(str, Enum)` domain enums → native PG ENUMs (each new enum = migration + DB-doc edit), BIGINT PKs, plus **`public_id UUID`** on `companies` for stable external references (deal module, gov reporting) without leaking sequence counts.

```sql
-- ── Company Registry ────────────────────────────────────────────
companies (
  id BIGSERIAL PK,
  public_id UUID UNIQUE DEFAULT gen_random_uuid(),
  jurisdiction CHAR(2) NOT NULL DEFAULT 'UZ',
  tax_id TEXT NOT NULL,                       -- STIR/INN
  legal_name TEXT NOT NULL,                   -- from registry once verified
  short_name TEXT,
  legal_form TEXT,                            -- OOO/AJ/ChP…
  legal_address TEXT,
  director_name TEXT,
  registration_date DATE,
  registry_status company_registry_status,    -- active|suspended|liquidated|unknown (as reported by gov)
  status company_status NOT NULL DEFAULT 'draft',
    -- draft|pending_verification|verified|rejected|suspended|liquidated
  verified_at TIMESTAMPTZ,
  reverification_due_at TIMESTAMPTZ,
  counterparty_id BIGINT NULL REFERENCES counterparties(id),
  created_by_telegram_user_id BIGINT NOT NULL,
  created_at / updated_at TIMESTAMPTZ,
  UNIQUE (jurisdiction, tax_id)
)

company_members (
  id BIGSERIAL PK, company_id FK,
  telegram_user_id BIGINT NOT NULL,
  member_role company_member_role NOT NULL,   -- owner|manager|member
  status company_member_status NOT NULL,      -- active|invited|removed
  invited_by_telegram_user_id BIGINT,
  created_at, UNIQUE (company_id, telegram_user_id)
)

company_business_roles (
  id BIGSERIAL PK, company_id FK,
  role company_business_role NOT NULL,
    -- manufacturer|importer|trader|logistics_provider|distributor|laboratory|insurance_provider
  status business_role_status NOT NULL DEFAULT 'declared',  -- declared|confirmed|revoked
  confirmed_by BIGINT NULL REFERENCES staff_users(id),
  created_at, UNIQUE (company_id, role)
)

company_bank_accounts (
  id BIGSERIAL PK, company_id FK,
  bank_mfo CHAR(5) NOT NULL, bank_name TEXT,
  account_number_enc BYTEA NOT NULL,          -- app-layer encrypted (see §15)
  account_last4 CHAR(4) NOT NULL,             -- for display/masking
  currency CHAR(3) DEFAULT 'UZS',
  status bank_account_status NOT NULL,        -- unverified|pending|verified|failed|archived
  verification_method bank_verification_method, -- document|e_invoice_crosscheck|bank_api|manual
  evidence_document_id BIGINT NULL,
  verified_at, verified_by, created_at
)

-- ── Verification ────────────────────────────────────────────────
verification_cases (
  id BIGSERIAL PK, company_id FK,
  case_type verification_case_type NOT NULL,  -- onboarding|reverification|targeted
  status verification_case_status NOT NULL,
    -- draft|submitted|checks_running|needs_info|pending_review|approved|rejected|cancelled
  submitted_at, decided_at,
  decided_by BIGINT NULL REFERENCES staff_users(id),  -- NULL = auto-decision or telegram actor (audit_log has detail)
  decision_note TEXT,
  created_at
)
-- partial unique index: one open case per company
CREATE UNIQUE INDEX ux_open_case ON verification_cases(company_id)
  WHERE status NOT IN ('approved','rejected','cancelled');

verification_checks (
  id BIGSERIAL PK, case_id FK,
  check_type verification_check_type NOT NULL,
    -- gov_registry|tax_status|vat_status|bank_account|licenses|sanctions_restrictions|manual_kyb
  status verification_check_status NOT NULL DEFAULT 'pending',
    -- pending|running|passed|warning|failed|unavailable|waived
  result JSONB,                               -- normalized DTO of findings
  snapshot_id BIGINT NULL REFERENCES registry_snapshots(id),
  attempts INT DEFAULT 0, last_error TEXT,
  started_at, finished_at,
  waived_by BIGINT NULL REFERENCES staff_users(id), waive_reason TEXT,
  UNIQUE (case_id, check_type)
)

verification_documents (
  id BIGSERIAL PK, company_id FK, case_id BIGINT NULL FK,
  kind verification_document_kind NOT NULL,
    -- registration_certificate|director_id|bank_letter|license|permit|certificate|power_of_attorney|other
  storage_path TEXT NOT NULL,                 -- verification/{company_id}/{token}-{name}
  mime_type TEXT, size_bytes INT, sha256 TEXT NOT NULL,
  uploaded_by_telegram_user_id BIGINT NOT NULL,
  status document_review_status NOT NULL DEFAULT 'pending_review', -- pending_review|accepted|rejected
  review_note TEXT, reviewed_by BIGINT NULL, reviewed_at,
  expires_at TIMESTAMPTZ NULL,
  created_at
)

-- ── Integration Gateway (immutable evidence, mirrors raw_items) ─
registry_snapshots (
  id BIGSERIAL PK,
  provider TEXT NOT NULL,                     -- 'soliq'|'gov_registry'|'license_gov'|'cbu_mfo'|'bank_<x>'
  query_key TEXT NOT NULL,                    -- e.g. tax_id or license number
  content_hash TEXT NOT NULL,                 -- sha256(provider+query_key+normalized payload)
  payload JSONB NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL,
  latency_ms INT, http_status INT,
  UNIQUE (provider, query_key, content_hash)  -- ON CONFLICT DO NOTHING; rows never mutated
)

integration_call_log (
  id BIGSERIAL PK, provider TEXT, operation TEXT, query_key TEXT,
  outcome TEXT,                               -- ok|error|timeout|circuit_open
  http_status INT, latency_ms INT, error TEXT, created_at
)  -- ops/billing observability; prunable

-- ── Compliance & Licensing ──────────────────────────────────────
license_types (
  id BIGSERIAL PK, code TEXT UNIQUE,          -- e.g. 'PRECURSOR_HANDLING'
  name_ru TEXT, name_uz TEXT, name_en TEXT,
  issuing_authority TEXT, description TEXT,
  requires_expiry BOOL DEFAULT true, is_active BOOL DEFAULT true
)

company_licenses (
  id BIGSERIAL PK, company_id FK, license_type_id FK,
  license_number TEXT, issued_by TEXT,
  issued_at DATE, expires_at DATE NULL,
  status license_status NOT NULL,             -- pending_review|active|expired|revoked|rejected
  source license_source NOT NULL,             -- uploaded|registry
  document_id BIGINT NULL REFERENCES verification_documents(id),
  snapshot_id BIGINT NULL REFERENCES registry_snapshots(id),
  verified_at, verified_by, created_at
)

license_requirements (                        -- rules-as-data, effective-dated
  id BIGSERIAL PK,
  product_id BIGINT NULL REFERENCES products(id),   -- NULL = category-level via product_group
  product_group TEXT NULL,                    -- coarse grouping until a category table exists
  hazard_class TEXT NULL,
  applies_to_role company_business_role NULL, -- NULL = any role
  license_type_id BIGINT NOT NULL REFERENCES license_types(id),
  requirement_level requirement_level NOT NULL, -- required|conditional|advisory
  jurisdiction CHAR(2) DEFAULT 'UZ',
  effective_from DATE NOT NULL, effective_to DATE NULL,
  rule_version INT NOT NULL, notes TEXT,
  created_by BIGINT REFERENCES staff_users(id), created_at
)

company_eligibility (                         -- materialized decisions
  id BIGSERIAL PK, company_id FK,
  product_id BIGINT NULL, product_group TEXT NULL,
  eligible BOOL NOT NULL,
  reasons JSONB NOT NULL,                     -- [{rule_id, rule_version, verdict, detail}]
  rule_version INT NOT NULL, computed_at TIMESTAMPTZ,
  UNIQUE (company_id, product_id, product_group)
)

-- ── Trust & Reputation ──────────────────────────────────────────
trust_events (
  id BIGSERIAL PK, company_id FK,
  event_type TEXT NOT NULL,                   -- 'company.verified','license.expired','deal.completed',…
  payload JSONB, occurred_at TIMESTAMPTZ NOT NULL,
  source TEXT NOT NULL                        -- 'verification'|'compliance'|'marketplace'|'deal'|'admin'
)  -- append-only

trust_profiles (
  company_id BIGINT PK REFERENCES companies(id),
  score NUMERIC(5,2) NOT NULL DEFAULT 0,
  grade trust_grade NOT NULL DEFAULT 'unrated', -- unrated|basic|verified|trusted|elite
  components JSONB NOT NULL,                  -- per-dimension subscores
  badges JSONB NOT NULL DEFAULT '[]',
  scoring_version INT NOT NULL, computed_at TIMESTAMPTZ
)

-- ── Event backbone ──────────────────────────────────────────────
domain_events (                               -- transactional outbox
  id BIGSERIAL PK,
  event_type TEXT NOT NULL,                   -- see §7 catalog
  aggregate_type TEXT, aggregate_id TEXT,
  payload JSONB NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at TIMESTAMPTZ NULL, attempts INT DEFAULT 0
)
CREATE INDEX ix_outbox_unpublished ON domain_events(id) WHERE published_at IS NULL;

-- Bridging migrations on existing tables:
ALTER TABLE sellers ADD COLUMN company_id BIGINT NULL REFERENCES companies(id);
ALTER TABLE clients ADD COLUMN company_id BIGINT NULL REFERENCES companies(id);
ALTER TABLE seller_offers ADD COLUMN company_id BIGINT NULL REFERENCES companies(id);
```

Audit continues to use the existing `audit_log` (staff.py) via `audit_service.write_audit` — every admin decision, waiver, rule edit, suspension, and manual trust adjustment writes a row in the same transaction.

### ER summary

```
companies 1─* company_members
companies 1─* company_business_roles
companies 1─* company_bank_accounts ─? verification_documents
companies 1─* verification_cases 1─* verification_checks ─? registry_snapshots
companies 1─* verification_documents
companies 1─* company_licenses ─? (verification_documents | registry_snapshots)
license_types 1─* company_licenses ; license_types 1─* license_requirements
products ?─* license_requirements ; companies 1─* company_eligibility
companies 1─1 trust_profiles ; companies 1─* trust_events
companies ?─1 counterparties (bridge)
sellers/clients/seller_offers ?─1 companies (bridge)
```

---

## 6. State machines

### Company lifecycle
```
draft ──submit──► pending_verification ──approve──► verified
  ▲                    │        ▲                     │
  └──── edit ◄─────────┘        │                     ├─ gov reports liquidation ──► liquidated (terminal)
                    reject ─► rejected ──resubmit─────┤
                                                      ├─ admin/regulatory ──► suspended ──reinstate──► verified
                                                      └─ reverification_due_at passes ─► (stays verified,
                                                            reverification case opens; downgrade only on failure)
```
Rule: **verification is not lost while a re-verification runs.** Only an explicit failed re-check or admin action downgrades — otherwise gov API flakiness would randomly de-verify companies.

### VerificationCase
```
draft ─► submitted ─► checks_running ─► pending_review ─► approved | rejected
                        │    ▲                                 
                        ▼    │ user provides info               
                      needs_info                                
auto path: checks_running ─(all auto checks passed AND verification_auto_approve=on)─► approved
any non-terminal ─► cancelled (company deleted/withdrawn)
```

### VerificationCheck
```
pending ─► running ─► passed | warning | failed | unavailable
unavailable ─► pending (scheduled retry, max N attempts, exponential backoff)
any ─► waived (admin only, reason required, audited)
```
`warning` = check completed with non-blocking findings (e.g., tax debt present but `tax_debt_blocking=off`): case can still be approved; the finding flows into trust + UI warnings.

### CompanyLicense
```
pending_review ─► active ─► expired (computed nightly) 
pending_review ─► rejected
active ─► revoked (registry says revoked, or admin)
expired/revoked ─► (new license row, never resurrection)
```

---

### 6.1 Concurrency & locking

- **Human decisions → optimistic**: approve/reject runs `UPDATE … WHERE status = 'pending_review'`; rowcount 0 = already decided elsewhere (dashboard vs Telegram race) → idempotent no-op, same pattern as offer moderation.
- **Case evaluator → pessimistic**: concurrent `verification.check.completed` consumers `SELECT … FOR UPDATE` the case row, re-read all check statuses under the lock, and transition at most once — prevents double `case.approved` when checks finish simultaneously on the `verify` queue.
- **Invariants live in the DB, not app code**: one-open-case = partial unique index; snapshot dedup = `ON CONFLICT DO NOTHING`; member uniqueness = composite unique. App-level `if` checks don't survive races; constraints do.
- **Event consumers are idempotent** (processed event-id dedup) and run with `task_acks_late` — a crashed worker re-delivers, never double-applies.

### 6.2 Person-level KYC data (P2, sensitive)

When director-level checks arrive (e-imzo, gov person lookup), PINFL / full name / birth date go in a dedicated `company_person_data` table: app-layer encrypted (same `VERIFICATION_ENC_KEY` scheme as bank accounts), masked in all read models, minimized to check requirements, never exposed via public APIs. Credentials stay separate from profile data platform-wide (marketplace users have no password at all — Telegram is the IdP; `staff_users` keeps only a hash).

## 7. Event-driven architecture & event catalog

**Transport (now):** transactional outbox → `dispatch_domain_events` beat task (every 10–15 s) marks rows published and fans out to Celery consumer tasks (new `verify` queue for checks; existing `notify` queue for messaging; `default` for projections). Producers write the event row **in the same DB transaction** as the state change — no dual-write problem. Consumers are idempotent (event id dedup).
**Transport (later):** same outbox drained to Kafka/NATS by a relay; consumers move behind topics. Zero producer changes.

| Event | Producer | Consumers (now) |
|---|---|---|
| `company.registered` | Company Registry | Notify (staff), Trust (init profile) |
| `company.profile.updated` | Company Registry | Verification (flag targeted re-check if identity fields changed) |
| `verification.case.submitted` | Verification | Check runner (fan out checks), Notify staff queue |
| `verification.check.completed` | Verification | Case evaluator (advance state machine), Trust |
| `verification.case.needs_info` | Verification | Notify (user DM via bot) |
| `verification.case.approved` / `.rejected` | Verification | Company Registry (status), Notify, Trust, Compliance (recompute eligibility) |
| `company.verified` | Company Registry | Marketplace (unlock publish), Counterparty bridge enrichment, Trust |
| `company.suspended` / `.reinstated` / `.liquidation_detected` | Company Registry | Marketplace (unpublish offers), Notify, Trust |
| `bank_account.verified` / `.failed` | Verification | Notify, Trust |
| `license.submitted` / `.verified` / `.rejected` | Compliance | Notify, Trust, Eligibility recompute |
| `license.expiring` (T-30/T-7) / `.expired` / `.revoked` | Compliance (beat scan) | Notify (user + staff), Eligibility recompute, Trust |
| `company.eligibility.changed` | Compliance | Marketplace (unpublish now-ineligible offers), Notify |
| `requirement_rules.published` (new rule version) | Compliance admin | Eligibility bulk recompute |
| `trust.score.updated` / `trust.badge.changed` | Trust | Notify (badge upgrades only), read-model cache |
| `reverification.due` | beat scan | Verification (open reverification case) |
| *(future)* `deal.completed`, `deal.disputed`, `deal.feedback.received` | Deal Lifecycle | Trust — **contract defined now**, producer later |

---

## 8. API catalog

All under `/api/v1`, mounted in `create_app()`. Auth reuses existing mechanisms verbatim.

### Web App (user-facing; `get_current_client` — initData or session cookie)
```
POST   /webapp/companies                       create draft (tax_id, jurisdiction)
POST   /webapp/companies/lookup                {tax_id} → prefill from gov registry (rate-limited, cached)
GET    /webapp/companies                       my companies (via company_members on telegram_user_id)
GET    /webapp/companies/{id}                  profile + status + trust summary
PATCH  /webapp/companies/{id}                  edit declared fields (draft/needs_info only)
POST   /webapp/companies/{id}/roles            declare business roles
POST   /webapp/companies/{id}/bank-accounts    add account (masked in all responses)
POST   /webapp/companies/{id}/documents        multipart upload (reuses storage_service validation)
POST   /webapp/companies/{id}/licenses         declare license (+link document)
POST   /webapp/companies/{id}/verification/submit
GET    /webapp/companies/{id}/verification     case + per-check statuses (user-safe subset)
GET    /webapp/companies/{id}/eligibility?product_id=…
POST   /webapp/companies/{id}/members/invite   invite by telegram username/contact
GET    /webapp/companies/{id}/trust            score, grade, badges (own view)
```

### Dashboard admin (JWT + RBAC)
```
GET    /admin/verification/cases?status=…             require_analyst_or_admin
GET    /admin/verification/cases/{id}                 full detail incl. snapshots diff
POST   /admin/verification/cases/{id}/approve|reject|request-info
POST   /admin/verification/checks/{id}/rerun
POST   /admin/verification/checks/{id}/waive          require_admin, reason required
GET    /admin/companies?status=&q=…
POST   /admin/companies/{id}/suspend|reinstate        require_admin
GET/POST/PATCH /admin/license-types                   require_admin
GET/POST /admin/license-requirements                  require_admin (versioned publish)
POST   /admin/license-requirements/publish            bump rule_version + bulk recompute
GET    /admin/trust/config  POST /admin/trust/recompute
GET    /admin/integrations/health                     provider circuit/latency status
```

### Internal policy facade (in-process now; the future service API)
```python
company_service.get_company_state(company_id) -> CompanyState        # status, verified_at, roles
compliance_service.check_eligibility(company_id, product_id) -> EligibilityDecision
trust_service.get_trust_summary(company_id) -> TrustSummary
```
Marketplace calls these at offer submit/publish; Deal Lifecycle will call the same contracts (later over HTTP if extracted).

### Public read surface
`GET /webapp/market` offer cards gain: company display name, trust grade + badges, "verified" indicators. Never expose tax debt details or raw check payloads publicly — warnings are company-private + staff-visible.

---

## 9. Verification workflows (sequences)

### 9.1 Onboarding happy path
```
User (Mini App)          API                Outbox/Celery(verify q)      Gateway            Staff
   │ POST /companies      │
   │  {tax_id}            │ create draft ──► [company.registered]
   │ POST …/lookup        │ ──────────────────────────────────────────► soliq/registry
   │ ◄─ prefilled name/address/director (snapshot stored) ◄────────────┘
   │ declare roles, bank, upload docs, licenses
   │ POST …/verification/submit
   │                      │ case: submitted ─► [verification.case.submitted]
   │                      │                     ├─ run_check(gov_registry) ──► snapshot, compare declared vs registry
   │                      │                     ├─ run_check(tax_status)   ──► taxpayer + restrictions
   │                      │                     ├─ run_check(vat_status)
   │                      │                     ├─ run_check(licenses)     ──► registry match else doc review needed
   │                      │                     └─ run_check(bank_account) ──► MFO/format valid + doc present?
   │                      │ each ─► [verification.check.completed] ─► case evaluator
   │                      │ all auto passed, manual items exist ─► pending_review ─► notify staff group
   │                      │                                                        │ approve (dashboard or TG inline)
   │                      │ case approved ─► company.verified ─► trust init, eligibility compute,
   │ ◄── bot DM "Company verified ✅" ◄── notify queue                    marketplace unlock
```

### 9.2 Check failure / degradation
- Provider timeout → check `unavailable`, retry with backoff (attempts capped). Case can reach `pending_review` with unavailable checks; staff may approve with waiver (audited) or wait. **A gov outage never hard-blocks onboarding review** — the platform invariant applied to verification.
- Mismatch (declared name ≠ registry name) → check `failed` with diff in `result`; case → `needs_info`; user corrects; affected checks re-run.

### 9.3 License expiry → eligibility revocation
```
beat license_expiry_scan (daily)
  ├─ T-30/T-7: [license.expiring] ─► bot DM + dashboard alert
  └─ T-0: status=expired ─► [license.expired] ─► eligibility recompute
        └─ eligible=false for category C ─► [company.eligibility.changed]
              ├─ marketplace: approved offers in C ─► archived (reason journaled) + seller DM
              └─ trust: compliance dimension drops
```

### 9.4 Re-verification & registry drift
- `reverification_due_at` (default: verified_at + 365d, runtime-tunable) → beat opens a `reverification` case running only auto checks; silent pass, human review only on drift.
- Monthly (tunable) `registry_refresh_scan` re-snapshots gov status for verified companies; a `liquidated`/`suspended` registry status raises a targeted case + staff alert immediately (does not auto-suspend unless `auto_suspend_on_liquidation=on`).

### 9.5 Bank account verification (strategy ladder)
1. **MVP `document`:** structural validation (MFO exists in CBU directory, 20-digit UZ account format, name match heuristic) + bank reference letter upload → manual review → `verified(method=document)`.
2. **`e_invoice_crosscheck`:** once e-invoice integration exists (deal module), the first inbound/outbound faktura confirms the account org binding → auto-upgrade.
3. **`bank_api` / penny-drop:** per-bank partnerships; adapter slot reserved.
Trust weights the method — API-verified > document-verified.

### 9.6 E-IMZO onboarding path (P2 — first adapter, replaces most manual entry for UZ companies)

**Auth model split — deliberate:** Telegram stays the *session* identity (who is using the app); E-IMZO is *company-identity binding* (one-time, at onboarding or on demand) — never a per-login requirement (the key lives with the director/accountant, mobile webview has no local signing service, foreign companies have no e-imzo at all).

Flow (wizard step 1 gains "Sign instead of typing"):
1. Backend issues a one-time challenge (nonce bound to `telegram_user_id` + draft company, short TTL).
2. Frontend signs it: desktop browser → e-imzo.js/CAPIWS against the local E-IMZO module; mobile/Mini App → QR / deep-link flow with the E-IMZO mobile app.
3. Backend verifies the PKCS#7 via the **UNICON e-imzo-server sidecar** (national O'zDSt algorithms — stock crypto libs cannot verify it) through the Integration Gateway; checks nonce, cert validity window, revocation where available.
4. Certificate subject prefills + locks: `legal_name`, `tax_id`, `director_name`, holder PINFL/position. Check `eimzo_signature` → `passed` (highest confidence tier); signer's membership auto-confirmed as `owner`; the case becomes auto-approve eligible.
5. Signed challenge + certificate stored as immutable evidence (same pattern as `registry_snapshots`); PINFL goes to `company_person_data` (encrypted, §6.2).

Manual entry remains the fallback path (foreign companies, key unavailable, e-imzo outage) at a lower confidence tier with human review. The same signing rails are reused later by the Deal Lifecycle module for e-contract signing (Didox and other EDO operators are consumers of E-IMZO, not the mechanism itself). No gov partner agreement is required for this path — which is why it jumps ahead of soliq in P2 ordering.

---

## 10. Trust score architecture

**Principle:** the score is a versioned pure function over the trust event ledger: `score = f(events, scoring_config_vN)`. Changing weights = new version + recompute; historical scores reproducible.

### Dimensions (v1 weights)
| Dimension | Max | Inputs (v1 available) |
|---|---|---|
| Identity & registry | 25 | company verified (15), registry snapshot fresh <90d (5), business roles confirmed (5) |
| Financial | 15 | bank verified (10; ×0.7 if document-method), VAT payer (5) |
| Compliance | 25 | all required licenses valid (15), no warnings/restrictions (5), docs complete (5) |
| Transactional | 25 | **0 until Deal module** — completed deals, volume, dispute ratio, on-time rate |
| Behavioral | 10 | profile completeness (4), responsiveness to inquiries (3), feedback (3, deal-gated) |

**Grades:** computed on *achievable* points until the deal module ships (so pre-deal companies aren't punished for a dimension that can't be earned): `unrated` (no verification) → `basic` (≥40% achievable) → `verified` (company verified + ≥60%) → `trusted` (≥80% + ≥1 yr clean) → `elite` (≥90% + transactional history). Badges are separate derived facts: `identity_verified`, `bank_verified`, `vat_payer`, `licensed:<type>`, `veteran`, `top_trader` (future).

### Anti-fraud / anti-gaming
- Feedback and transactional events only from **completed, platform-settled deals** (no free-text reviews from unverified accounts).
- Per-dimension caps + diminishing returns; velocity guards (score can rise max X pts / 30d from behavioral inputs).
- Decay: registry freshness and license validity naturally decay the score without re-verification.
- Manual adjustments are ledger events (`admin.trust_adjustment`, reason, actor) — visible in audit, reversible, never a direct field write.
- Ring/collusion detection (shared members, shared bank accounts, mutual-deal loops) — flagging job, phase 2.

---

## 11. RBAC, admin architecture & runtime rules

### Staff roles
Reuse `StaffRole` machinery. MVP maps verification review to `analyst`/`admin` via existing `require_analyst_or_admin`. Phase 2: add `compliance` member to the enum (migration) for a dedicated compliance-officer role: can decide cases and manage rules, cannot manage users/settings.

### Company-side permissions (webapp)
`company_members.member_role`: `owner` (everything incl. members, bank, delete), `manager` (edit profile/docs/licenses, submit verification, publish offers on behalf), `member` (read + operate deals later). Enforced in webapp deps: `require_company_role(company_id, *roles)` resolving via `telegram_user_id`.

### Business-role → capability matrix (extensible)
Capabilities are data (`role_capabilities` seed), not if-statements:
| Business role | Publish products | Respond to buy requests | Deal participation | Visibility |
|---|---|---|---|---|
| manufacturer / importer / trader / distributor | ✅ (eligibility-gated) | ✅ | buyer+seller | market + supplier directory |
| logistics_provider | ❌ products; ✅ service listings (future) | ❌ | service party | logistics directory (deal module) |
| laboratory | ❌ | ❌ | inspection party | lab directory (deal module) |
| insurance_provider | ❌ | ❌ | insurance party | directory (deal module) |
New roles = new seed rows + capability mappings, no code change for gating.

### Runtime business rules (extends `_SPECS` — admin-editable, no deploy)
```
verification_required_for_publish   bool  default false → flip true after rollout grace period
verification_auto_approve           bool  default false (auto-approve when all auto checks pass)
tax_debt_blocking                   bool  default false (store + warn, never auto-block; per brief)
auto_suspend_on_liquidation         bool  default false (alert-first)
reverification_interval_days        int   default 365
license_expiry_warn_days            int   default 30
bank_verification_required          bool  default false
trust_scoring_version               int   default 1
gov_lookup_cache_ttl_hours          int   default 24
```
This *is* the rule engine for §2 of the brief: statuses stored, warnings displayed, blocking behavior configurable — no hardcoded policy. A full rules-DSL engine is deliberately **not** built (YAGNI); `license_requirements` covers the one genuinely data-driven rule domain.

### Admin surfaces (dashboard, `app/[locale]/(dashboard)/…`)
`/verification` (case queue — clone of `/moderation` UX: FIFO, detail drawer with declared-vs-registry diff, evidence viewer, approve/reject/request-info), `/companies` (registry + suspend/reinstate), `/compliance` (license types, requirement rules with version publish), `/admin/integrations` (provider health), trust config in `/admin/settings`. Telegram dual-actioning mirrors offer moderation: case card to staff group with inline `vercase:<action>:<id>` callbacks — same idempotency + group-admin authz pattern as `telegram/handlers/moderation.py`.

---

## 12. Integration architecture

### Adapter pattern (mirrors `SourceAdapter`)
```python
@runtime_checkable
class VerificationProvider(Protocol):
    provider_name: str                      # registry key
    config_schema: type[BaseModel]
    async def lookup(self, query: ProviderQuery) -> ProviderResult   # normalized DTO + raw payload
    async def health(self) -> ProviderHealth
```
Registry (`app/integrations/registry.py`) with import-time self-registration — **imported in both `app/main.py` and the worker task module** (known process-registration gotcha). Every call: snapshot persisted (`ON CONFLICT DO NOTHING`), call-log row, wrapped in circuit breaker (open after N failures / T window → checks report `unavailable` instantly instead of hammering a dead API) + per-provider rate limiter + response cache (`gov_lookup_cache_ttl_hours`).

### Uzbekistan provider map (verify availability — Open Questions)
| Need | Candidate | Notes |
|---|---|---|
| Registry (name, address, director, status, reg. date) by STIR | Tax Committee (soliq.uz) APIs / my.gov.uz open-data / stat.uz register | Partner-API agreements likely required; scrape/open-data fallback with lower confidence score |
| Taxpayer + VAT payer status, restrictions | soliq.uz VAT register + taxpayer lookup | Same |
| License registries | license.gov.uz (unified licensing portal) | Coverage per chemical license type must be confirmed; fallback = document upload + manual |
| Bank MFO directory | CBU (already integrated: `cbu_rates` adapter exists — same host org) | Static-ish; cacheable |
| Account ownership | none today | Strategy ladder §9.5 |
| Company identity + authorized-rep proof (strong) | **E-IMZO signature challenge — first P2 adapter, before soliq** | No partner agreement needed (local signature verification vs public root certs); cert subject carries org name, INN/STIR, holder's name, PINFL, position. Requires UNICON's e-imzo-server (Java) as a sidecar container behind the gateway (national O'zDSt crypto). See §9.6 |
| Sanctions/watchlists | internal list + optional intl lists | Runtime-configurable check |

### Deal Lifecycle reuse (the point of building the gateway now)
Escrow, e-invoice (Didox/Faktura operators), e-contract, customs (Single Window), track&trace (ASL BELGISI), logistics — all become new `VerificationProvider`-style adapters in the same gateway with the same snapshot/circuit/log machinery. The Deal module consumes companies via `public_id`, eligibility via the facade, and documents via the shared vault. **No refactoring of this module needed** — that was the design goal.

---

## 13. Audit & compliance architecture

- **Actor audit:** every state-changing admin/user action → existing `audit_log` via `write_audit` in the same transaction (`vercase.approve`, `check.waive`, `rules.publish`, `company.suspend`, `trust.adjust`…). Telegram actors: `staff_user_id=NULL` + telegram id in details (existing convention).
- **Evidence audit:** `registry_snapshots` are immutable; checks/decisions FK to them → any historical decision is reconstructable: *what did we know, when, from where*.
- **Decision audit:** eligibility rows store `reasons` + `rule_version`; trust profiles store `scoring_version`; prompts…rules never mutated in place — versioned like the LLM prompt convention already used in this repo.
- **Data lifecycle:** call-log prunable (90d); snapshots retained (legal evidence); documents retained per retention policy (Open Question — UZ law); right-to-erasure applies to *personal* data (member contact info), never to audit/evidence of a legal entity's verification.

## 14. Notification architecture

Reuses the `notify` queue end-to-end (token-bucket rate limits, fail-soft enqueue wrapped in try/except, tasks never raise). New tasks in `app/tasks/notify.py` (module already registered): `send_verification_status_dm` (localized, reuses D-10 status-push pattern), `send_verification_case_to_group` (inline approve/reject keyboard, clone of `send_offer_to_group`), `send_license_expiry_dm`, `send_trust_badge_dm`. Dashboard gets live case-queue updates via the existing SSE channel. All user-facing strings in all bot/webapp locales (ru/en/uz/tr/fa/zh) from day one — same rule as the rest of the stack.

## 15. Security architecture

- **PII/financial data:** account numbers encrypted at the app layer (Fernet/AES-GCM; `VERIFICATION_ENC_KEY` env — required, no default, per config convention) — stored as `account_number_enc` + `account_last4`; full number never in API responses or logs. Director personal data minimized to what the registry publishes.
- **Documents:** private bucket prefix `verification/`; magic-byte MIME validation + size caps (existing `validate_upload`); download via short-lived presigned URLs, staff-RBAC- or member-gated; sha256 stored for tamper evidence.
- **AuthZ:** company resources always resolved through `company_members` on the *verified* telegram identity — never trust body-provided company_id without membership check. Staff decisions: actor from JWT `sub` only (existing convention).
- **Provider credentials:** per-provider secrets in env (no defaults); outbound calls TLS; provider webhooks (future banks) signature-verified + replay-protected.
- **Abuse controls:** `lookup` endpoint rate-limited per user + cached (prevents using IMEX as a free INN-enumeration oracle); document upload counts capped; one open case per company (DB-enforced).
- **Data localization:** UZ personal-data law requires citizens' personal data stored in-country — current hosting must be confirmed compliant (Open Question).

## 16. Risks & tradeoffs

| Risk | Impact | Mitigation |
|---|---|---|
| Gov APIs unavailable / no partner agreement at launch | Auto-checks degrade to manual review | Design already treats every check as waivable/manual-fallback; ship with document-based flow, wire APIs incrementally |
| Bank ownership unverifiable via API | Weakest trust link; fraud vector | Method-weighted trust; e-invoice cross-check upgrade path; never claim "bank verified" UI-wise for document-method without qualifier |
| Wrong license-requirement rules → false "eligible" verdicts | Legal/reputational | Rules-as-data with staff ownership + versioning; "advisory" level for uncertain rules; legal review gate before `verification_required_for_publish=true` |
| Verification friction kills seller acquisition | Marketplace liquidity | Grace-period rollout: verification optional → badge advantage → required (runtime flag); existing sellers grandfathered until flag flips |
| Score gaming pre-deal-history | Trust inflation | Achievable-points grading, deal-gated feedback, velocity caps |
| Single Postgres growth (snapshots, events) | Ops | Partial indexes now; partition `domain_events`/`registry_snapshots` by month when >10M rows; both prunable/archivable |
| Enum-heavy PG migrations | Migration friction | Accepted — codebase convention; keep enums additive |
| Identity-model debt (clients/sellers/companies triangle) | Complexity | Bridging FKs now; unify user identity only when a real driver appears (deliberately deferred) |

## 17. Open questions (business decisions required)

1. **Which gov integrations are actually contracted/available?** soliq partner API, my.gov.uz open data, license.gov.uz — need confirmed access paths before promising auto-checks (affects onboarding SLA promise).
2. **Is verification blocking at launch?** Recommended: no — grace period, then flip `verification_required_for_publish`. Business must set the date.
3. **Who reviews?** Existing analysts, or hire/designate a compliance officer (drives the `compliance` role addition)?
4. **Director identity proof level for MVP:** registry name-match only, document upload, or wait for e-imzo challenge?
5. **Authoritative license-type list for chemical categories in UZ** (precursors, hazardous classes) — needs regulatory research + legal sign-off; who owns rule content?
6. **Foreign companies** (importers from TR/CN/RU…): supported at launch? If yes: which registries, or manual-only KYB tier with capped trust?
7. **Tax-debt display policy:** private-to-company only, staff-only, or visible warning to counterparties? (Brief says warn, not block — but *who sees* the warning is a business call.)
8. **Data retention & localization:** retention period for verification documents; confirm hosting satisfies UZ personal-data localization.
9. **Trust score public exposure:** full numeric score public, or grade+badges public and numbers private? (Recommended: grade+badges public.)
10. **Re-verification cadence** (default 365d?) and whether registry-drift monitoring is monthly or weekly (API quota dependent).

## 18. Technology stack (recommendation = current stack + minimal additions)

| Concern | Choice | Why |
|---|---|---|
| Services/API | FastAPI (existing) | — |
| Async work | Celery, new `verify` queue + `notify` reuse | matches topology; add `-Q …,verify` to worker |
| Events | Postgres outbox + beat dispatcher → Kafka/NATS later | no new infra day 1; no dual-write |
| DB | Postgres (existing), migration 0017+ | — |
| Docs | MinIO/S3 via existing `storage_service` | — |
| Encryption | `cryptography` (Fernet/AES-GCM), key in env | app-layer, DB-agnostic |
| Circuit breaker | small in-repo util (or `aiobreaker`) | keep deps pinned/minimal |
| Frontends | webapp (Mini App onboarding wizard — clone request-wizard zustand pattern), dashboard (case queue — clone moderation UX) | — |
| Digital signature (P2) | E-IMZO integration | strongest UZ KYB proof |

### Delivery phasing (suggested)
- **P1 (foundation):** companies/members/roles, document vault, verification cases with manual + structural checks, admin queue (dashboard+TG), outbox, audit, webapp onboarding wizard, `company.verified` badge in market. *No gov API dependency.*
- **P2 (automation):** soliq/registry/license adapters, auto-checks, lookup-prefill, re-verification scans, license expiry engine, eligibility gating (advisory), trust v1.
- **P3 (enforcement + hardening):** `verification_required_for_publish=true`, eligibility enforcement on publish, e-imzo, bank strategy upgrades, ring detection, `compliance` staff role.
