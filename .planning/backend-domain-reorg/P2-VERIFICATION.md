# P2 — Verification domain migration

> Prereq reading: `00-CONTEXT.md` (track goal, target convention, binding coupling findings)
> and `P1-MARKETPLACE.md` (the pilot that established the folder convention, the import-alias
> technique, and the CI-glob pattern this phase reuses). **P1 must be merged and green before
> this phase starts.**

**Goal:** `verification_service`, `verification_checks`, `registry_service`,
`models/verification.py`, `models/registry.py`, `api/admin_verification.py`, plus the
verification-owned slice of `api/portal/companies.py` and `schemas/portal_company.py`, move into
`backend/app/domains/verification/`. Every call site repo-wide updated in the same change, full
gate green, one commit. No behavior change.

## Scope decisions (deviations from the `00-CONTEXT.md` roadmap line)

The roadmap sketch for this phase listed five services. Reading the code, two of them do not
belong to this bounded context and are moved out of P2's scope:

- **`otp_service` — excluded.** Its docstring is explicit: *"Passwordless SMS-OTP auth for portal
  accounts"*. It rate-limits phone codes and upserts `user_accounts`; it never touches
  `VerificationCase`/`VerificationCheck`/`Company`. It is **account authentication**, not company
  verification — the two only share the word "verify". Its natural home is an `accounts`/`auth`
  domain in the P11 leftovers grouping (alongside `auth_service`, `client_service`, `rate_limit`).
  Pulling it in here would put portal login inside the company-verification folder and mislead
  every future reader.
- **`directory_service` — deferred to P3.** Its docstring: *"Public company directories, keyed by
  confirmed business role."* It queries `Company` by `CompanyBusinessRole`, and
  `manufacturer_service.list_manufacturers` delegates to it. It reads a *result* of verification
  (confirmed roles) but it is a **companies** query service. Moving it with `models/companies.py`
  in P3 keeps it next to the model it queries.
- **`models/registry.py` — added.** Not in the roadmap line, but `registry_service` is the only
  writer of `RegistrySnapshot` and `admin_verification.py` is the only other reader. Leaving the
  model behind in `app/models/` would split a two-file unit across the old and new layouts for no
  reason.

If you disagree with either exclusion, change it here before starting — not mid-phase.

## Files moving

| From | To |
|---|---|
| `app/models/verification.py` | `app/domains/verification/models.py` |
| `app/models/registry.py` | `app/domains/verification/registry_models.py` |
| `app/services/verification_service.py` | `app/domains/verification/service.py` |
| `app/services/verification_checks.py` | `app/domains/verification/checks.py` |
| `app/services/registry_service.py` | `app/domains/verification/registry.py` |
| `app/api/admin_verification.py` | `app/domains/verification/api_admin.py` |
| *(new, extracted — see below)* | `app/domains/verification/api_portal.py` |
| *(new, extracted — see below)* | `app/domains/verification/schemas.py` |

### The two extractions

`app/api/portal/companies.py` (720 lines) and `app/schemas/portal_company.py` each straddle two
domains. P2 takes the verification slice; P3 takes the rest.

**From `app/api/portal/companies.py` → `app/domains/verification/api_portal.py`:**

| Route | Line (current) |
|---|---|
| `POST /{company_id}/documents` | 610 |
| `GET /{company_id}/documents/{document_id}/download` | 644 |
| `DELETE /{company_id}/documents/{document_id}` | 657 |
| `POST /{company_id}/verification/submit` | 686 |
| `GET /{company_id}/verification` | 705 |

plus the helpers only these routes use: `_check_out` (103), `_case_out` (108), `_latest_case`
(126), `_document_or_404` (672).

**From `app/schemas/portal_company.py` → `app/domains/verification/schemas.py`:**
`CheckOut` (293), `CaseOut` (299), `DocumentOut` (321).

> `_case_out` is also imported by one sibling router (`from app.api.portal.companies import
> _case_out, _company_or_404`) — after the move that import re-points to
> `app.domains.verification.api_portal`. Confirm the current importer with
> `grep -rn "_case_out" backend/app` before wiring.

### Route-ordering safety (read before splitting the router)

`app/main.py` lines 234–244 carry explicit comments about portal router include-order: literal
paths like `/portal/companies/directory` must be registered before the companies router's
`/portal/companies/{company_id}` param route. **The five extracted routes are not affected** —
they all sit one segment deeper (`/{company_id}/documents…`, `/{company_id}/verification…`) and
cannot shadow or be shadowed by `/{company_id}`. Give the new router the same
`APIRouter(prefix="/portal/companies", tags=["portal-verification"])` and include it adjacent to
`portal_companies_router`. Do **not** reorder any existing `include_router` call.

### Step 0 — extract the shared portal helpers first

`app/api/portal/companies.py` is a de-facto shared kernel: **11 sibling routers** import private
helpers from it —

```
_company_or_404          app/api/portal/{compliance,eimzo,inquiries,lab,lab_requests,
_rate_limited            logistics,manufacturers,market,offers,requests,samples}.py
_require_business_role
_case_out
```

If these stay where they are, the new `api_portal.py` must import private helpers from a
*companies* module, and after P3 eleven unrelated domains would import private helpers from
`app.domains.companies.api_portal`. Fix it once, here:

1. Create `app/api/portal/deps.py` (shared kernel — same status as `app/api/deps.py`, stays out
   of `app/domains/` permanently).
2. Move `_rate_limited` (59), `_company_or_404` (70), `_require_business_role` (77),
   `_require_company_admin` (91) into it, renamed without the leading underscore
   (`rate_limited`, `company_or_404`, `require_business_role`, `require_company_admin`) — they are
   now a public shared surface, and ruff should not be the only thing telling you that.
3. Re-point all 11 sibling routers + `companies.py` itself to the new module.
4. `_case_out` does **not** go to `deps.py` — it is verification-owned and moves to
   `api_portal.py` in this phase.

This is a mechanical, behavior-free change. Land it as the **first commit of the phase**, gate
green, before any `git mv` — so that if the domain move needs backing out, the deps extraction
(useful on its own) survives.

## Call sites to update (confirmed via repo-wide grep, `app/` + `tests/`)

- **`app.models.verification`** (19 files): `app/models/__init__.py` (barrel, line 146 — update in
  place, keep FK-order position), `app/api/admin_verification.py`, `app/api/portal/companies.py`,
  `app/services/{company_service,eimzo_service,storage_service,verification_checks,
  verification_service}.py`, `app/tasks/{notify,verification}.py`, plus 9 test files:
  `tests/test_{admin_verification_api,company_service_db,eimzo_service_db,
  registry_verification_db,verification_checks,verification_document_vault,verification_handler,
  verification_service_db,verification_tasks}.py`.
- **`app.models.registry`** (7 files): `app/models/__init__.py` (barrel, line 138),
  `app/api/admin_verification.py`, `app/services/registry_service.py`,
  `app/tasks/verification.py`, `tests/test_{migration_0029,registry_service_db,
  registry_verification_db}.py`.
- **`verification_service`** (13 files, both import styles): `app/tasks/verification.py`,
  `app/services/eimzo_service.py`, `app/api/portal/companies.py`,
  `app/api/admin_verification.py`, plus `tests/test_{admin_verification_api,portal_companies_api,
  portal_eimzo_api,eimzo_service_db,registry_verification_db,verification_service_db}.py` and the
  `_verification_db.py` helper. Re-verify with the grep in step 5 — this module is imported both
  as `app.services.verification_service` and via `from app.services import (…)` blocks.
- **`verification_checks`** (4 files): `app/tasks/verification.py`,
  `app/api/admin_verification.py`, `tests/test_{verification_checks,registry_checks}.py`.
- **`registry_service`** (3 files): `app/tasks/verification.py`,
  `app/api/admin_verification.py`, `tests/test_registry_service_db.py`. Note: **zero**
  `app.services.registry_service` full-path hits — every call site uses the
  `from app.services import registry_service` namespace style, so the alias fix covers all of them.
- **`app.api.admin_verification`** (3 files): `app/main.py` line 51,
  `tests/test_{admin_verification_api,registry_verification_db}.py`.
- **`app/main.py`**: line 51 (`admin_verification` import path) and line 63 area — add the new
  `portal_verification_router` import + its `include_router(..., prefix="/api/v1")` call next to
  line 244. Line 260's `include_router(admin_verification_router, …)` is unchanged apart from
  where the name is imported from.
- **Submodule-namespace style** (`from app.services import verification_service` etc., with call
  sites doing `verification_service.foo(...)`): alias on import so call sites stay untouched —
  `from app.domains.verification import service as verification_service`,
  `… import checks as verification_checks`, `… import registry as registry_service`. Note that
  `app/api/admin_verification.py` and `app/api/portal/companies.py` import these inside multi-name
  `from app.services import (…)` parenthesised blocks — those blocks must be **split**, not
  sed-replaced: the shared-kernel names (`audit_service`, `storage_service`) stay on the
  `app.services` line, the moved ones become separate aliased imports.

## Known cross-domain reach — promote `_open_case_for` here

`verification_service._open_case_for` is a **private** function with three callers, two of them
across what become domain boundaries:

| Caller | Domain | Phase that moves it |
|---|---|---|
| `app/services/verification_service.py:158` | verification (internal) | — |
| `app/api/portal/companies.py:136` (inside `_summary_out`) | companies | **P3** |
| `app/services/eimzo_service.py:153` | contracts | **P4** |

**Decision: promote it in this phase.** Rename to a public `open_case_for` in
`app/domains/verification/service.py` and update all three call sites as part of the move.

The reasoning: P2 owns the definition, and P2 is the phase that *creates* the boundary the other
two will cross. Deferring means P3 and P4 each move a call site that reaches into another
domain's privates, and whichever of them eventually does the rename touches verification's
internals from outside its own phase. A three-call-site rename inside the folder that owns the
function is smaller and lands in the right place.

> An earlier draft of this plan deferred this to P4 on the basis of two callers. That grep missed
> `portal/companies.py:136` — P3 crosses the boundary first. Corrected here.

Likewise `eimzo_service.py:201` does a function-local `from app.tasks.verification import
_run_check` (task-layer glue, already `# noqa: PLC0415`). `app/tasks/` is **not** moved by this
track — the Celery topology (`_TASK_MODULES` in `celery_app.py`, the `verify` queue routing) stays
exactly as-is. Only the imports *inside* `app/tasks/verification.py` change.

## mypy configuration — the gap P1's plan does not cover

`backend/pyproject.toml` has `[[tool.mypy.overrides]] module = ["app.services.*"]` setting
`disallow_untyped_defs = true` **and `disallow_any_explicit = true`**. Global `[tool.mypy]` is
`strict = true`, which already implies `disallow_untyped_defs` — but **`disallow_any_explicit` is
not part of `strict`**. So a service file moved to `app/domains/…` silently loses the
explicit-`Any` ban unless a matching override is added.

P1's step 7 updates the mypy *invocation paths* but not the *override module keys*. This phase
must do both, and should retro-fix P1's blocks if that landed without them:

```toml
[[tool.mypy.overrides]]
module = ["app.domains.*"]
disallow_untyped_defs = true
disallow_any_explicit = true

[[tool.mypy.overrides]]
# Same pydantic carve-out as app.schemas.* — see that block's comment.
module = ["app.domains.*.schemas"]
disallow_any_explicit = false
```

Order matters: mypy applies the **last** matching override, so the `*.schemas` block must come
after the general `app.domains.*` block.

## Steps

1. **Commit 1 (prep):** create `app/api/portal/deps.py`, move the four shared helpers out of
   `app/api/portal/companies.py`, re-point the 11 sibling routers. Full gate green, commit.
2. Create `app/domains/verification/__init__.py`.
3. `git mv` the 6 whole files to their new paths (preserves history).
4. Extract the 5 routes + 4 helpers into `app/domains/verification/api_portal.py`, and the 3
   schema classes into `app/domains/verification/schemas.py`. These two are hand-carved, not
   `git mv` — history for the extracted lines is not preserved, which is accepted.
5. Fix internal imports within the moved files (`verification_service` ↔ `verification_checks`,
   `registry_service` → `registry_models`, `api_admin` → all three services).
6. Rename `_open_case_for` → `open_case_for` in `app/domains/verification/service.py` and update
   its three callers (the internal one at `service.py:158`, `app/api/portal/companies.py:136`,
   `app/services/eimzo_service.py:153`). Confirm with
   `grep -rn "_open_case_for" backend/app backend/tests` returning nothing.
7. Update the `app/models/__init__.py` barrel lines for `verification.py` (146) and `registry.py`
   (138), preserving their positions in the FK-ordered list. The `__all__` entries
   (`VerificationCase`, `VerificationCheck`, `VerificationDocument`, `RegistrySnapshot`) are
   name-only and need no edit.
8. Grep-and-replace every call site:
   - `app.models.verification` → `app.domains.verification.models`
   - `app.models.registry` → `app.domains.verification.registry_models`
   - `app.services.verification_service` → `app.domains.verification.service`
   - `app.services.verification_checks` → `app.domains.verification.checks`
   - `app.services.registry_service` → `app.domains.verification.registry`
   - `app.api.admin_verification` → `app.domains.verification.api_admin`
   Then handle the `from app.services import (…)` blocks by hand (split + alias, per above).
9. Update `app/main.py`: line 51 import path; add the portal-verification router import and its
   `include_router` call. **Do not reorder existing includes.**
10. Update `backend/pyproject.toml` mypy overrides (the `app.domains.*` blocks above) **and** the
   mypy invocations — local commands + `.github/workflows/ci.yml` lines 75 and 78 — adding
   `app/domains/verification/{service,checks,registry}.py` to the services check and
   `app/domains/verification/schemas.py` to the schemas check.
11. Run the full gate and fix anything red:
    - `cd backend && ruff check .`
    - `cd backend && mypy app/services app/domains/marketplace/*.py app/domains/verification/{service,checks,registry}.py --ignore-missing-imports`
    - `cd backend && mypy app/schemas app/domains/marketplace/schemas.py app/domains/verification/schemas.py --ignore-missing-imports`
    - `cd backend && pytest tests/ -q` (full suite, not a subset)
12. **Commit 2 (the move)** once everything is green.

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
- `pytest tests/ -q` — full suite green, in particular:
  `test_verification_service_db.py`, `test_verification_checks.py`, `test_verification_tasks.py`,
  `test_verification_handler.py`, `test_verification_notify.py`,
  `test_verification_document_vault.py`, `test_admin_verification_api.py`,
  `test_registry_service_db.py`, `test_registry_verification_db.py`, `test_registry_checks.py`,
  `test_migration_0029.py`, `test_eimzo_service_db.py`, `test_portal_companies_api.py`,
  `test_portal_eimzo_api.py`.
- `uv run uvicorn app.main:app --reload` boots without import errors.
- **Route-parity check** (the split router's real risk): compare
  `sorted((r.path, tuple(sorted(r.methods))) for r in app.routes)` before and after — it must be
  byte-identical. A silently dropped or shadowed route is the one failure mode the test suite
  might not catch.
- `grep -rn "app\.models\.verification\|app\.models\.registry\|app\.services\.verification_\|app\.services\.registry_service\|app\.api\.admin_verification" backend/app backend/tests` returns nothing.
- `grep -rn "from app.api.portal.companies import _" backend/app` returns nothing — all private
  cross-router imports are gone.
