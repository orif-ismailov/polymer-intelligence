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
| `app/tasks/` | Celery app (`celery_app.py`), beat schedule (`schedule.py`), task modules (ingest*/parse*/notify/reports/nightly_catchup/rescore/userbot_health/request_analysis). |
| `app/services/` | Business logic — **mypy-strict**, keep typed. Includes `news_service`, `news_dedup`, `report_service`, `settings_service`, `offer*/sourcing/request*`, and the R1 verification/portal set: `event_service`+`event_types` (transactional outbox), `otp_service`, `company_service`, `verification_service`+`verification_checks`, `rate_limit`, `crypto`; **R2** `notification_service` (in-portal notifications; kind-dedup; i18n key+params, never rendered text) with outbox consumers + the retention beat in `app/tasks/portal_notify.py`. |
| `app/schemas/` | Pydantic request/response models — **mypy-strict**. |
| `app/models/` | SQLAlchemy 2 ORM; `__init__.py` imports all in FK order for `Base.metadata`. Domains: signals, sources, requests, marketplace, sourcing, reports, app_settings, prices, alerts, reference, counterparties, staff. |
| `app/api/` | Routers; `app/api/webapp/` is the Telegram Web App surface (incl. `webapp/news.py`); `app/api/portal/` is the **client cabinet** — R1 `auth` (phone-OTP), `companies`, `offers` + **R2** `market`, `inquiries`, `requests`, `news` (webapp-news twin), `notifications` (auth via `deps.get_current_account`; company-scoped writes via `company_service.get_company_for` → 404 for non-members); `admin_verification.py` backs the staff verification queue; `admin_settings.py`/`reports.py`/`moderation.py` back the news + marketplace admin; `deps.py` holds RBAC guards. |
| `app/seed/` | Idempotent seeders (`seed_reference/staff/sources/demo`) + JSON in `data/`. |
| `parsing/` | LLM extractors (`extractor.py`, `news_extractor.py` + `news_schemas.py`), prompts (`prompts/{extract,news_extract,report,analyze_request}_vN.md`), budget guard, rule-based fallback, eval CLI. |
| `alembic/versions/` | Migration chain `0001`→`0018` (`0017` R1 verification/portal, `0018` R2 dual-origin requests/inquiries + `portal_notifications`). |

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
- **Prompts are immutable + versioned** across four families (`extract`, `news_extract`, `report`,
  `analyze_request`): change = new `parsing/prompts/<family>_v{N+1}.md` + bump its pin. The
  `extract`/`report`/`analyze_request` pins are env (`LLM_PROMPT_VERSION`, `REPORT_PROMPT_VERSION`,
  `REQUEST_AI_ANALYSIS_PROMPT_VERSION`); the `news_extract` version is a **runtime** app-setting
  (`news_prompt_version`), so it can be changed from the dashboard without a deploy. The resolved
  version is journaled in `parse_runs.prompt_version`.
- **Runtime settings** (`app/services/settings_service.py`, `app_settings` table) are operator-editable
  knobs (`news_ai_enabled`, `news_require_approval`, `report_auto_publish`, `llm_extract_model`,
  `news_prompt_version`, `news_refresh_interval_minutes`) — separate from the immutable env/`config.py`
  contract. Read them via `settings_service`, not `settings`.
- `raw_items` is **immutable** — `save_raw_items()` (`app/services/raw_pipeline.py`) inserts with
  `ON CONFLICT DO NOTHING`; never mutate existing rows.
- Domain exceptions drop the `Error` suffix (`BudgetExceeded`, `InvalidInitData`) — ruff `N818` off.
- `settings` is a single module-level instance — import it, never call `Settings()` again.
- The `telegram` and `userbot` packages live at the **repo root**, not under `backend/`; tests and
  the worker import them, and compose mounts them read-only into the backend image.
