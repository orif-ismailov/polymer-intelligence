# P7 — Lab orders / Laboratory / Logistics / Manufacturers

> Prereq reading: `00-CONTEXT.md` (track goal, target convention, binding coupling findings),
> `P1-MARKETPLACE.md` (folder convention + import-alias technique), `P2-VERIFICATION.md`
> (`app/api/portal/deps.py`), `P3-COMPANIES.md` (`directory_service`, which
> `manufacturer_service` delegates to). **P1–P6 must be merged and green before this phase
> starts.**

**Goal:** `lab_service`, `sample_service`, `laboratory_service`, `logistics_service`,
`manufacturer_service` and their models/schemas/routers move out of the technical-layer folders.
Full gate green. No behavior change.

## This is not one domain — it is four

`00-CONTEXT.md` groups these five services into a single phase. Reading the code, **they are four
mutually disjoint bounded contexts.** No file appears in two groups, and at the service layer
none of the four imports any other:

| Group | Models | Schemas | Services | Routers |
|---|---|---|---|---|
| **lab orders** | `lab.py` | `lab.py` | `lab_service`, `sample_service` | `admin_lab`, `portal/lab`, `portal/samples` |
| **laboratory** | `laboratory.py` | `portal_laboratory.py` | `laboratory_service` | `admin_lab_requests`, `portal/lab_requests` |
| **logistics** | `logistics.py` | `portal_logistics.py` | `logistics_service` | `admin_logistics_requests`, `portal/logistics` |
| **manufacturers** | `manufacturers.py` | `portal_manufacturers.py` | `manufacturer_service` | `portal/manufacturers` |

`laboratory_service`, `logistics_service` and `manufacturer_service` each import exactly:
`accounts`, `companies`, `enums`, their own model, and `company_service`/`storage_service`
(plus `directory_service` for manufacturers). They do not know about each other, and none of them
touches `models/lab.py`.

**The `lab` / `laboratory` distinction is load-bearing and the codebase already defends it.**
`models/laboratory.py`'s docstring says, in bold: *"**Not `lab_orders`.** That table (P6,
migration 0028) is a different thing and stays untouched: staff-driven, hung off an offer or a
deal, worked by partner labs."* They are genuinely different flows — `lab.py` is staff-driven lab
orders and physical samples against an offer or deal; `laboratory.py` is a buyer broadcasting an
analysis request to every verified laboratory, each of which opens its own thread.

Collapsing both into one `app/domains/lab*/` folder would destroy exactly the distinction the
code goes out of its way to protect, in the name of a reorg whose entire purpose is
navigability. Don't.

### Recommendation: four folders, four commits

```
app/domains/lab_orders/       # models/lab.py       — NOT "lab", see naming note
app/domains/laboratory/
app/domains/logistics/
app/domains/manufacturers/
```

**Naming.** The folder for `models/lab.py` is `lab_orders`, not `lab`. `app/domains/lab/` and
`app/domains/laboratory/` as siblings would be the single most confusing pair of directory names
in the codebase, and `lab_orders` is the name the other module's docstring already uses for it.

**Four commits, not one.** The groups are disjoint, so each is independently atomic and
gate-green — which honors `00-CONTEXT.md`'s "each domain move is atomic" rule *better* than one
40-file commit would. Suggested order, cheapest-risk first:

1. **logistics** — 5 files, fully self-contained `/portal/logistics` prefix, no cross-domain
   reach beyond `companies`. The pilot for the sub-phase pattern.
2. **laboratory** — 5 files, structurally identical to logistics (`requests` / `pool` /
   `threads` / messages / file). Doing logistics first makes this one mechanical.
3. **manufacturers** — 4 files, same shape plus the intra-router ordering gotcha below.
4. **lab orders** — 7 files, the largest and the only group with real cross-domain reach
   (`deals`, `marketplace`, `staff`).

If you would rather keep it to one commit, the plan still works — but take the four folders
regardless. The folder split is the recommendation; the commit split is the convenience.

## Route checks — no misplaced routes, but one real gotcha

All five portal routers were checked. **No route lives in the wrong router this phase** (unlike
P4 and P5), and no cross-router include-order dependency exists:

- `portal/lab` (`/portal/companies`) — routes are `/{company_id}/lab-orders…`, a segment deeper
  than `/{company_id}` and a distinct literal from companies' own `/{company_id}/documents`,
  `/roles`, `/bank-accounts`. Cannot be shadowed.
- `portal/samples` (`/portal`) — `/companies/{company_id}/samples`,
  `/market/offers/{offer_id}/samples`, `/samples/{sample_id}/transition`. The middle one lives
  under `/portal/market/` but at three segments deep; `portal/market`'s `/{offer_id}` is one
  segment. No overlap.
- `portal/lab_requests` (`/portal/lab`), `portal/logistics` (`/portal/logistics`),
  `portal/manufacturers` (`/portal/manufacturers`) — self-contained prefixes owned by nothing
  else.

> Two `main.py` comments are **stronger than the facts require**: the one at line 241 ("Lab orders
> hang off /portal/companies/{id}/lab-orders — same reason again") and the one at line 248
> ("Manufacturers before any catch-all company/id routes that could shadow list paths"). Neither
> router can actually be shadowed — the first is a segment deeper, the second has its own prefix.
> **Leave both comments alone.** They are harmless, and deleting a caution you have merely proven
> unnecessary *today* invites someone to reintroduce the real problem later. Only P4's comment was
> deleted, and only because that fix made it factually dead.

### The gotcha: `portal/manufacturers.py` intra-file declaration order is load-bearing

Within that one router:

```
line 180  POST "/rfqs"
line 199  GET  "/rfqs/{rfq_id}"
...
line 398  POST "/{manufacturer_id}/threads"
line 432  POST "/{manufacturer_id}/rfqs"
```

`/rfqs/{rfq_id}` and `/{manufacturer_id}/rfqs` overlap: the path
`/portal/manufacturers/rfqs/rfqs` matches both. It resolves correctly only because the literal
`/rfqs…` routes are **declared before** the `/{manufacturer_id}…` routes in the file.

A whole-file `git mv` preserves this automatically. The risk is a well-meant tidy-up during the
move — grouping routes by resource, sorting them, or splitting the file — which would break it
**silently**, with no import error and no obvious test failure. Move the file byte-for-byte apart
from its import block, and do not reorder route declarations.

## Test coverage — good this phase

Unlike P6 (where two routers had no test importer at all), every group here has real coverage,
and `tests/test_portal_manufacturers_api.py` drives the routes over HTTP through the app
(`client.get(_BASE, …)`), so it exercises actual route registration rather than the service layer
alone:

| Group | Tests |
|---|---|
| lab orders | `test_lab_api.py`, `test_lab_service.py`, `test_lab_service_db.py`, `test_lab_schema_db.py`, `test_lab_notify.py`, `test_lab_market_db.py`, `test_samples_api.py`, `test_sample_service.py`, `test_sample_service_db.py` |
| laboratory | `test_portal_lab_requests_api.py` (also imports `app.api.admin_lab_requests`) |
| logistics | `test_portal_logistics_api.py` (also imports `app.api.admin_logistics_requests`) |
| manufacturers | `test_portal_manufacturers_api.py` |

The route-parity check is still required, but here the suite is genuine backup rather than the
false comfort it would be in P6.

## Files moving

### 1. logistics → `app/domains/logistics/`

| From | To |
|---|---|
| `app/models/logistics.py` | `app/domains/logistics/models.py` |
| `app/schemas/portal_logistics.py` | `app/domains/logistics/schemas.py` |
| `app/services/logistics_service.py` | `app/domains/logistics/service.py` |
| `app/api/admin_logistics_requests.py` | `app/domains/logistics/api_admin.py` |
| `app/api/portal/logistics.py` | `app/domains/logistics/api_portal.py` |

Call sites: `app/models/__init__.py` (barrel line 108), `app/api/public.py`,
`tests/test_portal_logistics_api.py`, `tests/test_public_api.py`, plus `app/main.py` lines 45
and 71.

### 2. laboratory → `app/domains/laboratory/`

| From | To |
|---|---|
| `app/models/laboratory.py` | `app/domains/laboratory/models.py` |
| `app/schemas/portal_laboratory.py` | `app/domains/laboratory/schemas.py` |
| `app/services/laboratory_service.py` | `app/domains/laboratory/service.py` |
| `app/api/admin_lab_requests.py` | `app/domains/laboratory/api_admin.py` |
| `app/api/portal/lab_requests.py` | `app/domains/laboratory/api_portal.py` |

Call sites: `app/models/__init__.py` (barrel line 103), `app/api/public.py`,
`tests/test_portal_lab_requests_api.py`, plus `app/main.py` lines 43 and 70.

### 3. manufacturers → `app/domains/manufacturers/`

| From | To |
|---|---|
| `app/models/manufacturers.py` | `app/domains/manufacturers/models.py` |
| `app/schemas/portal_manufacturers.py` | `app/domains/manufacturers/schemas.py` |
| `app/services/manufacturer_service.py` | `app/domains/manufacturers/service.py` |
| `app/api/portal/manufacturers.py` | `app/domains/manufacturers/api_portal.py` |

Call sites: `app/models/__init__.py` (barrel line 113), `app/api/public.py`,
`tests/test_portal_manufacturers_api.py`, plus `app/main.py` line 72. No admin router.

> `manufacturer_service` imports `directory_service` — after P3 that is
> `app.domains.companies.directory`, which `list_manufacturers` delegates to. Re-point it; the
> delegation is deliberate (it is what stops the manufacturers page and the other three
> directories answering the same question differently). Do not inline it back.

### 4. lab orders → `app/domains/lab_orders/`

| From | To |
|---|---|
| `app/models/lab.py` | `app/domains/lab_orders/models.py` |
| `app/schemas/lab.py` | `app/domains/lab_orders/schemas.py` |
| `app/services/lab_service.py` | `app/domains/lab_orders/service.py` |
| `app/services/sample_service.py` | `app/domains/lab_orders/samples.py` |
| `app/api/admin_lab.py` | `app/domains/lab_orders/api_admin.py` |
| `app/api/portal/lab.py` | `app/domains/lab_orders/api_portal.py` |
| `app/api/portal/samples.py` | `app/domains/lab_orders/api_portal_samples.py` |

Call sites: `app/models/__init__.py` (barrel line 102), `app/api/portal/offers.py`
(→ `app/domains/marketplace/api_portal.py` after P1, imports `lab_service`),
`app/tasks/notify.py`, plus 9 test files and `app/main.py` lines 42, 69, 79.

Cross-domain reach to expect and accept: `lab_service` imports `deals` (P5), `marketplace` (P1),
`staff` (shared kernel) and `companies` (P3); `sample_service` imports `marketplace` and
`companies`. A lab order hangs off an offer or a deal by design — this is the domain doing its
job, not leakage.

## Steps (repeat per group)

1. Re-run the grep inventory for the group against the current tree.
2. Create `app/domains/<group>/__init__.py`.
3. `git mv` that group's files. **Do not reorder anything inside them** — see the manufacturers
   gotcha.
4. Fix internal imports within the moved files.
5. Update the group's `app/models/__init__.py` barrel line, preserving FK-order position.
   `__all__` entries are name-only — no edit.
6. Replace call sites (`app.models.<x>` → `app.domains.<group>.models`, `app.schemas.<x>` →
   `…schemas`, `app.services.<x>_service` → `…service`, routers → `…api_admin` / `…api_portal`).
   Split any mixed `from app.services import (…)` block by hand — `storage_service` and
   `company_service` sit next to the moving names in all five services.
7. Update that group's `app/main.py` import lines. Leave every `include_router` call where it is.
8. Update `backend/pyproject.toml` mypy overrides (the `app.domains.*` blocks from P2 — verify
   present) and the mypy invocations, local + `.github/workflows/ci.yml` lines 75/78, adding the
   group's service and schema files.
9. Run the full gate:
   - `cd backend && ruff check .`
   - `cd backend && mypy app/services app/domains/*/service.py app/domains/lab_orders/samples.py app/domains/compliance/{substances,substance_ai,licenses}.py app/domains/deals/{escrow,rfq}.py app/domains/contracts/{render,eimzo}.py app/domains/companies/directory.py app/domains/verification/{checks,registry}.py app/domains/marketplace/{requests,compliance}.py --ignore-missing-imports`
   - `cd backend && mypy app/schemas app/domains/*/schemas.py app/domains/compliance/{substance_schemas,substance_match_schemas}.py app/domains/contracts/eimzo_schemas.py --ignore-missing-imports`
   - `cd backend && pytest tests/ -q` (full suite, not a subset)
10. Commit that group. Then move to the next.

## Verification (per group, and once at the end)

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
- `pytest tests/ -q` — full suite green. Per-group signal files are in the coverage table above.
- **Route-parity check:** compare `sorted((r.path, tuple(sorted(r.methods))) for r in app.routes)`
  before and after — byte-identical.
- **Route-*order* check — specific to this phase.** Parity compares the route *set* and will not
  notice a reordering. After the manufacturers group, additionally assert that
  `POST /api/v1/portal/manufacturers/rfqs` resolves to the RFQ-create handler and **not** to the
  `/{manufacturer_id}/rfqs` handler with `manufacturer_id="rfqs"`. Cheapest form: compare the
  ordered list of `(path, name)` for routes under `/portal/manufacturers` before and after.
- **`Base.metadata` parity:** `sorted(Base.metadata.tables)` before and after — identical, after
  each group.
- `uv run uvicorn app.main:app --reload` boots without import errors.
- Final sweep, once all four groups have landed:
  `grep -rn "app\.models\.\(lab\|laboratory\|logistics\|manufacturers\)\b\|app\.schemas\.\(lab\|portal_laboratory\|portal_logistics\|portal_manufacturers\)\b\|app\.services\.\(lab_service\|sample_service\|laboratory_service\|logistics_service\|manufacturer_service\)\b\|app\.api\.\(admin_lab\|admin_lab_requests\|admin_logistics_requests\)\b\|app\.api\.portal\.\(lab\|lab_requests\|logistics\|manufacturers\|samples\)\b" backend/app backend/tests`
  returns nothing.
