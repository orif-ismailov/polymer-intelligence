# P6 — Compliance / Substances domain migration

> Prereq reading: `00-CONTEXT.md` (track goal, target convention, binding coupling findings),
> `P1-MARKETPLACE.md` (folder convention + import-alias technique; also the phase that owns
> `offer_compliance_service`, this domain's heaviest consumer), `P2-VERIFICATION.md`
> (`app/api/portal/deps.py`). **P1–P5 must be merged and green before this phase starts.**

**Goal:** `substance_service`, `substance_ai_service`, `company_license_service`,
`models/compliance.py`, `schemas/{compliance,substance,substance_match}.py`,
`api/admin_substances.py`, `api/admin_licenses.py`, `api/portal/substances.py`, and
`api/portal/compliance.py` move into `backend/app/domains/compliance/`. Every call site repo-wide
updated in the same change, full gate green. No behavior change.

## Size

**~25 unique files**, and unusually schema-heavy: three of the eleven moving files are schema
modules, and they form a small internal stack (`substance_match` → `substance`,
`compliance` → `substance`). Service reference counts are low —
`substance_service` 5, `company_license_service` 4, `substance_ai_service` 2.

## No misplaced routes in this phase — checked

P4 and P5 each had to relocate a route that lived in the wrong router and depended on
`main.py` include-order. **This phase does not.** All four routers were checked explicitly:

| Router | Prefix | Verdict |
|---|---|---|
| `admin_substances` | `/admin/substances` | `""` declared before `/{substance_id}` **within** the router — order is intra-file and already correct. |
| `portal/substances` | `/portal/substances` | Single `""` route. Nothing to collide with. |
| `portal/compliance` | `/portal/companies` | All four routes sit at `/{company_id}/…` depth or deeper — cannot shadow or be shadowed by `/{company_id}`. |
| `admin_licenses` | `/admin` | Declares `/companies/{company_id}/licenses` and `/licenses/{license_id}/revoke`. |

The `admin_licenses` case is the one that looks alarming and is not. It shares the bare `/admin`
prefix with `admin_verification` (P2), which declares `GET /admin/companies/{company_id}`,
`POST …/suspend` and `POST …/reinstate`. Those do **not** collide: a path parameter does not match
across a `/`, so `/{company_id}` cannot swallow `/{company_id}/licenses`, and `suspend` /
`reinstate` / `licenses` are distinct literals at the same depth. Include order (verification at
`main.py:260`, licenses at `:265`) is irrelevant here.

Worth recording anyway: **after P2 and P6, two domains own routes under `/admin/companies/`** —
verification owns the company lifecycle actions, compliance owns the licence sub-resource. That is
legitimate REST layering, not a leak. Do not "tidy" it into one router later; note it so nobody
tries.

## Scope decisions

- **`app/api/portal/compliance.py` — included, whole.** Three of its four routes are this domain's
  (`/{company_id}/licenses` → `company_license_service`, and both `/{company_id}/substance-
  suggestions…` routes → `substance_ai_service`). The fourth,
  `GET /{company_id}/offers/{offer_id}/compliance`, just reads a marketplace verdict via
  `offer_compliance_service.verdict_out`. Splitting one route out to marketplace is not worth a
  second router on the same prefix — move the file whole and keep the cross-domain call to
  `app.domains.marketplace.compliance`.
- **`offer_compliance_service` — stays in marketplace (P1).** It is this domain's heaviest
  consumer (it imports `models.compliance`, `schemas.compliance`, `schemas.substance`,
  `substance_service` and `company_license_service`), which makes it tempting to pull over. Don't:
  it owns the *offer* publish gate, sits in a deliberate import cycle with `offer_service`
  (function-local imports at `offer_service.py:492` and `:677`, both marked
  `# noqa: PLC0415 — cycle`), and moving it would drag that cycle across a domain boundary. A
  heavy consumer is not the same as an owner.
- **`app/integrations/chem_registry/` — stays put**, same rule as `app/ingest/` and the other
  integrations. Note its mode is read through `settings_service.get(db, "chem_registry_mode")`
  (a runtime app-setting declared in `settings_service._SPECS`), so there is **no** import cycle
  between the two despite both names appearing in each other's greps — `settings_service` only
  contains the setting's *string key*, not an import.
- **`app/seed/seed_substances.py` — stays put.** Seeders are their own layer; no phase moves one.
  Only its `app.models.compliance` import line changes.
- **No task module.** This domain has no entry in `_TASK_MODULES` and no beat schedule — nothing
  to touch in `app/tasks/`.

## Correction to `P1-MARKETPLACE.md`

P1 lists `app/integrations/chem_registry/client.py` as an `offer_compliance_service` call site.
**It is not.** The only occurrence in that file is prose in the module docstring
(`client.py:10`: "…adds a `LiveChemRegistryClient` here and `offer_compliance_service` does not…").
The file's sole `app.` import is `from app.services import settings_service`. P1's grep matched a
comment.

P1 has been amended. If P1 already shipped, no action is needed — the false entry costs a fruitless
search, not a broken build.

## Files moving

| From | To |
|---|---|
| `app/models/compliance.py` | `app/domains/compliance/models.py` |
| `app/schemas/compliance.py` | `app/domains/compliance/schemas.py` |
| `app/schemas/substance.py` | `app/domains/compliance/substance_schemas.py` |
| `app/schemas/substance_match.py` | `app/domains/compliance/substance_match_schemas.py` |
| `app/services/substance_service.py` | `app/domains/compliance/substances.py` |
| `app/services/substance_ai_service.py` | `app/domains/compliance/substance_ai.py` |
| `app/services/company_license_service.py` | `app/domains/compliance/licenses.py` |
| `app/api/admin_substances.py` | `app/domains/compliance/api_admin_substances.py` |
| `app/api/admin_licenses.py` | `app/domains/compliance/api_admin_licenses.py` |
| `app/api/portal/substances.py` | `app/domains/compliance/api_portal_substances.py` |
| `app/api/portal/compliance.py` | `app/domains/compliance/api_portal.py` |

## Call sites to update

Counts measured on the **pre-P1** tree. P1–P5 will have relocated several importers into
`app/domains/`. **Re-run the greps against the post-P5 tree before starting.**

- **`app.models.compliance`** (11 files): `app/models/__init__.py` (barrel, line 29 — update in
  place, keep FK-order position), `app/models/lab.py`, `app/models/marketplace.py`
  (→ `app/domains/marketplace/models.py` after P1), `app/seed/seed_substances.py`,
  `app/services/{company_license_service,offer_compliance_service,substance_ai_service,
  substance_service}.py`, `tests/test_{offer_compliance_gate_db,substance_ai,
  substance_registry_db}.py`.
  > `00-CONTEXT.md` names the `marketplace.py` ↔ `compliance.py` circular FK as tolerated. It
  > does not block the split — FK resolution is `Base.metadata`-based, not import-order-based —
  > but it is why the `Base.metadata` parity check below is not optional.
- **`app.schemas.compliance`** (5 files): `app/api/admin_licenses.py`,
  `app/api/portal/compliance.py`, `app/schemas/marketplace.py` (→ marketplace after P1),
  `app/schemas/portal_company.py` (→ `app/domains/companies/schemas.py` after P3),
  `app/services/offer_compliance_service.py`.
- **`app.schemas.substance`** (10 files): `app/api/{admin_substances}.py`,
  `app/api/portal/{compliance,substances}.py`, `app/schemas/{compliance,portal_company,
  substance_match}.py`, `app/services/{offer_compliance_service,substance_service}.py`,
  `tests/test_{substance_registry_db,substances_api}.py`. Two of these are **internal** to the
  moving set (`schemas/compliance.py`, `schemas/substance_match.py`) — fix those as internal
  imports in step 4, not as call sites.
- **`app.schemas.substance_match`** (3 files): `app/api/portal/compliance.py`,
  `app/services/substance_ai_service.py`, `tests/test_substance_ai.py`.
- **`substance_service`** (5 files): `app/api/admin_substances.py`,
  `app/api/portal/substances.py`, `app/services/{offer_compliance_service,substance_ai_service}.py`,
  `tests/test_substance_registry_db.py`.
- **`substance_ai_service`** (2 files): `app/api/portal/compliance.py`,
  `tests/test_substance_ai.py`.
- **`company_license_service`** (4 files): `app/api/admin_licenses.py`,
  `app/api/portal/compliance.py`, `app/services/offer_compliance_service.py`,
  `tests/test_offer_compliance_gate_db.py`.
- **Routers:** `app.api.admin_substances` → `app/main.py:49` + `tests/test_substances_api.py`;
  `app.api.admin_licenses` → `app/main.py:44` **only** (no test file imports it — see the gap
  below); `app.api.portal.substances` → `app/main.py:80` + `tests/test_substances_api.py`;
  `app.api.portal.compliance` → `app/main.py:64` **only**.
- **Shared-kernel splits:** `app/api/portal/compliance.py:30` is a mixed block —
  `company_license_service`, `offer_compliance_service`, `rate_limit`, `substance_ai_service`.
  `rate_limit` stays on `app.services`; `offer_compliance_service` becomes
  `from app.domains.marketplace import compliance as offer_compliance_service`; the other two
  become domain imports. **Split by hand.**
  Line 18's `from app.api.portal.companies import _company_or_404, _rate_limited` becomes the
  `app/api/portal/deps.py` public names from P2.

## Test-coverage gap worth knowing before you start

`app/api/admin_licenses.py` and `app/api/portal/compliance.py` are each imported by **`main.py`
only** — no test file imports either router. Their routes are exercised indirectly at best
(`test_offer_compliance_gate_db.py` drives `company_license_service` and
`offer_compliance_service` at the service layer, not through HTTP).

So for those two routers the full suite will **not** tell you if the move broke request wiring —
an import typo surfaces at app construction, but a mis-registered route or a changed
`response_model` would pass. The route-parity check below is the real gate here, not `pytest`.
Do not skip it on the grounds that the suite is green.

## Steps

1. Re-run the grep inventory against the post-P5 tree.
2. Create `app/domains/compliance/__init__.py`.
3. `git mv` the 11 files to their new paths (preserves history).
4. Fix internal imports within the moved set — the schema stack first
   (`substance_match_schemas` → `substance_schemas`, `schemas` → `substance_schemas`), then the
   services (`substances`, `substance_ai`, `licenses` → `models`, and `substance_ai` →
   `substance_match_schemas`), then the four routers.
5. Update the `app/models/__init__.py` barrel line for `compliance.py` (29), preserving FK-order
   position. `__all__` entries (`CompanyLicense`, `Substance`, `SubstanceSuggestion`) are
   name-only — no edit.
6. Replace call sites:
   - `app.models.compliance` → `app.domains.compliance.models`
   - `app.schemas.compliance` → `app.domains.compliance.schemas`
   - `app.schemas.substance` → `app.domains.compliance.substance_schemas`
   - `app.schemas.substance_match` → `app.domains.compliance.substance_match_schemas`
   - `app.services.substance_service` → `app.domains.compliance.substances`
   - `app.services.substance_ai_service` → `app.domains.compliance.substance_ai`
   - `app.services.company_license_service` → `app.domains.compliance.licenses`
   - `app.api.admin_substances` → `app.domains.compliance.api_admin_substances`
   - `app.api.admin_licenses` → `app.domains.compliance.api_admin_licenses`
   - `app.api.portal.substances` → `app.domains.compliance.api_portal_substances`
   - `app.api.portal.compliance` → `app.domains.compliance.api_portal`
   Then split the mixed `from app.services import (…)` blocks by hand and alias.
7. Update `app/main.py` import lines 44, 49, 64, 80. Leave every `include_router` call where it is.
8. Update `backend/pyproject.toml` mypy overrides (the `app.domains.*` blocks from P2 — verify
   present) and the mypy invocations, local + `.github/workflows/ci.yml` lines 75/78, adding
   `app/domains/compliance/{substances,substance_ai,licenses}.py` to the services check and
   `app/domains/compliance/{schemas,substance_schemas,substance_match_schemas}.py` to the schemas
   check.
9. Run the full gate and fix anything red:
   - `cd backend && ruff check .`
   - `cd backend && mypy app/services app/domains/*/service.py app/domains/compliance/{substances,substance_ai,licenses}.py app/domains/deals/{escrow,rfq}.py app/domains/contracts/{render,eimzo}.py app/domains/companies/directory.py app/domains/verification/{checks,registry}.py app/domains/marketplace/{requests,compliance}.py --ignore-missing-imports`
   - `cd backend && mypy app/schemas app/domains/*/schemas.py app/domains/compliance/{substance_schemas,substance_match_schemas}.py app/domains/contracts/eimzo_schemas.py --ignore-missing-imports`
   - `cd backend && pytest tests/ -q` (full suite, not a subset)
10. Commit once everything is green.

## Verification

- **Test integrity — see `00-CONTEXT.md` § "Test integrity across the migration".** Green is not
  enough: capture the baseline (`pytest --collect-only` count + passed/skipped/deselected) before
  starting, re-run the gate after **each step** rather than only before the commit, and confirm
  all four numbers are **identical** afterwards. A dropped collected count or a risen skip count
  is a regression even though pytest prints it in green. Sweep the `patch("app...")` target
  strings — they are invisible to ruff, mypy and every import tool — and change import *paths*
  only, never import *style*, or a patch can silently stop applying and leave a test passing
  vacuously.
- `ruff check .` — no new lint errors.
- Both `mypy` invocations — clean.
- `pytest tests/ -q` — full suite green. Highest-signal files: `test_substance_registry_db.py`,
  `test_substances_api.py`, `test_substance_ai.py`, `test_offer_compliance_gate_db.py`,
  `test_offer_compliance_verdicts.py`, `test_chem_registry_client.py`.
- **Route-parity check — load-bearing this phase**, not a formality: compare
  `sorted((r.path, tuple(sorted(r.methods))) for r in app.routes)` before and after, byte-identical.
  Two of the four moving routers have no test coverage at all (see the gap above), so parity is the
  only thing standing between a wiring mistake and production. Extend it to compare
  `response_model` per route if that is cheap in this codebase.
- **`Base.metadata` parity:** `sorted(Base.metadata.tables)` before and after — identical.
  `models/compliance.py` sits in a known circular FK with `models/marketplace.py` and is
  additionally imported by `models/lab.py`; a dropped barrel line surfaces here before alembic.
- `uv run uvicorn app.main:app --reload` boots without import errors.
- `grep -rn "app\.models\.compliance\|app\.schemas\.compliance\|app\.schemas\.substance\|app\.schemas\.substance_match\|app\.services\.substance_\|app\.services\.company_license_service\|app\.api\.admin_substances\|app\.api\.admin_licenses\|app\.api\.portal\.substances\|app\.api\.portal\.compliance" backend/app backend/tests` returns nothing.
