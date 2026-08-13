# Backend domain reorg — context

**Track:** reorganize `backend/app/` from technical layers (`app/models/`, `app/services/`,
`app/schemas/`, `app/api/`) into bounded-context domain folders (`app/domains/<name>/`), one
domain at a time, tests green after every domain.

## Why

The backend has ~15 business domains (marketplace, verification, contracts, deals, escrow, lab,
news, ...) flattened across four top-level technical-layer folders (34 model files, 47 service
files, 24 schema files, ~60 router files). Finding "everything about contracts" means jumping
across four directories, each with a dozen-plus unrelated siblings — this was raised as a growing
navigability problem as the codebase has grown past the original signal-pipeline scope into
marketplace, verification/portal, contracts, deals, escrow, labs, and news tracks.

CQRS was considered and rejected: it separates read/write, not domains — irrelevant to
navigability and would add indirection on top of the existing problem. Full tactical DDD
(repository pattern abstracting SQLAlchemy, domain entities split from ORM models, event
sourcing) was also rejected: the service layer already functions as a reasonable application
layer over sufficiently rich ORM models (state machines, actor-rule tables per domain already
document real invariants), and there's no persistence-swap or test-isolation need to justify a
repository abstraction. What's adopted is DDD's **strategic** pattern only — group each bounded
context's models/schemas/service/api together — nothing tactical.

## Findings from the coupling research (binding for every phase)

- ~1800 `app.services.X` / `app.models.X` / `app.schemas.X` / `app.api.X` import references
  repo-wide (`app/` + `tests/`), all literal strings — mechanical (grep+sed), not a logic
  rewrite, but real volume per domain.
- `app/models/__init__.py` is a genuine barrel (imports every model in FK order, feeds
  `Base.metadata` for alembic). Moving a model file just means updating its barrel line in
  place, preserving relative order — SQLAlchemy resolves FKs from `Base.metadata` after all
  models load, not from Python import order, so this is safe.
- `app/services/__init__.py`, `app/schemas/__init__.py`, `app/api/__init__.py` are empty — no
  existing re-export shim to lean on. **No backward-compat shims are added during this
  migration** — each domain move is atomic: move the files, update every call site (`app/` +
  `tests/`) in the same change, get the full gate green, then commit. Leaving old-path shim
  files would recreate the "why does this exist in two places" confusion the reorg exists to
  fix.
- A `from app.services import offer_service` (submodule-as-namespace) style is used ~62 times
  repo-wide, with call sites doing `offer_service.foo(...)`. Fix by aliasing the import
  (`from app.domains.marketplace import service as offer_service`) so call sites don't need
  touching — only the import line changes.
- CI runs two explicit directory-path mypy invocations: `mypy app/services --ignore-missing-imports`
  and `mypy app/schemas --ignore-missing-imports` (plus matching `[[tool.mypy.overrides]]` blocks
  in `backend/pyproject.toml` keyed by `app.services.*` / `app.schemas.*`). Each phase must add
  its new domain's service/schema files to these invocations (both the local command and
  `.github/workflows/ci.yml`) as part of that phase's change.
- Circular FKs exist between `companies.py`↔`verification.py` and `marketplace.py`↔`compliance.py`
  models. This does not block a folder split (FK resolution is metadata-based, not
  import-order-based) — it's accepted as a tolerated two-way relationship between those domain
  pairs, not something to solve.
- Full test suite (`pytest tests/ -q`, not a subset), `ruff check .`, and both `mypy` invocations
  must be green before every commit in this track — same standing rule as the rest of the repo.

## Target convention

Each domain becomes `backend/app/domains/<name>/`, e.g.:
```
app/domains/marketplace/
  __init__.py
  models.py      # was app/models/marketplace.py
  schemas.py     # was app/schemas/marketplace.py
  service.py     # was app/services/offer_service.py
  compliance.py  # was app/services/offer_compliance_service.py (kept as its own file)
  requests.py    # was app/services/offer_request_service.py
  api_portal.py  # was app/api/portal/offers.py
  api_admin.py   # was app/api/offer_requests.py
```
Sub-files stay separate where the source was already meaningfully split — the goal is one
**folder** per domain, not one file per domain.

The **shared kernel** (`audit_service`, `event_service`/`event_types`, `notification_service`,
`storage_service`, `settings_service`, `app/api/deps.py`, `app/core/security.py`) stays in
`app/services/` / `app/api/` / `app/core/` — it is genuinely cross-cutting infra imported by
nearly every domain, and is not moved by this track. `app/services/` and `app/schemas/` keep
existing indefinitely, shrinking as more domains move out.

## Phase roadmap

Ordered by lowest external fan-in / least shared-kernel entanglement first (from the coupling
research), confirmed with the user:

1. **Marketplace/offers** — `P1-MARKETPLACE.md`. Lowest external fan-in of the two initial
   candidates (marketplace vs. verification) — no other domain's *services* reach into
   marketplace, only `offer_compliance_service` reaches out to substances/compliance. Pilot:
   establishes the folder convention, the import-alias technique, and the CI-glob pattern reused
   by every later phase.
2. **Verification** — `verification_service`, `verification_checks`, `registry_service`,
   `otp_service`, `directory_service` + `models/verification.py`. More entangled: contracts'
   `eimzo_service` depends on it, circular FK with companies.
3. **Companies** — `company_service` + `models/companies.py`. Highest fan-in (8 other domains
   depend on it) — moved once several dependents already exist as domains, so "update every call
   site" happens once at scale.
4. **Contracts** — `contract_service`, `contract_render`, `eimzo_service`.
5. **Deals/Escrow/RFQ** — `deal_service`, `escrow_service`, `rfq_response_service`,
   `rfq_push_service`, `supplier_matching_service`.
6. **Compliance/Substances** — `substance_service`, `substance_ai_service`,
   `company_license_service`.
7. **Lab/Logistics/Manufacturers** — `lab_service`, `laboratory_service`, `logistics_service`,
   `manufacturer_service`, `sample_service`.
8. **News/Reports** — `news_service`, `news_dedup`, `report_service`, `ai_signal_service`,
   `relevance_service`, `grade_service`.
9. **Requests/Pricing** — `request_service`, `request_analysis_service`, `price_analysis_service`,
   `dashboard_summary_service`.
10. **Signals/Ingest** — `signal_service`, `raw_pipeline`, `source_service`,
    `source_health_service`, `sourcing_service` (`app/ingest/` adapter package already has its
    own per-type structure and is left as-is).
11. Remaining small isolated services (`alert_service`, `auth_service`, `client_service`,
    `fx_service`, `lead_score_recompute_service`, `rate_limit`, `review_service`,
    `userbot_health_service`, `product_service`) grouped into 2-3 small domains at the end.

Each phase gets its own `P<N>-<NAME>.md` in this directory, written just before that phase
starts — not drafted all up front, so later plans don't drift from the codebase before they're
executed. Plain hand-written Markdown; no GSD tooling (removed from this project).
