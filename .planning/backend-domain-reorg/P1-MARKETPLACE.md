# P1 — Marketplace/offers domain migration

> Prereq reading: `00-CONTEXT.md` (track goal, target convention, binding coupling findings).

**Goal:** `offer_service`, `offer_request_service`, `offer_compliance_service`,
`models/marketplace.py`, `schemas/marketplace.py`, `schemas/portal_market.py` and **all seven
marketplace routers** (`portal/offers`, `offer_requests`, `moderation`, `portal/market`,
`portal/inquiries`, `webapp/market`, `webapp/seller`) move into
`backend/app/domains/marketplace/`, every call site repo-wide updated in the same change, full
gate green, one commit. No behavior change.

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
| `app/api/moderation.py` | `app/domains/marketplace/api_admin_moderation.py` |
| `app/api/portal/market.py` | `app/domains/marketplace/api_portal_market.py` |
| `app/api/portal/inquiries.py` | `app/domains/marketplace/api_portal_inquiries.py` |
| `app/api/webapp/market.py` | `app/domains/marketplace/api_webapp_market.py` |
| `app/api/webapp/seller.py` | `app/domains/marketplace/api_webapp_seller.py` |
| `app/schemas/portal_market.py` | `app/domains/marketplace/portal_market_schemas.py` |

### The five extra routers (added while planning P11)

The first draft of this plan moved two routers and listed the five below as *call sites* — files
whose imports get rewritten in place. That would have left five marketplace surfaces in
`app/api/` after the pilot phase, so "find everything about offers" would still mean visiting two
directories, which is the exact problem this track exists to fix. Every one of them imports this
domain's models and schemas and nothing else domain-shaped:

| Router | Prefix | Marketplace imports |
|---|---|---|
| `app/api/moderation.py` | `/admin/moderation` | `SellerOffer`, `schemas.marketplace`, `offer_service`, `offer_compliance_service` |
| `app/api/portal/market.py` | `/portal/market` | `SellerOffer`, `schemas.portal_market` |
| `app/api/portal/inquiries.py` | `/portal` | `OfferRequest`, `SellerOffer`, `schemas.marketplace`, `schemas.portal_market` |
| `app/api/webapp/market.py` | `/webapp/market` | `SellerOfferFile`, `schemas.marketplace` |
| `app/api/webapp/seller.py` | `/webapp/seller` | `Seller`, `SellerOffer`, `SellerOfferFile`, `schemas.marketplace` |

`app/schemas/portal_market.py` comes with them — its only importers are `portal/market.py` and
`portal/inquiries.py`, both of which move.

> **`portal/market.py` has load-bearing intra-file route order.** Its routes are declared
> `""` (54), `/favorites` (115), `/offers/{offer_id}/favorite` (128, 147),
> `/companies/{company_id}` (164) and finally `/{offer_id}` (225). The catch-all param route is
> last **on purpose** — declared any earlier it would swallow `/favorites`, `/offers/…` and
> `/companies/…`. `git mv` preserves this; a tidy-up during the move (grouping or sorting routes)
> breaks it silently, with no import error and no obvious test failure. Move the file
> byte-for-byte apart from its import block.

> **Two of these import P2's shared portal helpers.** `portal/market.py:18` has
> `from app.api.portal.companies import _company_or_404`, and `portal/inquiries.py:20` has
> `_company_or_404, _rate_limited, _require_business_role`. P2 extracts those into
> `app/api/portal/deps.py` under public names. **P1 runs first**, so at this point they still
> import from `app.api.portal.companies` — leave that import path alone here; P2 re-points it
> along with the other nine siblings. Do not pre-empt the extraction.


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
- **`app/main.py`** — **seven** import lines, path only. `include_router(...)` calls are
  **all unchanged**, and none of them may be reordered:
  | Line | Import |
  |---|---|
  | 61 | `from app.api.offer_requests import router as offer_requests_router` |
  | 76 | `from app.api.portal.offers import router as portal_offers_router` |
  | 60 | `from app.api.moderation import router as moderation_router` |
  | 73 | `from app.api.portal.market import router as portal_market_router` |
  | 68 | `from app.api.portal.inquiries import router as portal_inquiries_router` |
  | 89 | `from app.api.webapp.market import router as webapp_market_router` |
  | 94 | `from app.api.webapp.seller import router as webapp_seller_router` |

  (`include_router` sites, for reference only — do not touch: 217 webapp_seller, 218
  webapp_market, 220 moderation, 221 offer_requests, 246 portal_offers, 247 portal_market,
  256 portal_inquiries.)
- **Test importers of the five extra routers**: `app.api.portal.market` →
  `tests/test_{portal_market_api,offer_sale_fields}.py`; `app.api.portal.inquiries` →
  `tests/test_portal_inquiries_api.py`; `app.api.webapp.market` →
  `tests/test_{marketplace_api,portal_company_logo_api}.py`; `app.api.webapp.seller` →
  `tests/test_marketplace_api.py`; `app.api.moderation` → **`app/main.py` only, no test
  importer** — route-parity is the only guard for that one.
- **`app.schemas.portal_market`** (4 files): `app/api/portal/{market,inquiries}.py` (both move —
  fix as internal imports, not call sites), `tests/test_{lab_market_db,offer_sale_fields}.py`.
- Any `from app.services import offer_service` / `offer_request_service` /
  `offer_compliance_service` (submodule-namespace style, found in step below) — alias on import:
  `from app.domains.marketplace import service as offer_service`, etc., so `offer_service.foo()`
  call sites don't need editing.

## Steps

1. Create `app/domains/__init__.py` and `app/domains/marketplace/__init__.py`.
2. `git mv` the 13 files above to their new paths (preserves history). **Do not reorder anything
   inside them** — see the `portal/market.py` note above.
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
   - `app.api.moderation` → `app.domains.marketplace.api_admin_moderation`
   - `app.api.portal.market` → `app.domains.marketplace.api_portal_market`
   - `app.api.portal.inquiries` → `app.domains.marketplace.api_portal_inquiries`
   - `app.api.webapp.market` → `app.domains.marketplace.api_webapp_market`
   - `app.api.webapp.seller` → `app.domains.marketplace.api_webapp_seller`
   - `app.schemas.portal_market` → `app.domains.marketplace.portal_market_schemas`
   Apply the submodule-alias fix for any `from app.services import X` style hits found.
6. Update all **seven** `app/main.py` router import lines (60, 61, 68, 73, 76, 89, 94) to their
   new paths. Leave every `include_router(...)` call exactly where it is.
7. Update `backend/pyproject.toml` mypy overrides and the CI `mypy` invocations (local commands
   + `.github/workflows/ci.yml`) to add
   `app/domains/marketplace/service.py app/domains/marketplace/requests.py app/domains/marketplace/compliance.py`
   to the services check and `app/domains/marketplace/schemas.py app/domains/marketplace/portal_market_schemas.py`
   to the schemas check.
8. Confirm old file locations are gone (handled by `git mv`).
9. Run the full gate and fix anything red:
   - `cd backend && ruff check .`
   - `cd backend && mypy app/services app/domains/marketplace/service.py app/domains/marketplace/requests.py app/domains/marketplace/compliance.py --ignore-missing-imports`
   - `cd backend && mypy app/schemas app/domains/marketplace/schemas.py --ignore-missing-imports`
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
- Both `mypy` invocations above — clean.
- `pytest tests/ -q` — full suite green, in particular the marketplace-touching tests:
  `test_marketplace_api.py`, `test_offer_requests.py`, `test_offer_compliance_gate_db.py`,
  `test_offer_compliance_verdicts.py`, `test_moderation_race_db.py`, `test_portal_offers_api.py`,
  `test_portal_offer_photos_api.py`, `test_seller_offer_edit.py`, `test_catalog_search.py`,
  `test_dual_origin_offers.py`, `test_sourcing.py`, `test_lab_market_db.py`.
- `uv run uvicorn app.main:app --reload` boots without import errors (router wiring resolves).
- `grep -rn "app\.models\.marketplace\|app\.schemas\.marketplace\|app\.schemas\.portal_market\|app\.services\.offer_\|app\.api\.moderation\|app\.api\.offer_requests\|app\.api\.portal\.\(offers\|market\|inquiries\)\|app\.api\.webapp\.\(market\|seller\)" backend/app backend/tests` returns nothing — no stale import path survived.
- **Route-order check** (new, because of `portal/market.py`): confirm
  `GET /api/v1/portal/market/favorites` resolves to the favorites handler and **not** to the
  `/{offer_id}` handler with `offer_id="favorites"`. Route-parity compares the route *set* and
  cannot see a reordering.
- **`app/api/portal/` and `app/api/webapp/` each lose two files** here. After this phase
  `app/api/` should hold no module importing `SellerOffer` or `schemas.marketplace`; grep to
  confirm.
