# CLAUDE.md — backend/

Scoped guidance for `backend/`. See the repo-root `CLAUDE.md` for the cross-cutting
big picture (pipeline, Celery topology, LLM extraction, conventions).

## Stack & tooling

FastAPI + Celery + SQLAlchemy 2, Python 3.12, **uv**-managed. Run all commands from `backend/`.

```bash
uv sync --frozen --extra dev        # install exact locked deps (uv.lock is authoritative)
ruff check .                         # lint  (config in pyproject.toml)
# strict type-check (CI-gated scope). Each domain moved into app/domains/<name>/ appends
# its service/schema modules here so the gate follows the code — keep in sync with ci.yml.
mypy app/services app/domains/marketplace/{service,requests,compliance}.py \
     app/domains/verification/{service,checks,registry}.py \
     app/domains/companies/{service,directory}.py \
     app/domains/contracts/{service,render,eimzo}.py \
     app/domains/deals/{service,escrow,rfq}.py \
     app/domains/compliance/{substances,substance_ai,licenses}.py --ignore-missing-imports
mypy app/schemas  app/domains/marketplace/{schemas,portal_market_schemas}.py \
     app/domains/{verification,companies}/schemas.py \
     app/domains/contracts/{schemas,eimzo_schemas}.py \
     app/domains/deals/schemas.py \
     app/domains/compliance/{schemas,substance_schemas,substance_match_schemas}.py --ignore-missing-imports
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
| `app/core/` | `config.py` (`settings` singleton), `db.py`, `logging.py` (structlog), `security.py`, `crypto.py`, `time.py`, `feed_bus.py` (SSE). |
| `app/ingest/` | Source adapters (`<type>/adapter.py`: `uzex`, `cbu_rates`, `xarid`, `html_table`, `llm_page`, `rss`, `telegram_channel`) + `registry.py` + `base.py` Protocol + `http_client.py` (SSRF-guarded). |
| `app/integrations/` | External gateway adapters: `sms/` (console/eskiz) + **R3** `eimzo/` (UNICON e-imzo-server sidecar client — `verify_pkcs7`, `EIMZO_STUB` dev mode) + **P3/P7.b** `escrow/` (`client` = outbound, waiting on the bank spec; `events` = INBOUND, a normalized callback + per-provider mapper registry, complete) + **P5** `chem_registry/` (stub-only: no national registry exists) + **P7.c** `gov_registry/` (interface + DTOs + stub; ПЦД access pending) + `circuit_breaker.py` (reusable, gateway-wide). |
| `app/tasks/` | Celery app (`celery_app.py`), beat schedule (`schedule.py`), task modules (ingest*/parse*/notify/reports/nightly_catchup/rescore/userbot_health/request_analysis/verification/**contracts** — R3 nightly integrity + expiry beats; **P7.b** `payments` gained `apply_escrow_provider_event`/`sweep_provider_events` on `default` and `reconcile_escrow_payments` on `verify`). |
| `app/domains/` | Bounded-context folders — one domain's models + schemas + service + routers together. **`marketplace/`**: `models.py`, `schemas.py`, `portal_market_schemas.py`, `service.py` (offers), `requests.py` (buyer inquiries), `compliance.py` (publish gate), and its seven routers `api_portal*`/`api_admin*`/`api_webapp_*`. **`verification/`**: `models.py` + `registry_models.py`, `schemas.py` (applicant-side case views), `service.py`, `checks.py` (pure verdict functions), `registry.py` (append-only gov snapshots), `api_admin.py` (staff queue) and `api_portal.py` (documents + case submit, carved out of `portal/companies.py`). **`companies/`**: `models.py`, `schemas.py`, `service.py`, `directory.py` (the public role directories) and `api_portal.py` (the client cabinet's company CRUD). Still incomplete by design — `CompanyReview`/`CompanyMedia` + `review_service` land here in P11. **`contracts/`**: `models.py` + `eimzo_models.py`, `schemas.py` + `eimzo_schemas.py`, `service.py` (the contract state machine), `render.py` (WeasyPrint HTML→PDF, golden-hash pinned), `eimzo.py` (E-IMZO challenge/verify, used for both company identity confirmation and contract signing), `api_admin.py`, `api_portal.py`, `api_portal_eimzo.py`. **`deals/`**: `models.py` + `payment_models.py`, `schemas.py`, `service.py` (deal state machine), `escrow.py` (escrow state machine + provider-event inbox), `rfq.py` (supplier quotes against a buyer RFQ), `api_admin.py`, `api_admin_escrow.py`, `api_portal.py`, `api_webhooks.py` (the bank callback inbox — shared-secret auth, `include_in_schema=False`). **`compliance/`**: `models.py`, `schemas.py` + `substance_schemas.py` + `substance_match_schemas.py`, `substances.py` (the registry), `substance_ai.py` (the AI hint), `licenses.py`, and four routers `api_admin_substances`/`api_admin_licenses`/`api_portal_substances`/`api_portal`. Note the offer publish gate `offer_compliance_service` is its heaviest consumer but stays in `marketplace/compliance.py` — it owns the OFFER gate and sits in a deliberate cycle with `offer_service`. Migration is one domain per change with no back-compat shims — see `.planning/backend-domain-reorg/`. |
| `app/services/` | Business logic — **mypy-strict**, keep typed. Includes `news_service`, `news_dedup`, `report_service`, `settings_service`, `sourcing/request*`, and the R1 verification/portal set: `event_service`+`event_types` (transactional outbox), `otp_service`, `rate_limit`; **R2** `notification_service`; **P6** `lab_service` (partner directory + order machine + `complete_with_result`), `sample_service` (two-party machine), plus `rfq_push_service`/`supplier_matching_service` (P9 moves those with requests). `verification_service`/`verification_checks`/`registry_service` moved to `app/domains/verification/`; `company_service`/`directory_service` to `app/domains/companies/`; the **R3** set `eimzo_service`/`contract_service`/`contract_render` to `app/domains/contracts/`; `deal_service`/`escrow_service`/`rfq_response_service` to `app/domains/deals/`; `substance_service`/`substance_ai_service`/`company_license_service` to `app/domains/compliance/`. |
| `app/schemas/` | Pydantic request/response models — **mypy-strict**. Marketplace, verification, company, contract, deal and compliance schemas now live in their `app/domains/<name>/` folders. |
| `app/models/` | SQLAlchemy 2 ORM; `__init__.py` imports all in FK order for `Base.metadata` — including models that have moved into `app/domains/`, so the barrel stays complete for alembic. Relocated models are imported as MODULES, not by name — see the file's docstring; the barrel binds no class that lives under `app/domains/`. Domains: signals, sources, requests, sourcing, reports, app_settings, prices, alerts, reference, counterparties, staff, reviews, media, **P6** `lab` (lab partners/orders + sample requests). Moved out to `app/domains/`: marketplace, verification, companies, contracts (incl. `eimzo`), deals (incl. `payments`), compliance, and `registry` (`registry_snapshots` — append-only, no UPDATE path anywhere). |
| `app/api/` | Routers; `app/api/webapp/` is the Telegram Web App surface (incl. `webapp/news.py`); `app/api/portal/` is the **client cabinet** — R1 `auth` (phone-OTP), `companies` + **R2** `requests`, `news` (webapp-news twin), `notifications` (auth via `deps.get_current_account`; company-scoped writes via `company_service.get_company_for` → 404 for non-members). The marketplace surfaces that used to sit here — portal `offers`/`market`/`inquiries`, `webapp/market`, `webapp/seller`, plus admin `moderation.py` and `offer_requests.py` — now live in `app/domains/marketplace/`, still mounted from `app/main.py` at their original prefixes; the verification surfaces — `admin_verification.py` (staff queue) and the documents + case-submit routes formerly in `portal/companies.py` — moved to `app/domains/verification/`, again at unchanged paths; `admin_settings.py`/`reports.py` back the news admin; the **R3** contract + E-IMZO routers moved to `app/domains/contracts/` — and with them went the include-order dependency: `/portal/companies/directory` used to live on the contracts router and force it to be registered before `portal/companies`, but P4 moved that route to the companies router where being declared above `/{company_id}` settles the match locally; **P6** `portal/lab.py` + `portal/samples.py` (both registered before `portal/companies` for the same reason) and `admin_lab.py` (queue + partner directory); the substance/licence/compliance routers moved to `app/domains/compliance/` — after which two domains own routes under `/admin/companies/`: verification owns the company lifecycle actions, compliance owns the `licenses` sub-resource, which is REST layering and not a leak; the deals/escrow routers (incl. the bank callback inbox) moved to `app/domains/deals/`, and with them `GET /portal/market/requests`, which now lives on the portal-market router that owns `/{offer_id}` — it used to depend, undocumented, on the deals router being included first (P5); `deps.py` holds RBAC guards. |
| `app/seed/` | Idempotent seeders (`seed_reference/staff/sources/demo/contract_templates` + **P5** `seed_substances`, revision-versioned) + JSON in `data/`. |
| `parsing/` | LLM extractors (`extractor.py`, `news_extractor.py` + `news_schemas.py`), prompts (`prompts/{extract,news_extract,report,analyze_request,substance_match}_vN.md`), budget guard, rule-based fallback, eval CLI. |
| `alembic/versions/` | Migration chain `0001`→`0034` (`0030` offer product facts, `0031` company manufacturer profile, `0032` company logistics profile, `0033` company laboratory profile, `0034` manufacturers module, `0029` gov-registry snapshots, `0022` logo, `0023` deals, `0024` escrow, `0025` offer sale fields, `0026` rfq push log, `0027` compliance, `0028` labs + samples); earlier: `0001`→`0021` (`0017` R1 verification/portal, `0018` R2 dual-origin requests/inquiries + `portal_notifications`, `0019` market-list index, `0020` R3 E-IMZO rails — `signature_evidence`/`company_person_data`/`integration_call_log`, `0021` R3 contracts). |

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
  `chem_registry_mode`, and **P7.c** `gov_registry_mode` (ships `stub`; `live` raises until a ПЦД adapter exists)) — separate from the immutable env/`config.py` contract. Read them via
  `settings_service`, not `settings`. A `SettingSpec` may carry `choices` for a closed set.
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
