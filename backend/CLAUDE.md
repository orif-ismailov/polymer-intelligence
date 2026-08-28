# CLAUDE.md — backend/

Scoped guidance for `backend/`. See the repo-root `CLAUDE.md` for the cross-cutting
big picture (pipeline, Celery topology, LLM extraction, conventions).

## Stack & tooling

FastAPI + Celery + SQLAlchemy 2, Python 3.12, **uv**-managed. Run all commands from `backend/`.

```bash
uv sync --frozen --extra dev        # install exact locked deps (uv.lock is authoritative)
ruff check .                         # lint  (config in pyproject.toml)
# strict type-check over the WHOLE app package. Modules that don't pass yet are listed
# in pyproject.toml's burn-down override (48 at the time of writing: routers, ingest
# adapters, seeders, task modules — none of which the old file-list gate covered either).
# A NEW file is checked by default; exempting one is a deliberate edit to that list.
mypy app --ignore-missing-imports
pytest tests/ -q                     # full suite
pytest tests/test_feed_api.py::test_name -q  # single test
pytest -k "telegram and not accuracy" -q     # by pattern
uv run uvicorn app.main:app --reload # local API (needs DATABASE_URL/REDIS_URL + secrets)
alembic upgrade head                 # apply migrations (or app/entrypoint.py, advisory-locked)
```

## Directory map

| Path | Role |
|------|------|
| `app/main.py` | `create_app()` factory — routers under `/api/v1`, CORS, lifespan (migrations + Telegram webhook). |
| `app/core/` | `config.py` (`settings` singleton), `paths.py` (`BACKEND_ROOT`/`PROMPTS_DIR` — anchor `parsing/` lookups here, never `Path(__file__).parent.parent.parent`, which breaks when a module moves), `db.py`, `logging.py` (structlog), `security.py`, `crypto.py`, `time.py`, `feed_bus.py` (SSE). |
| `app/ingest/` | **Stays outside `app/domains/` by design**, and imports `app.domains.signals.source_models` — an adapter layer depending on the model it adapts; do not add a re-export shim to hide the path. Source adapters (`<type>/adapter.py`: `uzex`, `cbu_rates`, `xarid`, `html_table`, `llm_page`, `rss`, `telegram_channel`) + `registry.py` + `base.py` Protocol + `http_client.py` (SSRF-guarded). |
| `app/integrations/` | External gateway adapters: `sms/` (console/eskiz) + **R3** `eimzo/` (UNICON e-imzo-server sidecar client — `verify_pkcs7`, `EIMZO_STUB` dev mode) + **P3/P7.b** `escrow/` (`client` = outbound, waiting on the bank spec; `events` = INBOUND, a normalized callback + per-provider mapper registry, complete) + **P5** `chem_registry/` (stub-only: no national registry exists) + **P7.c** `gov_registry/` (interface + DTOs + stub; ПЦД access pending) + **P7.a** `didox/` (the EDI partner API — `client` = the gateway, `auth` = service `user-key` minting + Redis cache, `registry` = the tax-registry lookup adapted onto the P7.c protocol) + `circuit_breaker.py` (reusable, gateway-wide). |
| `app/tasks/` | Celery app (`celery_app.py`), beat schedule (`schedule.py`), task modules (ingest*/parse*/notify/reports/nightly_catchup/rescore/userbot_health/request_analysis/verification/**contracts** — R3 nightly integrity + expiry beats; **P7.b** `payments` gained `apply_escrow_provider_event`/`sweep_provider_events` on `default` and `reconcile_escrow_payments` on `verify`). |
| `app/domains/` | Bounded-context folders — one domain's models + schemas + service + routers together. **`marketplace/`**: `models.py`, `schemas.py`, `portal_market_schemas.py`, `service.py` (offers), `requests.py` (buyer inquiries), `compliance.py` (publish gate), and its seven routers `api_portal*`/`api_admin*`/`api_webapp_*`. **`verification/`**: `models.py` + `registry_models.py`, `schemas.py` (applicant-side case views), `service.py`, `checks.py` (pure verdict functions), `registry.py` (append-only gov snapshots), `api_admin.py` (staff queue) and `api_portal.py` (documents + case submit, carved out of `portal/companies.py`). **`companies/`**: `models.py`, `schemas.py`, `service.py`, `directory.py` (the public role directories) and `api_portal.py` (the client cabinet's company CRUD). Still incomplete by design — `CompanyReview`/`CompanyMedia` + `review_service` land here in P11. **`contracts/`**: `models.py` + `eimzo_models.py`, `schemas.py` + `eimzo_schemas.py`, `service.py` (the contract state machine), `render.py` (WeasyPrint HTML→PDF, golden-hash pinned), `eimzo.py` (E-IMZO challenge/verify, used for both company identity confirmation and contract signing), `api_admin.py`, `api_portal.py`, `api_portal_eimzo.py`. **`deals/`**: `models.py` + `payment_models.py`, `schemas.py`, `service.py` (deal state machine), `escrow.py` (escrow state machine + provider-event inbox), `rfq.py` (supplier quotes against a buyer RFQ), `api_admin.py`, `api_admin_escrow.py`, `api_portal.py`, `api_webhooks.py` (the bank callback inbox — shared-secret auth, `include_in_schema=False`). **`compliance/`**: `models.py`, `schemas.py` + `substance_schemas.py` + `substance_match_schemas.py`, `substances.py` (the registry), `substance_ai.py` (the AI hint), `licenses.py`, and four routers `api_admin_substances`/`api_admin_licenses`/`api_portal_substances`/`api_portal`. Note the offer publish gate `offer_compliance_service` is its heaviest consumer but stays in `marketplace/compliance.py` — it owns the OFFER gate and sits in a deliberate cycle with `offer_service`. **`logistics/`**, **`laboratory/`**, **`manufacturers/`**, **`lab_orders/`**: four disjoint contexts split out of one roadmap line, each `models` + `schemas` + `service` + routers. **`laboratory/` and `lab_orders/` are different flows and the names are deliberate** — `laboratory` is a buyer broadcasting an analysis request to every verified lab (each opens a thread); `lab_orders` is staff-driven analysis hung off an offer or deal, worked by partner labs, and owns the `lab_verified` gold badge. `lab_orders/api_portal.py` declares the RFQ/thread literals BEFORE `/{manufacturer_id}`-style param routes in `manufacturers/api_portal.py` — that intra-file order is load-bearing, do not sort or regroup those decorators. **`news/`**: `models.py` (only `Report` — **there is no news-article model**; an article IS a `Signal` row with `kind='news'` and its classification lives in `signals.ai` under `ai.news`), `schemas.py`, `service.py`, `dedup.py`, `reports.py` (digest render + the draft→approved→published lifecycle), `api_admin.py`/`api_portal.py`/`api_webapp.py`. **`pricing/`**: `models.py` (price points, fed by the CBU/UZEX ingest pipelines), `analysis.py`, `api_admin.py`. **`requests/`**: `models.py` (also declares `Client`), `schemas.py` + `webapp_schemas.py` + `analysis_schemas.py`, `service.py`, `analysis.py` (the LLM buyer-request analysis), `rfq_push.py` + `supplier_matching.py` (arrived from P5 — outbound actions on a request, not deals), and four routers. **`sourcing/`**: the AI-broker waterfall for a buyer request (inventory -> partners -> offers -> import) — unrelated to `signals/`, which it never imports. **`signals/`**: `models.py` + `source_models.py` + `counterparty_models.py`, `service.py`, `ai.py`, `raw_pipeline.py`, `sources.py`, `source_health.py`, `api_feed.py`/`api_sources.py`/`api_admin.py`. Read that folder's `__init__.py` first: `api_feed.py` imports no model (its contract is the `v_live_feed` DB view), news articles are `Signal` rows with `kind='news'`, and `counterparty_models` looks unused but its barrel import is what puts `counterparties` in `Base.metadata` for a STRING FK target. Plus **`accounts/`** (portal identity + phone-OTP), **`reference/`** (products/grades/synonyms — its own domain because four others consume it), **`alerts/`**, **`notifications/`** (owns the row + portal read surface; the DISPATCHER `notification_service` stays kernel), and **`storefront/`** (the anonymous public surface — a bounded context whose data is borrowed from four domains). **`edi/`** (P7.a — the Didox document rail, and the only domain whose subject lives in ANOTHER domain): `models.py` (`DidoxDocument`/`DidoxCompany` — one table for both document types, linked to its subject by `(subject_kind, subject_id)` rather than an FK, because a 007 hangs off a contract and an ЭСФ off a deal), `payloads.py` (pure builders for `007`/`002` — golden-tested, PascalCase in and lowercase out), `contract_docs.py` (**the door**: turns one of our contracts into their document — owner is the SELLER, prose is lifted from the rendered contract's `<h2>` sections, and a missing signer identity or ИКПУ raises rather than defaulting), `service.py` (the create/sign/status machine — an outgoing draft leaves by `send_document`, an incoming one by `sign_document`), `session.py` (the 360-min `user-key`; `require_user_key` NEVER mints), `onboarding.py`, `numbering.py`, `api_portal.py`, `api_admin.py`. **The reorg is complete**: 21 domains, and what is left in `app/services|schemas|api|models/` is a CLOSED shared kernel listed in those packages' `__init__.py` docstrings. See `.planning/backend-domain-reorg/`. |
| `app/services/` | **CLOSED shared kernel**, declared in its `__init__.py` — **mypy-strict**, keep typed. `audit_service`, `auth_service`, `event_service`+`event_types` (transactional outbox), `notification_service` (the dispatcher), `storage_service`, `settings_service`, `rate_limit`, `dashboard_summary_service`. Everything else moved into `app/domains/<name>/`; "still here" now means kernel, not unmigrated. |
| `app/schemas/` | Kernel only: `auth.py`, `admin_settings.py`, and `dashboard.py` — the internal dashboard's presentation layer across seven domains, deliberately kept with `dashboard_summary_service` + `app/api/dashboard.py` rather than split per domain. |
| `app/models/` | Kernel only: `enums.py`, `staff.py` (StaffUser + AuditLog — authorization substrate, no owner), `events.py`, `integration.py`, `app_settings.py`. `__init__.py` is the alembic barrel: it imports every domain's models **as MODULES, never by name** — a name import is a circular-import bug that only fires when a domain model is the first app module imported in a process. `grep '^from app.domains' app/models/__init__.py` must return nothing. |
| `app/api/` | Routers; `app/api/webapp/` is the Telegram Web App surface (incl. `webapp/news.py`); `app/api/portal/` is the **client cabinet** — R1 `auth` (phone-OTP), `companies` + **R2** `requests`, `news` (webapp-news twin), `notifications` (auth via `deps.get_current_account`; company-scoped writes via `company_service.get_company_for` → 404 for non-members). The marketplace surfaces that used to sit here — portal `offers`/`market`/`inquiries`, `webapp/market`, `webapp/seller`, plus admin `moderation.py` and `offer_requests.py` — now live in `app/domains/marketplace/`, still mounted from `app/main.py` at their original prefixes; the verification surfaces — `admin_verification.py` (staff queue) and the documents + case-submit routes formerly in `portal/companies.py` — moved to `app/domains/verification/`, again at unchanged paths; `admin_settings.py`/`reports.py` back the news admin; the **R3** contract + E-IMZO routers moved to `app/domains/contracts/` — and with them went the include-order dependency: `/portal/companies/directory` used to live on the contracts router and force it to be registered before `portal/companies`, but P4 moved that route to the companies router where being declared above `/{company_id}` settles the match locally; **P6** `portal/lab.py` + `portal/samples.py` (both registered before `portal/companies` for the same reason) and `admin_lab.py` (queue + partner directory); the substance/licence/compliance routers moved to `app/domains/compliance/` — after which two domains own routes under `/admin/companies/`: verification owns the company lifecycle actions, compliance owns the `licenses` sub-resource, which is REST layering and not a leak; the deals/escrow routers (incl. the bank callback inbox) moved to `app/domains/deals/`, and with them `GET /portal/market/requests`, which now lives on the portal-market router that owns `/{offer_id}` — it used to depend, undocumented, on the deals router being included first (P5); `deps.py` holds RBAC guards. |
| `app/seed/` | Idempotent seeders (`seed_reference/staff/sources/demo/contract_templates` + **P5** `seed_substances`, revision-versioned) + JSON in `data/`. |
| `parsing/` | LLM extractors (`extractor.py`, `news_extractor.py` + `news_schemas.py`), prompts (`prompts/{extract,news_extract,report,analyze_request,substance_match}_vN.md`), budget guard, rule-based fallback, eval CLI. |
| `alembic/versions/` | Migration chain `0001`→`0041`. Recent: **`0041` the Didox rail** (`didox_documents`, `didox_companies`, `contracts.signing_provider`, `contract_templates.kind`, `seller_offers.ikpu_*` + `sample_letter_*`, `sample_requests.public_id|deal_id|letter_*`, and `sample_request_status += pending_letter` — the ENUM value is added inside `op.get_context().autocommit_block()`, per the `0028_lab.py` precedent), `0035`–`0040` (storefront + confirmed roles); `0030` offer product facts, `0031`–`0033` the manufacturer/logistics/laboratory company profiles, `0034` manufacturers module, `0029` gov-registry snapshots, `0022` logo, `0023` deals, `0024` escrow, `0025` offer sale fields, `0026` rfq push log, `0027` compliance, `0028` labs + samples; earlier: `0001`→`0021` (`0017` R1 verification/portal, `0018` R2 dual-origin requests/inquiries + `portal_notifications`, `0019` market-list index, `0020` R3 E-IMZO rails — `signature_evidence`/`company_person_data`/`integration_call_log`, `0021` R3 contracts). |

## Verifying a change

A green `pytest` is not evidence that a route works for a user. Anything a screen can reach must
also be driven in a real browser through the `chrome-devtools` MCP server (repo-root `CLAUDE.md`
explains why, with the list of bugs that survived a full suite). The two failure shapes this
package produces are worth naming: a **schema that reads back fewer fields than it accepts**
silently erases data on the next save, and an **endpoint whose response shape differs from the
mock** (raw base64 vs JSON) turns a working 200 into an outage. Neither shows up in a test that
mocks the thing it is testing.

## Gotchas specific to this package

- **Adapters self-register at import time** into `app/ingest/registry.py`. Registration happens
  only in the process that imports the module — so each adapter is imported in BOTH `app/main.py`
  (API process: Test button, `GET /admin/source-types`) AND `app/tasks/ingest.py` (worker). A new
  adapter must be imported in both.
- **Celery task modules** must be listed in `_TASK_MODULES` in `celery_app.py` — autodiscover is a
  no-op here; an unlisted module = "unregistered task" at dispatch. Queues are
  `ingest/parse/notify/default` + `verify` (R1 company verification) — news/report/breaking-news
  tasks route onto the first four, `app.tasks.verification.*` routes to `verify`. `task_routes` must
  stay in sync with the compose `-Q` flag (both compose files). Task **names** in `schedule.py` are a
  stable contract; the `@task(name=...)` bodies live in the modules.
- **New ORM model** → add it to `app/models/__init__.py` (FK order) or alembic's `env.py` won't see it.
- **Enums** in `app/models/enums.py` are `(str, Enum)`, not `StrEnum` (matches PG ENUMs verbatim;
  ruff `UP042` disabled).
- **Prompts are immutable + versioned** across five families (`extract`, `news_extract`, `report`,
  `analyze_request`, `substance_match`): change = new `parsing/prompts/<family>_v{N+1}.md` + bump its
  pin (`substance_match` pins in `substance_ai_service.PROMPT_VERSION`). The
  `extract`/`report`/`analyze_request` pins are env (`LLM_PROMPT_VERSION`, `REPORT_PROMPT_VERSION`,
  `REQUEST_AI_ANALYSIS_PROMPT_VERSION`); the `news_extract` version is a **runtime** app-setting
  (`news_prompt_version`), so it can be changed from the dashboard without a deploy. The resolved
  version is journaled in `parse_runs.prompt_version`.
- **Runtime settings** (`app/services/settings_service.py`, `app_settings` table) are operator-editable
  knobs (news/report toggles, `escrow_mode`, the `rfq_supplier_push_*` set, and **P5**
  `dangerous_check_enforced` (publish gate, ships OFF), `substance_ai_enabled`,
  `chem_registry_mode`, and **P7.c** `gov_registry_mode` (ships `stub`; `didox` reads the tax
  registry through the P7.a gateway; `live` raises until a ПЦД adapter exists), plus **P7.a**
  `didox_mode` (the DOCUMENT rail — deliberately separate, because reading the registry is harmless
  and sending legally significant documents is not)) — separate from the immutable env/`config.py`
  contract. Read them via `settings_service`, not `settings`. A `SettingSpec` may carry `choices`
  for a closed set.
- **Labs and samples (P6)** — the analysis is a MANUAL partner-lab process, so every
  `lab_orders` status is moved by staff (`/admin/lab-orders`, analyst; the partner directory
  is admin-only). `done` is unreachable through `lab_service.transition`: the only door is
  `complete_with_result`, which stores the PDF and points the order at it in one transaction
  (`ck_lab_order_done_has_result` says the same thing in the schema). **`lab_verified` is set
  there and nowhere else** — it separates "the seller uploaded a passport" (badge, derived
  from `seller_offer_files.kind='lab_passport'`) from "we had it analysed" (gold badge, its
  own market filter). A seller-uploaded passport re-enters moderation; a staff-uploaded
  result does not. `sample_service` is the other machine: both parties drive it, so
  `_ACTOR_RULES` is a table, and "one live request per (offer, buyer)" is a partial unique
  index, not an `if`.
- **Provider callbacks (P7.b)** — the escrow rail is deliberately ONE-DIRECTIONAL. A bank may
  apply only the movements that carry a deal FORWARD (`escrow_service.AUTO_APPLIED` =
  `funded`, `released`); everything else is recorded, explained and HELD for an operator
  (`HOLD_PREFIX` in `provider_events.error`, surfaced by `held_provider_events` and
  `GET /admin/escrow/provider-events`). **That is the answer to the question P3 recorded in
  `apply_provider_event`** — a refund kills the deal, `cancelled` is not reachable by
  `system`, and we neither widened `deal_service._ACTOR_RULES` nor invented a service
  account. `mark` (operator) and `mark_from_provider` (bank) share one body, `_apply_mark`:
  they differ only in who is accountable, so a rail can never become the way around a guard.
  The webhook records → commits → answers 200 → THEN enqueues, and `sweep_provider_events`
  is the other half of that bargain — a dropped dispatch must cost latency, not evidence.
  The hold queue self-clears (a hold is a disagreement; the operator's manual mark ends it),
  which is why there is no resolve endpoint and no extra column.
- **State registries (P7.c)** — `registry_snapshots` is append-only: no `updated_at`, no
  UPDATE path, a re-check is a new row. Two writers share one shape — `source='registry'`
  (an API answered, `created_by` NULL) and `source='manual'` (a staff member transcribed an
  open service + screenshot). The verdict comes from the same pure functions
  (`verification_checks.check_gov_registry`/`check_vat_status`) either way; `source` is the
  only record of which it was. `StubGovRegistryClient` **raises** instead of returning empty
  snapshots — an empty `CompanySnapshot` reads as "no such company", turning our missing
  integration into a finding about a real business. Registry checks are spawned at submit
  only when `gov_registry_mode='live'`; on the stub rail they appear when an operator records
  a snapshot (`verification_service.upsert_check`), so no case waits on a channel we lack.
- **Didox (P7.a Stage 1)** — the EDI operator's `/v1/utils/info/{tin}` reads the TAX REGISTRY, so it
  is wired in as a third `gov_registry_mode` rail (`stub` | **`didox`** | `live`) rather than as a
  second registry subsystem: `DidoxGovRegistryClient` implements the P7.c protocol, and the existing
  `registry_service`/`verification_checks`/admin UI work unchanged. Three things the live API taught
  us that the code now encodes. **"No such company" is HTTP 200 with an envelope full of nulls** —
  `DidoxCompanyInfo.from_payload` returns `None` for it, because an empty snapshot reads as a finding
  about a real business. **A 401 is auth, not content** (prod demands a `user-key` for that endpoint;
  the test contour does not) so it raises `ProviderUnavailable` instead of becoming a verdict.
  **`lookup_licenses` raises** — Didox has no licence register, and `[]` would mean "holds none".
  `CompanyNotFound` subclasses `ProviderUnavailable` so every existing caller degrades to an
  `unavailable` check while `GET /portal/companies/lookup` (registration prefill) can say "not found";
  `ChannelDisabled` splits "this deployment has no registry" from "the provider is down" so the
  wizard stays silent about a feature nobody enabled. The user-key can only be minted per company
  (E-IMZO) or by password, so `auth.service_user_key` mints ONE for our own account, caches it in
  Redis for 300 min (server TTL is 360), and **never retries a failed password** — the lockout
  ladder ends at permanent.
- **Didox documents (P7.a Stage 2)** — the rail that carries a contract to the tax authority.
  `contracts.signing_provider` is frozen at creation (`eimzo` | `didox`) and decides everything
  downstream; on the Didox rail **no `contract_signatures` rows are written**, because
  `signature_evidence_id` is NOT NULL and points at a PKCS#7 we verified — and we never see the
  counterparty's (they may have signed at any of the 27 operators). The contract becomes active
  through `contract_service.activate_from_provider` instead.
  **`POST /{id}/sign` is the door for an outgoing draft** — their §9, and it works. An earlier
  note here said the opposite: on 21.08 `/sign` answered 500 `Undefined variable $isDraft` and we
  routed outgoing drafts through `PUT /{id}/send`. That 500 was a symptom of the UNSIGNED public
  offer; once the offer was signed the two swapped places, and `/send` now answers
  `422 Неподдерживаемый тип документа` for a 007. `send_document` stays on the client for the types
  that use it. **The ИКПУ search covers the company's own basket, not the tasnif catalog**, and
  `check/{code}` 422s for an unbound code — so the picker binds first and reads the row back rather
  than guessing packages or origin. `origin` is never returned by Didox at all: it is the seller's
  answer (own production vs resale) and the offer form asks for it.

  **Their refusals arrive in a ladder, one gate at a time**, and each hides the next until it is
  cleared — which is why every "one more thing and we are done" estimate on this rail was wrong.
  In order, live: the buyer's ИНН must be in the tax registry (`ИНН/ПИНФЛ заказчика некорректный`);
  the ИКПУ must be known to the roaming centre (`не включены в список избранных ИКПУ` — NOT the
  counterparty's basket, which stays empty; Didox fixed this at `dev-s0.rouming.uz`); the buyer's
  `FizTin`/`Fio` are mandatory (`ПИНФЛ … заказчика не указан`) — **`create` accepts them empty and
  only `sign` refuses**, so the condition surfaces after the signatory has typed their key
  password; and the PINFL must be 14 digits, not the 9-digit ИНН. The first two are checked BEFORE
  a key is loaded, as `counterparty_unknown` and `counterparty_ikpu_missing` blockers on the
  prefill — neither is fixable from our side, so they can only be shown.

  **Section titles must not carry their own number.** Didox prefixes `ordno` when it prints, and
  our template writes «1. Стороны» into the `<h2>`, so the operator's form read «1. 1. Стороны».
  `sections_from_html` strips a LEADING ordinal (`1.`, `2)`, `1.2.` — the separator is required, or
  «2026 год…» loses its year). Still open and NOT a code question: we also send «Стороны»,
  «Предмет договора» and «Подписи сторон», all three of which Didox already renders from
  `Owner`/`Clients`/`Products` and its own signature block — and the third asserts that signature
  marks are kept "в системе", which is false on this rail.

  **`didox_documents.status` is the OWNER's view** (we read it with `owner=1`), and Didox's `1` and
  `2` are one state named from two ends. `contracts.api_portal._didox_status_for_viewer` mirrors
  them for whoever is asking, because handing the seller's number to the buyer hid the sign button
  from the very party whose turn it was. Everything else — draft, signed, rejected, annulled — is a
  fact about the document and does not flip.

  **`print_form` is the operator's rendering, and a different artefact from ours.**
  `contracts/render.py` produces what we asked the parties to sign; `GET /v1/documents/{id}/pdf`
  carries Didox's electronic-document id, the QR, the ИКПУ/НДС table and both signature marks — the
  form my.soliq.uz shows. Two routes differing only in who may ask: `view/…` also checks the
  document is theirs (cabinet, with that company's `user-key`), the plain one takes the partner
  token alone (staff, who act as nobody). Streamed, never cached: the form changes with the status,
  and a draft's carries no marks. The ARCHIVE is the artefact we keep, fetched once on the move to
  signed.

  **`get_document(owner=True)` goes over the wire as `owner=true` and earns a bare 500.** `bool` is
  an `int` to the type checker, so it passes mypy; the client coerces with `int(owner)`.

- **`MAX_CHECK_ATTEMPTS` lives in `verification_service`**, and `tasks/verification.py`
  imports it for `max_retries`. The evaluator needs the same number: an `unavailable` check
  blocks a case while retries remain and stops blocking once they are spent. Before P7.c it
  blocked unconditionally, and since `approve()` only reaches `pending_review`, an exhausted
  check pinned the case in `checks_running` — a dead provider silently disabled the manual
  path it was supposed to leave open. Don't split that constant.
- **Chemical compliance (P5)** — `substances` is the source of truth (no national registry exists):
  `hs_code` is the legal identifier, `cas` a nullable secondary. `offer_compliance_service.decide()`
  is the whole ruleset as a pure function; `evaluate()` adds the DB lookups. The gate HOLDS a
  non-compliant offer as a `draft` rather than raising — a `docs_required` substance can only get
  its documents after the offer row exists — and releases it on the next save once the requirement
  is met. Approval re-checks on both paths (dashboard + bot).
- `raw_items` is **immutable** — `save_raw_items()` (`app/services/raw_pipeline.py`) inserts with
  `ON CONFLICT DO NOTHING`; never mutate existing rows.
- Domain exceptions drop the `Error` suffix (`BudgetExceeded`, `InvalidInitData`) — ruff `N818` off.
- `settings` is a single module-level instance — import it, never call `Settings()` again.
- The `telegram` and `userbot` packages live at the **repo root**, not under `backend/`; tests and
  the worker import them, and compose mounts them read-only into the backend image.
