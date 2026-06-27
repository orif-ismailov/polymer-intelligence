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
| `app/ingest/` | Source adapters (`<type>/adapter.py`) + `registry.py` + `base.py` Protocol + `http_client.py` (SSRF-guarded). |
| `app/tasks/` | Celery app (`celery_app.py`), beat schedule (`schedule.py`), task modules (ingest/parse/notify/…). |
| `app/services/` | Business logic — **mypy-strict**, keep typed. |
| `app/schemas/` | Pydantic request/response models — **mypy-strict**. |
| `app/models/` | SQLAlchemy 2 ORM; `__init__.py` imports all in FK order for `Base.metadata`. |
| `app/api/` | Routers; `app/api/webapp/` is the Telegram Web App surface; `deps.py` holds RBAC guards. |
| `app/seed/` | Idempotent seeders (`seed_reference/staff/sources/demo`) + JSON in `data/`. |
| `parsing/` | LLM extractor, prompts (`prompts/extract_vN.md`), budget guard, rule-based fallback, eval CLI. |
| `alembic/versions/` | Migration chain `0001`→`0005`. |

## Gotchas specific to this package

- **Adapters self-register at import time** into `app/ingest/registry.py`. Registration happens
  only in the process that imports the module — so each adapter is imported in BOTH `app/main.py`
  (API process: Test button, `GET /admin/source-types`) AND `app/tasks/ingest.py` (worker). A new
  adapter must be imported in both.
- **Celery task modules** must be listed in `_TASK_MODULES` in `celery_app.py` — autodiscover is a
  no-op here; an unlisted module = "unregistered task" at dispatch. Queues (`ingest/parse/notify/
  default`) and `task_routes` must stay in sync with the compose `-Q` flag.
- **New ORM model** → add it to `app/models/__init__.py` (FK order) or alembic's `env.py` won't see it.
- **Enums** in `app/models/enums.py` are `(str, Enum)`, not `StrEnum` (matches PG ENUMs verbatim;
  ruff `UP042` disabled).
- **Prompts are immutable + versioned**: change = new `parsing/prompts/extract_v{N+1}.md` + bump
  `LLM_PROMPT_VERSION`. The version is journaled in `parse_runs.prompt_version`.
- `raw_items` is **immutable** — `save_raw_items()` (`app/services/raw_pipeline.py`) inserts with
  `ON CONFLICT DO NOTHING`; never mutate existing rows.
- Domain exceptions drop the `Error` suffix (`BudgetExceeded`, `InvalidInitData`) — ruff `N818` off.
- `settings` is a single module-level instance — import it, never call `Settings()` again.
- The `telegram` and `userbot` packages live at the **repo root**, not under `backend/`; tests and
  the worker import them, and compose mounts them read-only into the backend image.
