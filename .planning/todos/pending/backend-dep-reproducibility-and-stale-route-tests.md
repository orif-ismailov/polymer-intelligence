---
created: 2026-06-18
title: Backend dependency reproducibility + 2 stale route-introspection tests
area: tooling
files:
  - backend/pyproject.toml
  - backend/uv.lock
  - backend/tests/test_prices_api.py:219
  - backend/tests/test_source_wizard.py:498
  - backend/app/api/main? (no change needed)
---

## Problem

Discovered during Phase 5 (telegram-monitoring-ai) execution, post-merge gate for Wave 2.

The backend has **no committed `uv.lock`** and pins `fastapi>=0.111.0` with **no upper bound**. A fresh `uv sync` therefore resolves transitive deps to the latest available — currently **FastAPI 0.137.2 + Starlette 1.3.1**. This is non-reproducible: different machines/CI runs can resolve different, potentially-incompatible versions.

Two consequences observed under the fresh resolve:

1. **Starlette 1.x changes how `app.routes` is represented.** Two pre-existing tests introspect mounted routes with `getattr(r, "path", "")` over `app.routes`:
   - `tests/test_prices_api.py::TestPricesApiRoutes::test_prices_path_mounted` (line ~219)
   - `tests/test_source_wizard.py::test_sources_router_mounted` (line ~498)

   Under Starlette 1.3.1 these find only the 2 inline demo routes and FAIL — **but the application is functionally intact**: every endpoint test passes (e.g. `test_prices_api.py` 8/8 endpoint tests green; routes resolve correctly via `TestClient`). The failure is stale test introspection, not broken routing.

2. With older FastAPI in the pinned range (0.111.0 / 0.115.x) `create_app()` instead asserts during route registration ("Status code 204 must not have a response body") — a different failure mode. So **no single version in the current allowed range is clean** without either fixing the tests or pinning deliberately.

These failures are **orthogonal to Phase 5** — `app/main.py`, all `app/api/*` routers, and both test files were untouched by the phase (verified via `git diff 7f7f687..HEAD -- app/`). All 103 Phase-5 tests pass. Phase 5 shipped green; this item was deferred by user decision (continue + record finding).

## Solution

TBD — recommended:
1. **Commit a `backend/uv.lock`** (and run CI via `uv sync --frozen`) so the environment is reproducible. Today `uv.lock` is neither tracked nor gitignored.
2. **Add a FastAPI/Starlette ceiling** in `backend/pyproject.toml` (e.g. pin to the known-good line the app was developed against, or `starlette<1.0`) until the route-introspection tests are modernized.
3. **Modernize the 2 route-mount tests** to introspect routes in a Starlette-1.x-compatible way (or assert via `TestClient` responses instead of walking `app.routes`).
4. Re-run the full backend suite to confirm a fully-green baseline.
