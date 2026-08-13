# P1 — Marketplace/offers domain migration

> Prereq reading: `00-CONTEXT.md` (track goal, target convention, binding coupling findings).

**Goal:** `offer_service`, `offer_request_service`, `offer_compliance_service`,
`models/marketplace.py`, `schemas/marketplace.py`, `api/portal/offers.py`,
`api/offer_requests.py` move into `backend/app/domains/marketplace/`, every call site
repo-wide updated in the same change, full gate green, one commit. No behavior change.

## Files moving

| From | To |
|---|---|
| `app/models/marketplace.py` | `app/domains/marketplace/models.py` |
| `app/schemas/marketplace.py` | `app/domains/marketplace/schemas.py` |
| `app/services/offer_service.py` | `app/domains/marketplace/service.py` |
| `app/services/offer_request_service.py` | `app/domains/marketplace/requests.py` |
| `app/services/offer_compliance_service.py` | `app/domains/marketplace/compliance.py` |
| `app/api/portal/offers.py` | `app/domains/marketplace/api_portal.py` |
| `app/api/offer_requests.py` | `app/domains/marketplace/api_admin.py` |

## Call sites to update (confirmed via repo-wide grep, `app/` + `tests/`)

- **`app.models.marketplace`** (~30 files): `app/models/__init__.py` (barrel — update in place,
  keep FK-order position), `app/api/{moderation,offer_requests}.py`,
  `app/api/portal/{compliance,inquiries,lab,manufacturers,market,offers}.py`,
  `app/api/webapp/{market,seller}.py`, `app/schemas/{portal_company,portal_market,public}.py`,
  `app/seed/seed_showcase_{docs,media,photos}.py`, `app/services/{deal_service,lab_service,
  manufacturer_service,offer_compliance_service,offer_request_service,offer_service,
  public_market_service,rfq_push_service,sample_service,sourcing_service,storage_service,
  supplier_matching_service}.py`, `app/tasks/{notify,verification}.py`, plus ~20 test files:
  `tests/test_{catalog_search,dashboard_origin_badges_db,deal_contract_link_db,
  deal_notifications_db,deal_service_db,dual_origin_offers,lab_api,lab_market_db,
  lab_schema_db,lab_service_db,marketplace_api,migration_0028,moderation_race_db,
  offer_compliance_gate_db,offer_request_dual_origin_db,offer_requests,offer_sale_fields,
  portal_inquiries_api,portal_market_api,portal_offer_photos_api,portal_offers_api,
  rfq_push,seller_offer_edit,sourcing}.py`, `tests/_verification_db.py`,
  `tests/test_admin_verification_api.py`.
- **`offer_service`** (~20 files): `app/api/{moderation,public}.py`,
  `app/api/portal/{manufacturers,market,offers,samples}.py`, `app/api/webapp/{market,seller}.py`,
  `app/services/public_market_service.py`, plus 10 `tests/test_*` files (catalog_search,
  client_session_auth, lab_market_db, marketplace_api, moderation_race_db,
  offer_compliance_gate_db, offer_moderation_telegram, portal_offer_photos_api,
  seller_offer_edit, notification_routing_matrix_db).
- **`offer_request_service`** (~7 files): `app/api/offer_requests.py`,
  `app/api/portal/{inquiries,market}.py`, `app/api/webapp/market.py`, plus 6 test files
  (dashboard_origin_badges_db, marketplace_api, moderation_race_db,
  offer_request_dual_origin_db, offer_requests, portal_inquiries_api, portal_market_api).
- **`offer_compliance_service`** (~4 files): `app/api/moderation.py`,
  `app/api/portal/compliance.py`, `app/services/offer_service.py`, plus 2 test files
  (offer_compliance_gate_db, offer_compliance_verdicts). Note `offer_service.py` imports it
  **function-locally** at lines 492 and 677 (`# noqa: PLC0415 — cycle`) — an intentional cycle
  between the two, which stays intra-domain after this move.
  > Corrected while planning P6: `app/integrations/chem_registry/client.py` was listed here and
  > is **not** a call site. Its only occurrence of the name is prose in the module docstring
  > (line 10); its sole `app.` import is `from app.services import settings_service`. Nothing to
  > change in that file.
- **`app.schemas.marketplace`**: `app/schemas/{compliance,portal_company,portal_market,
  public}.py` plus the API/service files above that also import schemas.
- **`app/main.py`** lines 61, 76: `from app.api.offer_requests import router as
  offer_requests_router`, `from app.api.portal.offers import router as portal_offers_router` —
  path only; `include_router(...)` calls at lines 221/246 unchanged.
- Any `from app.services import offer_service` / `offer_request_service` /
  `offer_compliance_service` (submodule-namespace style, found in step below) — alias on import:
  `from app.domains.marketplace import service as offer_service`, etc., so `offer_service.foo()`
  call sites don't need editing.

## Steps

1. Create `app/domains/__init__.py` and `app/domains/marketplace/__init__.py`.
2. `git mv` the 7 files above to their new paths (preserves history).
3. Fix internal imports within the moved files (e.g. `offer_service.py` importing
   `offer_compliance_service` becomes `app.domains.marketplace.compliance`).
4. Update the `app/models/__init__.py` barrel line for `marketplace.py`, preserving its current
   position in the FK-ordered import list.
5. Grep-and-replace every call site listed above:
   - `app.models.marketplace` → `app.domains.marketplace.models`
   - `app.schemas.marketplace` → `app.domains.marketplace.schemas`
   - `app.services.offer_service` → `app.domains.marketplace.service`
   - `app.services.offer_request_service` → `app.domains.marketplace.requests`
   - `app.services.offer_compliance_service` → `app.domains.marketplace.compliance`
   - `app.api.portal.offers` → `app.domains.marketplace.api_portal`
   - `app.api.offer_requests` → `app.domains.marketplace.api_admin`
   Apply the submodule-alias fix for any `from app.services import X` style hits found.
6. Update `app/main.py` router import lines (61, 76) to the new `api_admin`/`api_portal` paths.
7. Update `backend/pyproject.toml` mypy overrides and the CI `mypy` invocations (local commands
   + `.github/workflows/ci.yml`) to add
   `app/domains/marketplace/service.py app/domains/marketplace/requests.py app/domains/marketplace/compliance.py`
   to the services check and `app/domains/marketplace/schemas.py` to the schemas check.
8. Confirm old file locations are gone (handled by `git mv`).
9. Run the full gate and fix anything red:
   - `cd backend && ruff check .`
   - `cd backend && mypy app/services app/domains/marketplace/service.py app/domains/marketplace/requests.py app/domains/marketplace/compliance.py --ignore-missing-imports`
   - `cd backend && mypy app/schemas app/domains/marketplace/schemas.py --ignore-missing-imports`
   - `cd backend && pytest tests/ -q` (full suite, not a subset)
10. Commit once everything is green.

## Verification

- `ruff check .` — no new lint errors.
- Both `mypy` invocations above — clean.
- `pytest tests/ -q` — full suite green, in particular the marketplace-touching tests:
  `test_marketplace_api.py`, `test_offer_requests.py`, `test_offer_compliance_gate_db.py`,
  `test_offer_compliance_verdicts.py`, `test_moderation_race_db.py`, `test_portal_offers_api.py`,
  `test_portal_offer_photos_api.py`, `test_seller_offer_edit.py`, `test_catalog_search.py`,
  `test_dual_origin_offers.py`, `test_sourcing.py`, `test_lab_market_db.py`.
- `uv run uvicorn app.main:app --reload` boots without import errors (router wiring resolves).
- `grep -rn "app\.models\.marketplace\|app\.schemas\.marketplace\|app\.services\.offer_" backend/app backend/tests` returns nothing — no stale import path survived.
