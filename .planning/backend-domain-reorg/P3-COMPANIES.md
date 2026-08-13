# P3 — Companies domain migration

> Prereq reading: `00-CONTEXT.md` (track goal, target convention, binding coupling findings),
> `P1-MARKETPLACE.md` (folder convention + import-alias technique), `P2-VERIFICATION.md`
> (the portal `deps.py` extraction and the `app/api/portal/companies.py` split this phase
> completes). **P1 and P2 must both be merged and green before this phase starts.**

**Goal:** `company_service`, `directory_service`, `models/companies.py`, the remainder of
`api/portal/companies.py`, and the remainder of `schemas/portal_company.py` move into
`backend/app/domains/companies/`. Every call site repo-wide updated in the same change, full gate
green. No behavior change.

## Read this first — this is the big one

`00-CONTEXT.md` sequenced companies third precisely because it has the **highest fan-in**:
**76 files** import `app.models.companies`, and **41 files** touch `company_service`. That is
roughly 2.5× the marketplace pilot. Two consequences:

- **Do not attempt this phase in one sitting without the gate running locally.** The failure mode
  is not a hard error — it is a partially-updated import graph that imports fine but fails 40 tests
  at once, where the signal is buried.
- **The sequencing bet only pays off if P1 and P2 actually landed.** Both marketplace and
  verification are heavy `models.companies` consumers; migrating them first means their call sites
  are already in `app/domains/` and get updated once, in place, rather than twice.

## Scope decisions

- **`directory_service` — included** (deferred here from P2; see that plan's rationale). It queries
  `Company` by confirmed `CompanyBusinessRole` and is the single source of truth behind all four
  public directories. It lands as `app/domains/companies/directory.py`.
- **`review_service` + `models/reviews.py` + `models/media.py` — excluded. DECIDED: P11 takes
  them.** They were argued for here — `CompanyReview` and `CompanyMedia` are company-owned (one row
  per *(subject company, author company)* pair; images a *company's* public profile references),
  and `portal/companies.py` already imports `review_service` and `storage_service` side by side for
  the public-profile routes. The call was made to keep the roadmap's placement and leave them to
  P11, which lands them in `app/domains/companies/` as a follow-on commit.

  Two consequences to expect and accept in this phase, neither a defect:
  - The companies domain is **visibly incomplete until P11** — `CompanyReview` and `CompanyMedia`
    stay in `app/models/`, so "everything about companies" is not yet one folder.
  - `_summary_out` / `_detail_out` will reach back into `app/models/reviews.py` for review
    aggregates, and `portal/companies.py` will keep importing `review_service` from
    `app.services`. Leave both alone; do not add a shim or pre-move a single file to tidy the
    import.

  This is settled — do not re-litigate it mid-phase.
- **`otp_service` — still excluded** (see `P2-VERIFICATION.md`). It upserts `user_accounts`, not
  companies. It belongs with `models/accounts.py` in the P11 accounts/auth grouping.
- **`models/accounts.py` — excluded.** `UserAccount` is the portal *identity*; a company is a thing
  an account owns. Different lifecycle, different domain. It goes to the accounts grouping.

## Files moving

| From | To |
|---|---|
| `app/models/companies.py` | `app/domains/companies/models.py` |
| `app/services/company_service.py` | `app/domains/companies/service.py` |
| `app/services/directory_service.py` | `app/domains/companies/directory.py` |
| `app/api/portal/companies.py` *(post-P2 remainder)* | `app/domains/companies/api_portal.py` |
| `app/schemas/portal_company.py` *(post-P2 remainder)* | `app/domains/companies/schemas.py` |

That is the complete list. `models/reviews.py`, `models/media.py` and `review_service` are
**not** part of this phase — see the scope decision above; P11 moves them into this same folder
later.

**No admin router moves.** There is no `app/api/admin_companies.py` — staff-side company
administration lives inside `app/api/admin_verification.py`, which P2 already moved to
`app/domains/verification/api_admin.py`. It keeps its `Company`/`CompanyBankAccount` imports,
re-pointed to `app.domains.companies.models`. That is a legitimate cross-domain read, not a
missed file.

### What `portal/companies.py` looks like when this phase starts

After P2 it has lost the four shared helpers (to `app/api/portal/deps.py`), the five
verification routes, and `_check_out`/`_case_out`/`_latest_case`/`_document_or_404`. What remains
— and moves whole — is:

| Route | Line (pre-P2 numbering) |
|---|---|
| `POST ""` (create company) | 221 |
| `GET ""` (list) | 252 |
| `GET /{company_id}` | 260 |
| `PATCH /{company_id}` | 269 |
| `PATCH /{company_id}/public-profile` | 289 |
| `POST` (logo/cover upload, 324) · `PUT /{company_id}/roles` | 324, 380 |
| bank accounts `POST` / `DELETE` | 406, 425 |
| media + review routes | 451, 488, 513, 550, 569 |

plus helpers `_summary_out` (135) and `_detail_out` (154). Re-derive these line numbers from the
post-P2 file — **do not trust the numbers above after P2 lands**; they are here to show shape and
size, not as edit coordinates.

> **Depends on a P2 amendment.** `_summary_out` calls
> `verification_service._open_case_for(db, company.id)` at line 136 — a private function in
> another domain. P2 promotes it to a public `open_case_for` precisely so this phase does not
> carry a privates-crossing-boundaries call into `app/domains/companies/`. Verify before starting:
> `grep -rn "_open_case_for" backend/app backend/tests` must return nothing. If it does not, P2
> shipped without the amendment — do the promotion first, as its own commit, rather than moving
> the private call.

## Call sites to update

### `app.models.companies` — 76 files

This is the bulk of the phase. Grouped by area (confirmed via repo-wide grep on the pre-P1 tree;
re-run before starting, since P1/P2 will have relocated some of these):

- **Barrel:** `app/models/__init__.py` line 23 — update in place, keep FK-order position. The
  `__all__` entries (`Company`, `CompanyMember`, `CompanyBusinessRole`, `CompanyBankAccount`) are
  name-only, no edit.
- **Models with FKs to Company** (4): `app/models/{compliance,lab,marketplace,requests}.py`.
  `marketplace.py` will already be `app/domains/marketplace/models.py` after P1.
- **Admin routers** (8): `app/api/admin_{contracts,deals,escrow,lab,lab_requests,licenses,
  logistics_requests,verification}.py`.
- **Portal routers** (8): `app/api/portal/{companies,contracts,deals,lab_requests,logistics,
  manufacturers,market,samples}.py`.
- **Other API** (2): `app/api/public.py`, `app/api/webapp/market.py`.
- **Services** (20): `app/services/{company_service,contract_service,deal_service,
  directory_service,eimzo_service,lab_service,laboratory_service,logistics_service,
  manufacturer_service,notification_service,offer_request_service,offer_service,
  public_market_service,registry_service,request_service,review_service,rfq_push_service,
  rfq_response_service,sample_service,storage_service,supplier_matching_service,
  verification_checks,verification_service}.py`.
- **Tasks/seed** (3): `app/tasks/{notify,verification}.py`, `app/seed/seed_showcase_media.py`.
- **Tests** (~30): `tests/_verification_db.py` plus `tests/test_{admin_verification_api,
  business_role_badges,company_logo_storage,company_reviews_api,company_service,
  company_service_db,contract_service_db,dual_origin_offers,eimzo_service_db,
  notify_request_group,offer_requests,portal_companies_api,portal_company_logo_api,
  portal_deals_api,portal_lab_requests_api,portal_logistics_api,portal_manufacturers_api,
  portal_offer_photos_api,portal_role_gates_api,public_api,rfq_push,supplier_matching,
  verification_checks,verification_document_vault,verification_handler,
  verification_service_db}.py`.

### `company_service` — 41 files

Almost entirely **submodule-namespace style** (`from app.services import company_service`, call
sites doing `company_service.foo(...)`) — only **one** file uses the full
`app.services.company_service` path (`tests/test_account_type_exclusivity.py`). So the alias fix
covers ~40 of 41 files with a one-line change each:

```python
from app.domains.companies import service as company_service
```

Importers: `app/api/portal/{contracts,eimzo,inquiries,manufacturers,offers,requests,samples}.py`,
`app/api/admin_verification.py` (→ `app/domains/verification/api_admin.py` after P2),
`app/services/{laboratory_service,logistics_service,manufacturer_service,offer_service,
rfq_response_service}.py`, `app/tasks/verification.py`, plus ~24 test files.

**Watch for parenthesised blocks.** Several of these import `company_service` inside a multi-name
`from app.services import (…)` block alongside shared-kernel names. Those must be **split by
hand** — sed will corrupt them. Example, `app/api/portal/companies.py` currently:

```python
from app.services import (
    audit_service, company_service, directory_service,
    rate_limit, review_service, storage_service, verification_service,
)
```
becomes (post-P2, post-P3) three imports: the shared-kernel names stay on `app.services`, and
`company_service` / `directory_service` / `review_service` / `verification_service` each become
their own aliased domain import.

### `directory_service` — 6 files
`app/api/portal/companies.py`, `app/api/admin_verification.py`,
`app/services/{public_market_service,manufacturer_service}.py`, `tests/test_public_api.py`.
All namespace-style → alias fix.

### `app.schemas.portal_company` — 9 files
`app/api/portal/{companies,offers}.py`, `app/schemas/portal_eimzo.py`,
`app/services/offer_service.py` (→ `app/domains/marketplace/service.py` after P1),
`tests/test_{company_service,offer_compliance_gate_db,offer_product_facts,offer_sale_fields,
security_pass}.py`.

> Note `app/schemas/portal_eimzo.py` imports from `portal_company` — a schema-level dependency
> from contracts (P4) into companies. Re-point it; do not try to untangle it here.

### `app.api.portal.companies` — 15 files
After P2's `deps.py` extraction, the only remaining importers are `app/main.py` line 63 (router
import) and the four test files that import the router directly
(`test_company_reviews_api.py`, `test_portal_companies_api.py`,
`test_portal_company_logo_api.py`, plus the deferred-import sites at lines 31/34/288/324 of
various modules — re-grep for `from app.api.portal.companies import router`). The eleven
private-helper importers are gone by then. **Verify that is true before starting** — it is the
single assumption this phase's difficulty estimate rests on:

```
grep -rn "from app.api.portal.companies import _" backend/app backend/tests   # must be empty
```

## Steps

1. Re-run the grep inventory above against the post-P2 tree. The counts here were measured on the
   pre-P1 tree; P1 and P2 will have moved some importers into `app/domains/`. **The re-grep is
   the plan, this document is the map.**
2. Create `app/domains/companies/__init__.py`.
3. `git mv` `models/companies.py`, `services/company_service.py`, `services/directory_service.py`,
   `api/portal/companies.py`, `schemas/portal_company.py` to their new paths. **Five files — not
   the review/media trio**, which P11 owns.
4. Fix internal imports within the moved files.
5. Update the `app/models/__init__.py` barrel line for `companies.py` (line 23), preserving its
   position in the FK-ordered list.
6. Replace call sites:
   - `app.models.companies` → `app.domains.companies.models`
   - `app.schemas.portal_company` → `app.domains.companies.schemas`
   - `app.api.portal.companies` → `app.domains.companies.api_portal`
   - `app.services.company_service` → `app.domains.companies.service` *(1 file)*
   Then handle the namespace-style imports by alias, splitting parenthesised blocks by hand.
7. Update `app/main.py` line 63's import path. `include_router(portal_companies_router, …)` at
   line 244 and the surrounding ordering comments (234–244) are **unchanged** — the router object
   and its prefix are identical, only the import path moves.
8. Update `backend/pyproject.toml` mypy overrides (the `app.domains.*` blocks established in P2 —
   verify they are present) and the mypy invocations, local + `.github/workflows/ci.yml` lines 75
   and 78, adding `app/domains/companies/{service,directory}.py` to the services check and
   `app/domains/companies/schemas.py` to the schemas check.
9. Run the full gate and fix anything red:
   - `cd backend && ruff check .`
   - `cd backend && mypy app/services app/domains/*/service.py app/domains/companies/directory.py app/domains/verification/{checks,registry}.py app/domains/marketplace/{requests,compliance}.py --ignore-missing-imports`
   - `cd backend && mypy app/schemas app/domains/*/schemas.py --ignore-missing-imports`
   - `cd backend && pytest tests/ -q` (full suite, not a subset)
10. Commit once everything is green.

> **On the "one atomic commit" rule.** `00-CONTEXT.md` requires each domain move to be atomic —
> move, update every call site, gate green, commit. At 76 files that stays achievable and this
> phase should honor it. If it proves not to be, the correct split is P2's shape — a **prep**
> commit that is independently green and useful (e.g. the `directory_service` extraction alone),
> then the move commit. Never a commit that leaves a half-updated import graph.

## Verification

- `ruff check .` — no new lint errors.
- Both `mypy` invocations — clean.
- `pytest tests/ -q` — full suite green. Highest-signal files:
  `test_company_service.py`, `test_company_service_db.py`, `test_portal_companies_api.py`,
  `test_portal_company_logo_api.py`, `test_company_reviews_api.py`, `test_company_logo_storage.py`,
  `test_business_role_badges.py`, `test_portal_role_gates_api.py`,
  `test_account_type_exclusivity.py`, `test_public_api.py`, `test_supplier_matching.py`,
  `test_admin_verification_api.py`.
- `uv run uvicorn app.main:app --reload` boots without import errors.
- **Route-parity check:** compare `sorted((r.path, tuple(sorted(r.methods))) for r in app.routes)`
  before and after — byte-identical. The portal include-order at `main.py` 234–244 is load-bearing
  and this phase touches the router it orders around.
- **`Base.metadata` parity:** `sorted(Base.metadata.tables)` before and after — identical. With 4
  models holding FKs to `Company` and a known circular FK with `verification.py`, a dropped barrel
  line would surface here faster than in alembic.
- `grep -rn "app\.models\.companies\|app\.schemas\.portal_company\|app\.services\.company_service\|app\.services\.directory_service\|app\.api\.portal\.companies" backend/app backend/tests` returns nothing.
