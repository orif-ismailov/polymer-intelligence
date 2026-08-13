# P4 — Contracts domain migration

> Prereq reading: `00-CONTEXT.md` (track goal, target convention, binding coupling findings),
> `P1-MARKETPLACE.md` (folder convention + import-alias technique), `P2-VERIFICATION.md`
> (`app/api/portal/deps.py`, the `open_case_for` promotion), `P3-COMPANIES.md` (the companies
> portal router this phase hands a route back to). **P1–P3 must be merged and green before this
> phase starts.**

**Goal:** `contract_service`, `contract_render`, `eimzo_service`, `models/contracts.py`,
`models/eimzo.py`, `schemas/portal_contract.py`, `schemas/portal_eimzo.py`,
`api/admin_contracts.py`, `api/portal/contracts.py`, and `api/portal/eimzo.py` move into
`backend/app/domains/contracts/`. Every call site repo-wide updated in the same change, full gate
green. One structural fix travels with it (below); otherwise no behavior change.

## Size

**~20 unique files**, and the reference counts are the smallest of any phase so far:
`contract_service` 4, `contract_render` 4, `eimzo_service` 6, `models.contracts` 14,
`models.eimzo` 5, and **1 file each** for both schema modules. After the 76-file grind of P3 this
is a small, well-fenced phase — it is a good one to use to confirm the convention still holds
before the wider phases (P5 deals, P8 news) start.

## The structural fix: `GET /portal/companies/directory`

`app/api/portal/contracts.py:153` defines `GET /companies/directory` on a router prefixed
`/portal`. It is a **pure companies query** — `Company` filtered to `status == verified`, with
`business_roles` eager-loaded and confirmed roles projected into `DirectoryCompanyOut`. It
touches no contract table. It sits in the contracts router for historical reasons, and
`app/main.py:234-235` carries an explicit comment pinning include-order because of it:

```
# Contracts router first: its literal /portal/companies/directory must win over the
# companies router's /portal/companies/{company_id} param route.
application.include_router(portal_contracts_router, prefix="/api/v1")
```

If this route simply travels with the contracts domain, P4 permanently parks a companies concern
inside `app/domains/contracts/` **and** keeps a cross-router include-order dependency that no
route-parity check will protect (parity compares the route set, not which router won a match).

**Do this instead:** move `company_directory` and its `DirectoryCompanyOut` schema into
`app/domains/companies/api_portal.py` (P3's output), declared **above** the `/{company_id}` route
in that file. FastAPI matches in declaration order *within* a router, so a literal sibling
declared first beats the param route with no include-order dependency at all. The
`main.py:234-235` comment and the ordering it enforces then become dead and should be deleted.

The resulting path is byte-identical (`/api/v1/portal/companies/directory`), so the route-parity
check still holds. The behavior change is nil; the fragility removed is real.

> **Follow-up, do not fix here:** `company_directory` hand-rolls a verified-company query that
> overlaps `directory_service` (P3's `app/domains/companies/directory.py`), whose whole docstring
> argument is that the directories "are one query with one parameter, not four surfaces." They
> differ today (this one resolves by `company_id` and filters `verified`, the service keys on
> confirmed business role), so collapsing them is a behavior decision, not a move. File it as its
> own task once both live in the companies domain and the duplication is visible in one folder.

## Scope decisions

- **`models/eimzo.py` — included.** `SignatureEvidence` is referenced by
  `models/contracts.py` itself; `CompanyPersonData` is written by `eimzo_service` and read
  nowhere else. Semantically `CompanyPersonData` is a *verification* artifact (it records the
  person data from a company's E-IMZO confirmation), but `eimzo_service` is its only writer and
  P4 owns that service. Splitting the two-class file to send one class to P2's folder would buy
  nothing. It moves whole, as `eimzo_models.py`.
- **`api/portal/eimzo.py` — included, with the same caveat.** Its two routes
  (`POST /{company_id}/eimzo/challenge`, `POST /{company_id}/eimzo/verify`) are **company
  confirmation**, not contract signing — arguably P2 verification territory. They are driven
  entirely by `eimzo_service`, which owns contract signing too, so they travel with it. Both sit
  a segment deeper than `/{company_id}` and cannot shadow it; no include-order concern.
- **`app/integrations/eimzo/` — stays put.** `app/integrations/` is the same category as
  `app/ingest/`: external-provider adapters with their own per-provider structure, which
  `00-CONTEXT.md` explicitly leaves alone. `ProviderUnavailable` keeps being imported from
  `app.integrations.eimzo`.
- **`app/tasks/contracts.py` — stays put.** `app/tasks/` is not moved by this track. It imports
  everything function-locally (`# noqa: PLC0415`) already, so only those inner import lines
  change. The beat entries and `_TASK_MODULES` are untouched.
- **`app/seed/seed_contract_templates.py` + `app/seed/data/contract_templates/` — stay put.**
  Seeders are their own layer and no phase has moved one; `contract_render` reads template HTML
  from the `ContractTemplate` row, not from disk, so there is no asset coupling to follow.

## Correction inherited from P2

`P2-VERIFICATION.md` originally deferred the `verification_service._open_case_for` private
cross-domain call to this phase. That was based on an incomplete grep — the function has **three**
callers, not two:

| Caller | Domain | Phase |
|---|---|---|
| `verification_service.py:158` | verification (internal) | — |
| `app/api/portal/companies.py:136` (inside `_summary_out`) | companies | **P3** |
| `eimzo_service.py:153` | contracts | **P4** |

So P3 crosses the boundary before P4 does, and the definition lives in P2's own domain. P2 has
been amended to **promote it to a public `open_case_for`** when it moves
`verification_service.py` — a three-call-site rename inside the phase that owns the definition.

**By the time P4 starts, `eimzo_service.py:153` should already read
`verification_service.open_case_for(...)`.** Verify that before starting:

```
grep -rn "_open_case_for" backend/app backend/tests    # must return only the def-internal calls
```

If it still shows the underscore, P2 shipped without the amendment — do the promotion here rather
than moving a private cross-domain call into a new folder.

## Files moving

| From | To |
|---|---|
| `app/models/contracts.py` | `app/domains/contracts/models.py` |
| `app/models/eimzo.py` | `app/domains/contracts/eimzo_models.py` |
| `app/schemas/portal_contract.py` | `app/domains/contracts/schemas.py` |
| `app/schemas/portal_eimzo.py` | `app/domains/contracts/eimzo_schemas.py` |
| `app/services/contract_service.py` | `app/domains/contracts/service.py` |
| `app/services/contract_render.py` | `app/domains/contracts/render.py` |
| `app/services/eimzo_service.py` | `app/domains/contracts/eimzo.py` |
| `app/api/admin_contracts.py` | `app/domains/contracts/api_admin.py` |
| `app/api/portal/contracts.py` *(minus `company_directory`)* | `app/domains/contracts/api_portal.py` |
| `app/api/portal/eimzo.py` | `app/domains/contracts/api_portal_eimzo.py` |

> **Naming note.** `app/domains/contracts/eimzo.py` sits alongside imports from
> `app.integrations.eimzo`. Inside `api_portal.py` both appear:
> `from app.integrations.eimzo import ProviderUnavailable` and
> `from app.domains.contracts import eimzo as eimzo_service`. That reads acceptably and matches
> P1's precedent (`offer_compliance_service.py` → `compliance.py`). If it grates during the move,
> `signing.py` is the alternative — decide before step 3, not after.

## Call sites to update

Counts confirmed by repo-wide grep on the **pre-P1** tree. P1–P3 will have relocated several of
these (`offer_service` → `app/domains/marketplace/service.py`, `portal/companies.py` →
`app/domains/companies/api_portal.py`, and so on). **Re-run the greps against the post-P3 tree
before starting** — this section is the map, not the coordinates.

- **`app.models.contracts`** (14 files): `app/models/__init__.py` (barrel, line 34 — update in
  place, keep FK-order position), `app/api/admin_contracts.py`, `app/api/portal/contracts.py`,
  `app/api/portal/deals.py`, `app/seed/seed_contract_templates.py`,
  `app/services/{contract_service,deal_service}.py`, `app/tasks/{contracts,notify}.py`, plus
  `tests/test_{contract_beat_db,contract_notify,contract_service_db,contracts_api,
  deal_contract_link_db}.py`.
- **`app.models.eimzo`** (5 files): `app/models/__init__.py` (barrel, line 47),
  `app/api/portal/contracts.py`, `app/services/{contract_service,eimzo_service}.py`,
  `tests/test_eimzo_service_db.py`. `__all__` entries (`CompanyPersonData`, `SignatureEvidence`,
  line 246 area) are name-only — no edit.
- **`app.schemas.portal_contract`** (1 file): `app/api/portal/contracts.py`.
- **`app.schemas.portal_eimzo`** (1 file): `app/api/portal/eimzo.py`. Note this module imports
  from `app.schemas.portal_company` — after P3 that is `app.domains.companies.schemas`; re-point,
  do not untangle.
- **`contract_service`** (4 files): `app/api/portal/contracts.py`, `app/tasks/contracts.py`
  (function-local, lines 27 and 94), `tests/test_{contract_service_db,contracts_api}.py`.
- **`contract_render`** (4 files): `app/services/contract_service.py`,
  `tests/test_{contract_render,contract_service_db,contracts_api}.py`.
- **`eimzo_service`** (6 files): `app/api/portal/{contracts,eimzo}.py`,
  `app/services/contract_service.py`, `tests/test_{contract_service_db,eimzo_service_db,
  portal_eimzo_api}.py`. Includes one **class import**, not a namespace import:
  `app/api/portal/contracts.py:44` — `from app.services.eimzo_service import CertCompanyMismatch`.
  That one is a plain path swap, no alias needed.
- **Routers** (2 files each): `app.api.admin_contracts` and `app.api.portal.contracts` →
  `app/main.py` (lines 39 and 65) + `tests/test_contracts_api.py`; `app.api.portal.eimzo` →
  `app/main.py` (line 67) + `tests/test_portal_eimzo_api.py`.
- **Namespace-style imports** — `app/api/portal/contracts.py:43` is a mixed block:
  ```python
  from app.services import company_service, contract_service, rate_limit, storage_service
  ```
  `rate_limit` and `storage_service` are shared kernel and stay on `app.services`;
  `company_service` is already `app.domains.companies.service` after P3; `contract_service`
  becomes `from app.domains.contracts import service as contract_service`. **Split by hand — sed
  will corrupt this line.** Same treatment for `app/tasks/contracts.py:27` and `:94`.

## Steps

1. Re-run the grep inventory against the post-P3 tree. Confirm the `open_case_for` promotion
   landed (see above) and that `grep -rn "from app.api.portal.companies import _"` is empty.
2. Create `app/domains/contracts/__init__.py`.
3. `git mv` the 10 files to their new paths (preserves history).
4. **Extract `company_directory` + `DirectoryCompanyOut`** out of `api_portal.py` and into
   `app/domains/companies/api_portal.py`, declared above the `/{company_id}` route. Move its
   `rate_limit.enforce_window(..., "directory", ...)` call and the `DIRECTORY_SEARCH_PER_MIN`
   constant reference with it. Delete the now-dead ordering comment at `app/main.py:234-235`.
5. Fix internal imports within the moved files (`contract_service` → `render`, `eimzo`,
   `models`, `eimzo_models`; `eimzo.py` → `app.domains.verification.service`).
6. Update the `app/models/__init__.py` barrel lines for `contracts.py` (34) and `eimzo.py` (47),
   preserving FK-order position.
7. Replace call sites:
   - `app.models.contracts` → `app.domains.contracts.models`
   - `app.models.eimzo` → `app.domains.contracts.eimzo_models`
   - `app.schemas.portal_contract` → `app.domains.contracts.schemas`
   - `app.schemas.portal_eimzo` → `app.domains.contracts.eimzo_schemas`
   - `app.services.contract_service` → `app.domains.contracts.service`
   - `app.services.contract_render` → `app.domains.contracts.render`
   - `app.services.eimzo_service` → `app.domains.contracts.eimzo`
   - `app.api.admin_contracts` → `app.domains.contracts.api_admin`
   - `app.api.portal.contracts` → `app.domains.contracts.api_portal`
   - `app.api.portal.eimzo` → `app.domains.contracts.api_portal_eimzo`
   Then split the mixed `from app.services import (…)` lines by hand and alias.
8. Update `app/main.py` import lines 39, 65, 67. The three `include_router` calls keep their
   positions — **except** that the contracts router no longer needs to precede the companies
   router, which is the point of step 4. Leave the *order* alone anyway (it is now merely
   arbitrary rather than load-bearing); only the comment goes.
9. Update `backend/pyproject.toml` mypy overrides (the `app.domains.*` blocks from P2 — verify
   present) and the mypy invocations, local + `.github/workflows/ci.yml` lines 75/78, adding
   `app/domains/contracts/{service,render,eimzo}.py` to the services check and
   `app/domains/contracts/{schemas,eimzo_schemas}.py` to the schemas check.
10. Run the full gate and fix anything red:
    - `cd backend && ruff check .`
    - `cd backend && mypy app/services app/domains/*/service.py app/domains/contracts/{render,eimzo}.py app/domains/companies/directory.py app/domains/verification/{checks,registry}.py app/domains/marketplace/{requests,compliance}.py --ignore-missing-imports`
    - `cd backend && mypy app/schemas app/domains/*/schemas.py app/domains/contracts/eimzo_schemas.py --ignore-missing-imports`
    - `cd backend && pytest tests/ -q` (full suite, not a subset)
11. Commit once everything is green.

## Verification

- `ruff check .` — no new lint errors.
- Both `mypy` invocations — clean.
- `pytest tests/ -q` — full suite green. Highest-signal files: `test_contracts_api.py`,
  `test_contract_service_db.py`, `test_contract_render.py`, `test_contract_beat_db.py`,
  `test_contract_notify.py`, `test_deal_contract_link_db.py`, `test_eimzo_service_db.py`,
  `test_portal_eimzo_api.py`.
- **`test_contract_render.py` is the golden-hash test.** `render_contract_html` is pinned to a
  stable sha256 (timestamps are injected, never `now()`). If that hash moves, something in the
  render path changed — a move must not touch it. Treat a hash diff as a hard stop, not a
  fixture to update.
- `uv run uvicorn app.main:app --reload` boots without import errors. WeasyPrint's import in
  `render.py` is lazy by design (native libs are in the Docker image, not necessarily local) —
  an ImportError at boot means the laziness was broken by the move.
- **Route-parity check:** compare `sorted((r.path, tuple(sorted(r.methods))) for r in app.routes)`
  before and after — byte-identical. This phase relocates a route between routers, so parity is
  the primary guard, backed by an explicit request-level check that
  `GET /api/v1/portal/companies/directory` still resolves to `company_directory` and **not** to
  `get_company` with `company_id="directory"` (which would now 422 rather than 404 — the exact
  failure the deleted ordering comment used to prevent).
- `grep -rn "app\.models\.contracts\|app\.models\.eimzo\|app\.schemas\.portal_contract\|app\.schemas\.portal_eimzo\|app\.services\.contract_\|app\.services\.eimzo_service\|app\.api\.admin_contracts\|app\.api\.portal\.contracts\|app\.api\.portal\.eimzo" backend/app backend/tests` returns nothing.
