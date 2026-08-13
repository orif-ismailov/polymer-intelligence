# P9 — Requests / Pricing

> Prereq reading: `00-CONTEXT.md` (track goal, target convention, binding coupling findings),
> `P1-MARKETPLACE.md` (folder convention + import-alias technique), `P5-DEALS.md` (which hands
> two RFQ services to this phase), `P8-NEWS-REPORTS.md` (which hands nothing here but sets the
> "check by consumer, not by name" precedent). **P1–P8 must be merged and green before this phase
> starts.**

**Goal:** the buyer-request domain and the pricing domain move out of the technical-layer folders,
as **two separate folders**. Full gate green. No behavior change.

## What this phase carries

1. **Requests** — the big one. `models/requests.py` has **33 importing files**, second only to
   `models/companies.py` in P3.
2. **Pricing** — tiny and unrelated (3 files). Split into its own folder, same reasoning as P7.
3. ~~**The `analyze_request_ai` bug**~~ — **already fixed, ahead of this phase.** See
   `.planning/todos/done/analyze-request-ai-unregistered-on-worker.md`. This phase no longer
   carries it; the section below is kept as the record of what was done and what is still
   unverified.

## Scope decisions

### Pricing is its own domain, not part of requests

The roadmap groups "Requests/Pricing". They share nothing. `models/prices.py` has exactly two
references (the barrel and `public_market_service`); `price_analysis_service` compares a buyer's
target price to the latest `price_points` market average; `api/prices.py` is imported only by
`main.py`. `PricePoint` rows are fed by the CBU-rates and UZEX ingest pipelines (P10) and read by
pricing and `public_market_service`.

Three files, one clear job. `app/domains/pricing/`, its own commit. The only link to requests is
that `request_analysis_service` imports `price_analysis_service` — an ordinary cross-domain call.

### Arriving from P5: `rfq_push_service` + `supplier_matching_service`

P5 established that neither touches `models/deals.py` or `models/payments.py`. `rfq_push_service`
records that a supplier was told about an RFQ (`Company` + `RfqPushLog`); `supplier_matching_service`
reads `Request`, `SellerOffer`, `SellerOfferFile` and `Company` to rank push candidates. Both are
outbound actions on a buyer `Request`, driven by `app/tasks/rfq_push.py` and
`app/api/dashboard_requests.py`. They land here.

> `RfqPushLog` stays in `app/domains/marketplace/models.py`. Cross-domain read, tolerated. Do not
> re-open P1.

### `app/api/webapp/files.py` — included

Not in any roadmap line, but every one of its routes is request-scoped
(`/requests/{request_id}/files`, `/requests/{request_id}/files/{file_id}`) and it imports
`Client`, `Request`, `RequestFile`. It is request-attachment handling, not a generic file surface.
It moves with requests.

### `schemas/webapp.py` — moves, with two squatters

Despite the name, it is cohesively requests+client: `RequestCreate`, `RequestFileOut`,
`StatusHistoryOut`, `RequestOut`, `RequestDetailOut`, then `ClientProfileOut` and
`ClientProfilePatch`. Every importer is a requests or client file.

It moves whole to `app/domains/requests/webapp_schemas.py`. **The two `ClientProfile*` classes are
client-domain squatters** — consumed by `app/api/webapp/me.py`, which belongs with `client_service`
in P11. Moving them now would mean splitting a file to satisfy a domain that does not exist yet;
leaving them means the requests folder briefly hosts two client schemas. Take the second, and
**record it in P11's plan** so `client_service`'s phase extracts them rather than discovering them.

### `schemas/dashboard.py` — stays in `app/schemas/`, deliberately

This one does **not** move, and the reason is worth stating so nobody "finishes the job" later.
It holds response shapes for the entire internal dashboard across at least seven domains:
`FeedItem`/`FeedPage` (signals), `SourceCreate`/`SourceDetail`/`SourcePatch`/`SourceHealthItem`
/`SourceTestOut` (sources), `AlertRuleCreate`/`AlertRulePatch`/`AlertRuleOut`/`AlertOut` (alerts),
`PriceSeriesOut` (pricing), `StaffUserItem` (staff), `RequestListOut`/`RequestDetailOut`
/`RequestPatch`/`RequestFileOut`/`DashboardRequestItem` (requests), `DashboardOfferItem`
(marketplace), `DashboardKpis`.

Nine files import it: `admin_users`, `alert_rules`, `dashboard`, `dashboard_requests`, `feed`,
`prices`, `sources`, `dashboard_summary_service`, and a test. It is a **presentation layer for one
UI**, not any domain's contract. `00-CONTEXT.md` explicitly expects `app/schemas/` to keep
existing indefinitely, shrinking as domains move out — this is one of the things that should
remain. Splitting it per-domain risks circular imports between `dashboard.py` and several domain
schema modules for no navigability gain.

Extracting only the five request classes was considered and rejected: `dashboard_requests.py`
imports request shapes *and* `DashboardKpis` from the same module, so the split buys one clean
import and creates a second cross-module hop.

### Deferred to P11: the dashboard presentation layer

`dashboard_summary_service` is consumed by exactly one file, `app/api/dashboard.py`, and builds a
cross-domain KPI overview (buyers, sellers, active requests, hot leads, alert rules, recent
requests, recent offers). It is not a requests service. It belongs with `api/dashboard.py`,
`api/feed.py` and `schemas/dashboard.py` as a **dashboard grouping decided in P11** — either a
`dashboard` domain or explicit shared kernel. This plan only asserts it is not P9's.

## The `analyze_request_ai` fix — DONE (landed ahead of this phase)

`app/tasks/request_analysis.py` defines `analyze_request_ai` and `task_routes` routed it, but
`"app.tasks.request_analysis"` was **absent from `_TASK_MODULES`** and nothing imported it at
module level — so the worker could not resolve the message, with `REQUEST_AI_ANALYSIS_ENABLED`
defaulting `True`.

**This has been fixed** — `"app.tasks.request_analysis"` is in `_TASK_MODULES` and
`tests/test_celery_app.py` carries three guarding tests. Skip step 1 below; the phase is **two
commits, not three**. The reasoning is retained because the last bullet is still outstanding.

- **Its own commit.** Migration commits are behavior-free by this track's rule; this one starts a
  dead feature running. Bundling them makes the diff unreviewable and un-revertable
  independently.
- **Do it before the move, not after.** Landing it against the current paths keeps the fix small
  and reviewable on its own; doing it after means the reviewer reads a Celery fix and a 33-file
  import rewrite in the same window.
- **Add the registry test, not just the list entry.** Walk `_TASK_MODULES`, import each, and
  assert every `@celery_app.task(name=...)` under `app/tasks/*.py` appears in `celery_app.tasks`;
  cross-check `task_routes` keys against the registry too. The one-line fix leaves the class of
  bug live; the test closes it.
- **The feature has probably never executed.** Registering it means its first real run happens in
  production. Exercise it on staging — confirm `analyze_request_ai` produces a `requests.ai` block
  and that budget-exceeded and LLM-error paths degrade as `request_analysis_service` claims —
  before assuming "fixed" means "working".

## Files moving

### 1. pricing → `app/domains/pricing/` (do this first — 3 files, warms up the phase)

| From | To |
|---|---|
| `app/models/prices.py` | `app/domains/pricing/models.py` |
| `app/services/price_analysis_service.py` | `app/domains/pricing/analysis.py` |
| `app/api/prices.py` | `app/domains/pricing/api_admin.py` |

Call sites: `app/models/__init__.py` (barrel line 130), `app/services/public_market_service.py`,
`app/services/request_analysis_service.py`, `app/api/dashboard_requests.py`,
`tests/test_{price_analysis,dashboard_requests,request_analysis}.py`, plus `app/main.py:81`.
`api/prices.py` imports `schemas/dashboard.PriceSeriesOut`, which stays put — re-point nothing.

### 2. requests → `app/domains/requests/`

| From | To |
|---|---|
| `app/models/requests.py` | `app/domains/requests/models.py` |
| `app/schemas/portal_request.py` | `app/domains/requests/schemas.py` |
| `app/schemas/webapp.py` | `app/domains/requests/webapp_schemas.py` |
| `app/schemas/request_analysis.py` | `app/domains/requests/analysis_schemas.py` |
| `app/services/request_service.py` | `app/domains/requests/service.py` |
| `app/services/request_analysis_service.py` | `app/domains/requests/analysis.py` |
| `app/services/rfq_push_service.py` | `app/domains/requests/rfq_push.py` |
| `app/services/supplier_matching_service.py` | `app/domains/requests/supplier_matching.py` |
| `app/api/dashboard_requests.py` | `app/domains/requests/api_admin.py` |
| `app/api/portal/requests.py` | `app/domains/requests/api_portal.py` |
| `app/api/webapp/requests.py` | `app/domains/requests/api_webapp.py` |
| `app/api/webapp/files.py` | `app/domains/requests/api_webapp_files.py` |

## Call sites to update

Counts measured on the **pre-P1** tree. **Re-run the greps against the post-P8 tree before
starting** — P1–P8 will have relocated many of these.

- **`app.models.requests`** (33 files) — the bulk of the phase:
  - Barrel: `app/models/__init__.py` line 140.
  - Models: `app/models/marketplace.py` (→ marketplace after P1).
  - API: `app/api/{dashboard_requests,deps,sourcing}.py`, `app/api/portal/{deals,requests}.py`,
    `app/api/webapp/{files,market,me,news,reference,requests,seller}.py`.
    > **`app/api/deps.py` imports `models/requests`** — it is shared kernel and stays in
    > `app/api/`; only its import line changes. Do not follow it into the domain folder.
  - Services: `app/services/{alert_service,client_service,deal_service,offer_request_service,
    request_analysis_service,request_service,rfq_response_service,sourcing_service,
    storage_service,supplier_matching_service}.py`.
  - Tasks: `app/tasks/{notify,request_analysis,rfq_push}.py`.
  - Tests: `tests/_verification_db.py`, `tests/test_{dashboard_origin_badges_db,deal_service_db,
    portal_requests_api,request_serialization_golden,request_service_dual_origin_db}.py`.
- **`app.schemas.webapp`** (11 files): `app/services/request_service.py`,
  `app/schemas/portal_request.py` (moves too — internal import), `app/api/webapp/{requests,files,
  me}.py`, `app/api/portal/requests.py`, plus `tests/test_{request_service_dual_origin_db,
  dashboard_origin_badges_db,rfq_push,request_serialization_golden,request_service}.py`.
  `webapp/me.py` stays behind and keeps importing the two `ClientProfile*` classes across the new
  boundary — expected, see the scope note.
- **`app.schemas.portal_request`** (1 file): `app/api/portal/requests.py`.
- **`app.schemas.request_analysis`** (2 files): `app/services/request_analysis_service.py`,
  `tests/test_request_analysis.py`.
- **`request_service`** (12 files), **`request_analysis_service`** (4),
  **`rfq_push_service`** (3: `app/api/dashboard_requests.py`, `app/tasks/rfq_push.py`,
  `tests/test_rfq_push.py`), **`supplier_matching_service`** (3: `app/tasks/rfq_push.py`,
  `tests/test_{lab_market_db,supplier_matching}.py`) — mostly namespace-style, so the alias fix
  covers them.
- **Routers:** `app.api.dashboard_requests` → `app/main.py:56` **only** (no test importer);
  `app.api.portal.requests` → `app/main.py:78` + `tests/test_portal_requests_api.py`;
  `app.api.webapp.requests` → `app/main.py:93` + `tests/test_{request_sla,webapp_requests_api}.py`;
  `app.api.webapp.files` → `app/main.py:88`.
- **`app/tasks/request_analysis.py`** imports `analyze_request_ai`'s dependencies function-locally
  and `request_service.py:123` imports the task function-locally (`# noqa: PLC0415`). Both inner
  import lines change; the module stays in `app/tasks/`.

## Route checks — no misplaced routes, one prefix pattern to understand

Three webapp routers share a bare `/webapp` prefix — `requests`, `me`, and `files`:

| Router | Paths |
|---|---|
| `webapp/requests` | `/requests`, `/requests/{request_id}` |
| `webapp/files` | `/requests/{request_id}/files`, `/requests/{request_id}/files/{file_id}` |
| `webapp/me` | `/me` |

**No collisions.** `/requests/{request_id}` and `/requests/{request_id}/files` differ in depth, and
`/me` shares nothing. This is the same shape as `admin_licenses` in P6 — alarming-looking, benign
for the same reason (a path parameter does not match across a `/`). Include order at
`main.py:213-215` is irrelevant.

Both routers move into the same folder here, so the split stops being surprising. `webapp/me.py`
stays behind under the bare prefix until P11 takes `client_service`.

`dashboard_requests` (`/requests`), `portal/requests` (`/portal/requests`) and `prices`
(`/prices`) own uncontested prefixes.

## Steps

Two commits: **(b)** pricing, **(c)** requests. (Commit **(a)**, the Celery fix, already landed.)

1. ~~**Commit (a):** the Celery fix.~~ **Already landed** — start at step 2.
2. Re-run the grep inventory against the post-P8 tree.
3. **Commit (b) — pricing:** create `app/domains/pricing/__init__.py`, `git mv` the 3 files, fix
   internal imports, update the barrel line for `prices.py` (130), replace call sites, update
   `app/main.py:81`, update mypy config, full gate, commit.
4. **Commit (c) — requests:** create `app/domains/requests/__init__.py`, `git mv` the 12 files,
   fix internal imports (`schemas.py` → `webapp_schemas`, `analysis.py` → `analysis_schemas` and
   `app.domains.pricing.analysis`, `service.py` → `webapp_schemas`), update the barrel line for
   `requests.py` (140), replace call sites, update `app/main.py` lines 56, 78, 88, 93, update
   mypy config, full gate, commit.
5. Replacements for commit (c):
   - `app.models.requests` → `app.domains.requests.models`
   - `app.schemas.portal_request` → `app.domains.requests.schemas`
   - `app.schemas.webapp` → `app.domains.requests.webapp_schemas`
   - `app.schemas.request_analysis` → `app.domains.requests.analysis_schemas`
   - `app.services.request_service` → `app.domains.requests.service`
   - `app.services.request_analysis_service` → `app.domains.requests.analysis`
   - `app.services.rfq_push_service` → `app.domains.requests.rfq_push`
   - `app.services.supplier_matching_service` → `app.domains.requests.supplier_matching`
   - `app.api.dashboard_requests` → `app.domains.requests.api_admin`
   - `app.api.portal.requests` → `app.domains.requests.api_portal`
   - `app.api.webapp.requests` → `app.domains.requests.api_webapp`
   - `app.api.webapp.files` → `app.domains.requests.api_webapp_files`
   Split mixed `from app.services import (…)` blocks by hand — `dashboard_requests.py` imports
   `request_analysis_service`, `rfq_push_service` and `price_analysis_service` alongside
   shared-kernel names.
6. mypy: add `app/domains/pricing/analysis.py` and
   `app/domains/requests/{service,analysis,rfq_push,supplier_matching}.py` to the services check,
   and `app/domains/requests/{schemas,webapp_schemas,analysis_schemas}.py` to the schemas check —
   local commands + `.github/workflows/ci.yml` lines 75/78.
7. Full gate before each commit:
   - `cd backend && ruff check .`
   - `cd backend && mypy app/services app/domains/*/service.py app/domains/requests/{analysis,rfq_push,supplier_matching}.py app/domains/pricing/analysis.py app/domains/news/{dedup,reports}.py app/domains/lab_orders/samples.py app/domains/compliance/{substances,substance_ai,licenses}.py app/domains/deals/{escrow,rfq}.py app/domains/contracts/{render,eimzo}.py app/domains/companies/directory.py app/domains/verification/{checks,registry}.py app/domains/marketplace/{requests,compliance}.py --ignore-missing-imports`
   - `cd backend && mypy app/schemas app/domains/*/schemas.py app/domains/requests/{webapp_schemas,analysis_schemas}.py app/domains/compliance/{substance_schemas,substance_match_schemas}.py app/domains/contracts/eimzo_schemas.py --ignore-missing-imports`
   - `cd backend && pytest tests/ -q` (full suite, not a subset)

## Verification

- `ruff check .` — no new lint errors.
- Both `mypy` invocations — clean.
- `pytest tests/ -q` — full suite green. Highest-signal files:
  `test_request_serialization_golden.py`, `test_request_service.py`,
  `test_request_service_dual_origin_db.py`, `test_request_analysis.py`, `test_request_sla.py`,
  `test_webapp_requests_api.py`, `test_portal_requests_api.py`, `test_dashboard_requests.py`,
  `test_dashboard_origin_badges_db.py`, `test_rfq_push.py`, `test_supplier_matching.py`,
  `test_price_analysis.py`.
- **`test_request_serialization_golden.py` is a golden test.** Its pinned payload covers the
  `schemas/webapp.py` shapes this phase moves. A diff there means a field, alias or ordering
  changed — treat it as a hard stop, not a fixture to regenerate.
- **`app/api/dashboard_requests.py` has no test importer** — same gap as P6's two routers. It is
  the largest moving router (it wires `request_analysis_service`, `rfq_push_service` and
  `price_analysis_service`), so route-parity is the real gate for it.
- **Route-parity check:** compare `sorted((r.path, tuple(sorted(r.methods))) for r in app.routes)`
  before and after — byte-identical, after each of the three commits.
- **`Base.metadata` parity:** `sorted(Base.metadata.tables)` before and after — identical.
  `models/marketplace.py` holds an FK into `requests`.
- `uv run uvicorn app.main:app --reload` boots without import errors.
- `grep -rn "app\.models\.requests\|app\.models\.prices\|app\.schemas\.webapp\|app\.schemas\.portal_request\|app\.schemas\.request_analysis\|app\.services\.request_service\|app\.services\.request_analysis_service\|app\.services\.rfq_push_service\|app\.services\.supplier_matching_service\|app\.services\.price_analysis_service\|app\.api\.dashboard_requests\|app\.api\.prices\|app\.api\.portal\.requests\|app\.api\.webapp\.requests\|app\.api\.webapp\.files" backend/app backend/tests` returns nothing.
