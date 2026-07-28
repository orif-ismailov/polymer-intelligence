# CLAUDE.md — backend/

Scoped guidance for `backend/`. See the repo-root `CLAUDE.md` for the cross-cutting
big picture (pipeline, Celery topology, LLM extraction, conventions).

## Stack & tooling

FastAPI + Celery + SQLAlchemy 2, Python 3.12, **uv**-managed. Run all commands from `backend/`.

```bash
uv sync --frozen --extra dev        # install exact locked deps (uv.lock is authoritative)
ruff check .                         # lint  (config in pyproject.toml)
mypy app/services --ignore-missing-imports   # strict type-check (CI-gated scope)
mypy app/schemas  --ignore-missing-imports
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
| `app/core/` | `config.py` (`settings` singleton), `db.py`, `logging.py` (structlog), `security.py`, `time.py`, `feed_bus.py` (SSE). |
| `app/ingest/` | Source adapters (`<type>/adapter.py`: `uzex`, `cbu_rates`, `xarid`, `html_table`, `llm_page`, `rss`, `telegram_channel`) + `registry.py` + `base.py` Protocol + `http_client.py` (SSRF-guarded). |
| `app/integrations/` | External gateway adapters: `sms/` (console/eskiz) + **R3** `eimzo/` (UNICON e-imzo-server sidecar client — `verify_pkcs7`, `EIMZO_STUB` dev mode) + **P3** `escrow/` + **P5** `chem_registry/` (stub-only: no national registry exists) + `circuit_breaker.py` (reusable, gateway-wide). |
| `app/tasks/` | Celery app (`celery_app.py`), beat schedule (`schedule.py`), task modules (ingest*/parse*/notify/reports/nightly_catchup/rescore/userbot_health/request_analysis/verification/**contracts** — R3 nightly integrity + expiry beats). |
| `app/services/` | Business logic — **mypy-strict**, keep typed. Includes `news_service`, `news_dedup`, `report_service`, `settings_service`, `offer*/sourcing/request*`, and the R1 verification/portal set: `event_service`+`event_types` (transactional outbox), `otp_service`, `company_service`, `verification_service`+`verification_checks`, `rate_limit`, `crypto`; **R2** `notification_service`; **R3** `eimzo_service` (challenge/verify → identity lock + evidence), `contract_service` (state machine + E-IMZO sign), `contract_render` (WeasyPrint HTML→PDF); **P6** `lab_service` (partner directory + order machine + `complete_with_result`), `sample_service` (two-party machine). |
| `app/schemas/` | Pydantic request/response models — **mypy-strict**. |
| `app/models/` | SQLAlchemy 2 ORM; `__init__.py` imports all in FK order for `Base.metadata`. Domains: signals, sources, requests, marketplace, sourcing, reports, app_settings, prices, alerts, reference, counterparties, staff, **P6** `lab` (lab partners/orders + sample requests). |
| `app/api/` | Routers; `app/api/webapp/` is the Telegram Web App surface (incl. `webapp/news.py`); `app/api/portal/` is the **client cabinet** — R1 `auth` (phone-OTP), `companies`, `offers` + **R2** `market`, `inquiries`, `requests`, `news` (webapp-news twin), `notifications` (auth via `deps.get_current_account`; company-scoped writes via `company_service.get_company_for` → 404 for non-members); `admin_verification.py` backs the staff verification queue; `admin_settings.py`/`reports.py`/`moderation.py` back the news + marketplace admin; **R3** `portal/eimzo.py` (challenge/verify), `portal/contracts.py` (contract lifecycle + counterparty directory + signed bundle) — registered BEFORE `portal/companies` so `/portal/companies/directory` wins over `/{company_id}`; `admin_contracts.py` is read-only staff oversight; **P6** `portal/lab.py` + `portal/samples.py` (both registered before `portal/companies` for the same reason) and `admin_lab.py` (queue + partner directory); `deps.py` holds RBAC guards. |
| `app/seed/` | Idempotent seeders (`seed_reference/staff/sources/demo/contract_templates` + **P5** `seed_substances`, revision-versioned) + JSON in `data/`. |
| `parsing/` | LLM extractors (`extractor.py`, `news_extractor.py` + `news_schemas.py`), prompts (`prompts/{extract,news_extract,report,analyze_request,substance_match}_vN.md`), budget guard, rule-based fallback, eval CLI. |
| `alembic/versions/` | Migration chain `0001`→`0028` (`0022` logo, `0023` deals, `0024` escrow, `0025` offer sale fields, `0026` rfq push log, `0027` compliance, `0028` labs + samples); earlier: `0001`→`0021` (`0017` R1 verification/portal, `0018` R2 dual-origin requests/inquiries + `portal_notifications`, `0019` market-list index, `0020` R3 E-IMZO rails — `signature_evidence`/`company_person_data`/`integration_call_log`, `0021` R3 contracts). |

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
  `chem_registry_mode`) — separate from the immutable env/`config.py` contract. Read them via
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
