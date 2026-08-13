# P5 — Deals / Escrow / RFQ-response domain migration

> Prereq reading: `00-CONTEXT.md` (track goal, target convention, binding coupling findings),
> `P1-MARKETPLACE.md` (folder convention + import-alias technique), `P2-VERIFICATION.md`
> (`app/api/portal/deps.py`), `P4-CONTRACTS.md` (the misplaced-route fix this phase repeats).
> **P1–P4 must be merged and green before this phase starts.**

**Goal:** `deal_service`, `escrow_service`, `rfq_response_service`, `models/deals.py`,
`models/payments.py`, `schemas/portal_deal.py`, `api/admin_deals.py`, `api/admin_escrow.py`,
`api/portal/deals.py`, and `api/webhooks_escrow.py` move into `backend/app/domains/deals/`. Every
call site repo-wide updated in the same change, full gate green. One structural fix travels with
it (below); otherwise no behavior change.

## Size

**~35 unique files.** Between P4 (~20) and P3 (76). The weight is concentrated in tests —
`deal_service` alone has 23 referencing files, 14 of them `tests/test_{deal,escrow}_*`. The
escrow state machine and the deal state machine each have dedicated transition tests
(`test_deal_transitions.py`, `test_escrow_transitions.py`) that do not touch the DB; those are
the fastest signal if an import rewrite breaks an enum path.

## Scope decisions (deviations from the `00-CONTEXT.md` roadmap line)

The roadmap listed five services for this phase. **Two of them do not belong here** — neither
touches `models/deals.py` or `models/payments.py` at all:

- **`rfq_push_service` — moves to P9 (Requests).** It imports exactly two models:
  `models/companies.Company` and `models/marketplace.RfqPushLog`. Its job is "record that a
  supplier was told about an RFQ, exactly once" — outbound bookkeeping on a buyer `Request`. Its
  consumers are `app/tasks/rfq_push.py` and `app/api/dashboard_requests.py`, which is the requests
  surface.
- **`supplier_matching_service` — moves to P9 (Requests).** It reads `Request`, `SellerOffer`,
  `SellerOfferFile`, and `Company` to build a ranked candidate set for an RFQ push. No deal, no
  payment, no `RfqResponse`. It is a requests→marketplace matcher.

  > Note both write/read `RfqPushLog`, which lives in `models/marketplace.py` and is therefore
  > already `app/domains/marketplace/models.py` after P1. That stays where it is — a cross-domain
  > read from P9, tolerated exactly like the others. Do **not** re-open P1 to relocate it.

- **`rfq_response_service` — stays in P5.** Unlike the two above, it owns `RfqResponse` (declared
  in `models/deals.py`) and its docstring is explicit that "acceptance itself lives in
  `deal_service`". Supplier quotes against an RFQ are the front half of the deal lifecycle.
- **`models/counterparties.py` — excluded, and flagged.** It has exactly **one** reference in the
  entire repo: the `app/models/__init__.py` barrel line. The `counterparties` table is real
  (created in `0001_initial_schema`, seeded via raw SQL in `seed_showcase.py`) and the FK lives on
  `signals.counterparty_id` (`models/signals.py:100`) — it is **signals entity resolution**, not a
  deals concern. It belongs to **P10 (Signals/Ingest)**.

  > Separately worth knowing: the `Counterparty` / `CounterpartyAlias` ORM classes have **no Python
  > consumers** — every read/write in the codebase goes through raw SQL or the `signals` FK. That
  > may be intentional (the model docstring says linking is "resolved by a background process"
  > that may not exist yet) or it may be dead ORM. Don't decide it here; note it for P10.

- **`app/integrations/escrow/` — stays put**, same rule as `app/ingest/` and
  `app/integrations/eimzo/` in P4.
- **`app/tasks/{deals,payments,rfq_push}.py` — stay put.** `app/tasks/` is not moved by this
  track. All three import only `celery_app`, `event_types`, and enums at module level and do the
  rest function-locally, so the edits are small and inner.

## The structural fix: `GET /portal/market/requests`

`app/api/portal/deals.py:717` defines `GET /market/requests` on a router prefixed `/portal`.
`app/api/portal/market.py:224` defines `GET /{offer_id}` on a router prefixed `/portal/market`.
Those are **the same path depth**: `/api/v1/portal/market/requests` matches both.

It resolves correctly today for one reason only — `app/main.py` includes `portal_deals_router`
(line 237) before `portal_market_router` (line 247). **This ordering dependency is undocumented.**
`main.py` carries explicit comments for the contracts/directory case, the deals-under-companies
case, the lab case and the manufacturers case, but says nothing about this one. It is the same
class of landmine P4 removed, minus the warning sign.

If it stays: P5 parks `/portal/market/requests` inside `app/domains/deals/api_portal.py`, and the
route silently depends on a deals router being registered before a marketplace router in a file
that mentions neither fact. Reorder the includes for any unrelated reason and
`GET /portal/market/requests` starts resolving to `get_offer(offer_id="requests")` → a 422 on a
route that used to work.

**Do this instead:** move `list_market_requests` and its `MarketRequestListOut` schema into
`app/domains/marketplace/api_portal.py` (P1's output), declared **above** the `/{offer_id}` route.
Within-router declaration order settles it with no include-order dependency at all.

The cost is a cross-domain import: the marketplace portal router will import
`rfq_response_service` (→ `app.domains.deals.rfq`) and `RfqResponse`. That is a normal
domain-to-domain call, and it is a better trade than an invisible ordering constraint. The path is
unchanged, so the route-parity check still holds.

> If that trade is rejected, the fallback is to leave the route in deals and **add the missing
> comment to `main.py`** next to the three that already exist. That is strictly worse — it
> documents the fragility rather than removing it — but it is much better than today, where
> nothing records the constraint at all. Do not leave this phase having done neither.

## Files moving

| From | To |
|---|---|
| `app/models/deals.py` | `app/domains/deals/models.py` |
| `app/models/payments.py` | `app/domains/deals/payment_models.py` |
| `app/schemas/portal_deal.py` | `app/domains/deals/schemas.py` |
| `app/services/deal_service.py` | `app/domains/deals/service.py` |
| `app/services/escrow_service.py` | `app/domains/deals/escrow.py` |
| `app/services/rfq_response_service.py` | `app/domains/deals/rfq.py` |
| `app/api/admin_deals.py` | `app/domains/deals/api_admin.py` |
| `app/api/admin_escrow.py` | `app/domains/deals/api_admin_escrow.py` |
| `app/api/portal/deals.py` *(minus `list_market_requests`)* | `app/domains/deals/api_portal.py` |
| `app/api/webhooks_escrow.py` | `app/domains/deals/api_webhooks.py` |

## Call sites to update

Counts measured on the **pre-P1** tree. P1–P4 will have relocated several importers into
`app/domains/`. **Re-run the greps against the post-P4 tree before starting** — this section is
the map, not the coordinates.

- **`app.models.deals`** (24 files): `app/models/__init__.py` (barrel, line 40 — update in place,
  keep FK-order position), `app/api/{admin_deals,admin_escrow}.py`,
  `app/api/portal/{deals,lab}.py`, `app/services/{deal_service,escrow_service,lab_service,
  rfq_response_service}.py`, `app/tasks/{notify,payments}.py`, plus 13 test files:
  `tests/test_{admin_deals_api,admin_escrow_api,deal_contract_link_db,deal_service_db,
  escrow_consumer_db,escrow_notifications_db,escrow_provider_events_db,escrow_reconcile_db,
  escrow_service_db,escrow_webhook_api,lab_service_db,portal_deals_api,
  rfq_response_service_db}.py`.
- **`app.models.payments`** (11 files): `app/models/__init__.py` (barrel, line 129),
  `app/api/admin_escrow.py`, `app/services/escrow_service.py`, `app/tasks/payments.py`, plus 7
  escrow test files.
- **`app.schemas.portal_deal`** (1 file): `app/api/portal/deals.py`. The
  `MarketRequestListOut` class inside it travels to marketplace with its route (see the fix
  above) — everything else moves whole.
- **`deal_service`** (23 files): `app/api/{admin_deals,admin_escrow,admin_lab}.py`,
  `app/api/portal/deals.py`, `app/services/{escrow_service,lab_service,rfq_response_service}.py`,
  `app/tasks/deals.py`, plus 14 test files. Note `rfq_response_service.py:37` imports **exception
  classes** by path — `from app.services.deal_service import CompanyNotVerified, ResponseNotOpen`
  — a plain path swap, no alias needed.
- **`escrow_service`** (12 files): `app/api/{admin_escrow,webhooks_escrow}.py`,
  `app/api/portal/deals.py`, `app/tasks/payments.py`, plus 8 test files.
- **`rfq_response_service`** (3 files): `app/api/portal/deals.py`,
  `tests/test_{deal_notifications_db,rfq_response_service_db}.py`.
- **Routers** (2 files each): `app.api.admin_deals` → `app/main.py:40` +
  `tests/test_admin_deals_api.py`; `app.api.admin_escrow` → `app/main.py:41` +
  `tests/test_admin_escrow_api.py`; `app.api.portal.deals` → `app/main.py:66` +
  `tests/test_portal_deals_api.py`; `app.api.webhooks_escrow` → `app/main.py:95` +
  `tests/test_escrow_webhook_api.py`.
- **Namespace-style imports:** `deal_service.py:57` opens a multi-name `from app.services import
  (…)` block; `app/api/portal/deals.py` and `app/api/admin_escrow.py` do the same. Shared-kernel
  names (`audit_service`, `event_service`, `event_types`, `notification_service`,
  `storage_service`) stay on `app.services`; the moved ones become separate aliased imports.
  **Split by hand — sed will corrupt these.**

## Cross-domain reach to expect (accept, do not fix)

`deal_service` imports from five other domains at module level: `accounts`, `companies`,
`contracts` (P4), `marketplace` (P1: `OfferRequest`, `SellerOffer`), and `requests` (P9). That is
expected — a deal is where a contract, an offer and a buyer request converge, and
`00-CONTEXT.md` explicitly tolerates two-way domain relationships rather than solving them. Do
not introduce indirection to "fix" it.

Also inbound: `lab_service` and `app/api/portal/lab.py` (both P7) read `models/deals`, and
`app/api/admin_lab.py` calls `deal_service`. Those call sites get re-pointed here and re-pointed
again in P7 — unavoidable given the ordering, and cheap.

## Steps

1. Re-run the grep inventory against the post-P4 tree.
2. Create `app/domains/deals/__init__.py`.
3. `git mv` the 10 files to their new paths (preserves history).
4. **Extract `list_market_requests` + `MarketRequestListOut`** into
   `app/domains/marketplace/api_portal.py`, declared above the `/{offer_id}` route. Its
   `_company_or_404` call becomes `deps.company_or_404` (P2's shared portal kernel). Add the
   cross-domain import of `app.domains.deals.rfq`.
5. Fix internal imports within the moved files (`escrow.py` → `service`, `payment_models`;
   `rfq.py` → `service` for the two exception classes; all three → `models`).
6. Update the `app/models/__init__.py` barrel lines for `deals.py` (40) and `payments.py` (129),
   preserving FK-order position. `__all__` entries are name-only — no edit.
7. Replace call sites:
   - `app.models.deals` → `app.domains.deals.models`
   - `app.models.payments` → `app.domains.deals.payment_models`
   - `app.schemas.portal_deal` → `app.domains.deals.schemas`
   - `app.services.deal_service` → `app.domains.deals.service`
   - `app.services.escrow_service` → `app.domains.deals.escrow`
   - `app.services.rfq_response_service` → `app.domains.deals.rfq`
   - `app.api.admin_deals` → `app.domains.deals.api_admin`
   - `app.api.admin_escrow` → `app.domains.deals.api_admin_escrow`
   - `app.api.portal.deals` → `app.domains.deals.api_portal`
   - `app.api.webhooks_escrow` → `app.domains.deals.api_webhooks`
   Then split the mixed `from app.services import (…)` blocks by hand and alias.
8. Update `app/main.py` import lines 40, 41, 66, 95. Leave every `include_router` call where it
   is — step 4 makes the deals-before-market ordering irrelevant, but reordering is not this
   phase's job.
9. Update `backend/pyproject.toml` mypy overrides (the `app.domains.*` blocks from P2 — verify
   present) and the mypy invocations, local + `.github/workflows/ci.yml` lines 75/78, adding
   `app/domains/deals/{service,escrow,rfq}.py` to the services check and
   `app/domains/deals/schemas.py` to the schemas check.
10. Run the full gate and fix anything red:
    - `cd backend && ruff check .`
    - `cd backend && mypy app/services app/domains/*/service.py app/domains/deals/{escrow,rfq}.py app/domains/contracts/{render,eimzo}.py app/domains/companies/directory.py app/domains/verification/{checks,registry}.py app/domains/marketplace/{requests,compliance}.py --ignore-missing-imports`
    - `cd backend && mypy app/schemas app/domains/*/schemas.py app/domains/contracts/eimzo_schemas.py --ignore-missing-imports`
    - `cd backend && pytest tests/ -q` (full suite, not a subset)
11. Commit once everything is green.

## Verification

- `ruff check .` — no new lint errors.
- Both `mypy` invocations — clean.
- `pytest tests/ -q` — full suite green. Highest-signal files: `test_deal_service_db.py`,
  `test_deal_transitions.py`, `test_deal_notifications_db.py`, `test_deal_contract_link_db.py`,
  `test_escrow_service_db.py`, `test_escrow_transitions.py`, `test_escrow_consumer_db.py`,
  `test_escrow_provider_events_db.py`, `test_escrow_reconcile_db.py`,
  `test_escrow_notifications_db.py`, `test_escrow_webhook_api.py`, `test_admin_deals_api.py`,
  `test_admin_escrow_api.py`, `test_portal_deals_api.py`, `test_rfq_response_service_db.py`.
- `uv run uvicorn app.main:app --reload` boots without import errors.
- **Route-parity check:** compare `sorted((r.path, tuple(sorted(r.methods))) for r in app.routes)`
  before and after — byte-identical. This phase relocates a route between routers, so back parity
  with an explicit request-level check that `GET /api/v1/portal/market/requests` resolves to
  `list_market_requests` and **not** to `get_offer` with `offer_id="requests"` (which would 422).
  That check is the whole point of step 4 — write it even though parity passes either way.
- **Webhook check:** `POST /api/v1/webhooks/escrow/{provider}` is authenticated by a shared secret,
  not a JWT, and carries `include_in_schema=False`. Confirm after the move that it still resolves,
  still rejects a bad signature, and still does **not** appear in `/openapi.json` — an accidental
  `include_in_schema` flip would publish a callback inbox.
- `grep -rn "app\.models\.deals\|app\.models\.payments\|app\.schemas\.portal_deal\|app\.services\.deal_service\|app\.services\.escrow_service\|app\.services\.rfq_response_service\|app\.api\.admin_deals\|app\.api\.admin_escrow\|app\.api\.portal\.deals\|app\.api\.webhooks_escrow" backend/app backend/tests` returns nothing.
