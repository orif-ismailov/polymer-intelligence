<!-- generated-by: gsd-doc-writer -->
# Development

Day-to-day workflow for a developer already set up and making changes. For system design see
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md); for prerequisites and first boot see
[`docs/GETTING-STARTED.md`](GETTING-STARTED.md); for how to run and write tests see
[`docs/TESTING.md`](TESTING.md); for the full environment-variable contract see
[`docs/CONFIGURATION.md`](CONFIGURATION.md).

Each component also has its own scoped `CLAUDE.md` with directory-local commands and gotchas:
[`backend/CLAUDE.md`](../backend/CLAUDE.md), [`dashboard/CLAUDE.md`](../dashboard/CLAUDE.md),
[`webapp/CLAUDE.md`](../webapp/CLAUDE.md), [`portal/CLAUDE.md`](../portal/CLAUDE.md),
[`telegram/CLAUDE.md`](../telegram/CLAUDE.md), [`userbot/CLAUDE.md`](../userbot/CLAUDE.md),
[`deploy/CLAUDE.md`](../deploy/CLAUDE.md).

## CI gates

`.github/workflows/ci.yml` runs on every push/PR to `main` or `dev`. It has eight jobs; four of
them — `backend`, `dashboard`, `webapp`, `portal` — must pass before `build-images` runs (which
gates `deploy`/`deploy-dev`). Note that `dashboard-e2e` is **not** in the `build-images` `needs`
list, so a Playwright failure does not block an image build. Run the exact same commands locally
before pushing:

| Job | Working dir | Commands |
|---|---|---|
| **backend** | `backend/` | `ruff check .` → `mypy app/services --ignore-missing-imports` → `mypy app/schemas --ignore-missing-imports` → `pytest tests/ -q --tb=short` (against a real `postgres:16-alpine` service container) |
| **dashboard** | `dashboard/` | `npx eslint --max-warnings 0` → `npx next typegen` → `npx tsc --noEmit` |
| **dashboard-e2e** | `dashboard/` | Migrates + seeds a real Postgres, starts the API on `:8000`, then `npm run e2e` (Playwright against a live `next dev`) |
| **webapp** | `webapp/` | `npx eslint . --ext .ts,.tsx --max-warnings 0` → `npx tsc --noEmit` |
| **portal** | `portal/` | `npm run lint` → `npm run typecheck` → `npm run build` (vite) |
| **build-images** | — | Builds (and, on a real branch push, pushes to GHCR) all four runtime images; needs `backend`, `dashboard`, `webapp`, `portal` green |
| **deploy** / **deploy-dev** | — | SSH pull + `docker compose up -d` on push to `main` / `dev` respectively |

Pinned tool versions (do not bump without re-running the gates — see `backend/pyproject.toml`):

- `uv` **0.11.2** (`astral-sh/setup-uv@v5`), Python **3.12**
- `ruff==0.15.17`, `mypy==2.1.0` (both pinned as backend dev dependencies)
- Node **20** (`actions/setup-node@v4`) for `dashboard/`, `webapp/`, `portal/`
- `fastapi>=0.137,<0.138` / `starlette>=1.3,<1.4` — route registration is version-sensitive; do
  not widen these ceilings without re-running the full backend suite

CI supplies hardcoded placeholder values for every required env var (`JWT_SECRET`, `BOT_TOKEN`,
`WEBHOOK_SECRET`, `TG_API_ID`, `TG_API_HASH`, `ANTHROPIC_API_KEY`, `S3_ACCESS_KEY`,
`S3_SECRET_KEY`, `VERIFICATION_ENC_KEY`, etc.) so `Settings` never fails to construct — see
[`docs/CONFIGURATION.md`](CONFIGURATION.md) for the full contract and what's required vs.
optional.

## Backend workflow (uv)

All backend commands run **from `backend/`**:

```bash
uv sync --frozen --extra dev      # install the EXACT locked deps — uv.lock is authoritative
ruff check .                       # lint (config in backend/pyproject.toml)
mypy app/services --ignore-missing-imports
mypy app/schemas  --ignore-missing-imports
pytest tests/ -q                   # full suite
pytest tests/test_feed_api.py::test_name -q   # single test
pytest -k "telegram and not accuracy" -q      # by pattern
uv run uvicorn app.main:app --reload           # local API (needs DATABASE_URL/REDIS_URL + secrets)
alembic upgrade head                            # apply migrations (or app/entrypoint.py, advisory-locked)
```

`uv sync --frozen` fails on any lock drift — if you add/bump a dependency, edit
`backend/pyproject.toml` and regenerate `uv.lock` (`uv lock`), then commit both files.

Full-stack local dev (Postgres, Redis, MinIO, API, worker, beat, userbot, nginx) uses
`docker compose -f deploy/docker-compose.dev.yml up` — see
[`docs/GETTING-STARTED.md`](GETTING-STARTED.md) for the first-boot walkthrough. Repo-root
`make` targets orchestrate the full stack against the **production** compose file
(`deploy/docker-compose.yml`, requires `--env-file .env`, already baked into every target):

| Target | What it does |
|---|---|
| `make smoke` | Full-stack production-compose smoke test with synthetic data + placeholder env (`tests/smoke/test_smoke_full_stack.sh`) |
| `make webapp-bundle` | Builds the Telegram Web App and loads it into the nginx-served `webapp_static` volume |
| `make portal-bundle` | Rebuilds and restarts the portal SSR service (`portal` is a long-running Node process now, not a static bundle) |

## Code style

**Backend (ruff + mypy, `backend/pyproject.toml`):**

- `ruff check .` — line length 100, target `py312`, rule sets `E, F, I, N, UP, B, SIM`. Two rules
  are deliberately disabled:
  - `UP042` (prefer `StrEnum`) — domain enums in `app/models/enums.py` are declared `(str, Enum)`,
    not `StrEnum`, so they match their Postgres ENUM types verbatim; `StrEnum` would change
    `str(member)`/f-string output from `"SignalKind.NEWS"` to `"news"`, a behavior change this
    codebase avoids.
  - `N818` (exception names must end in `Error`) — domain exceptions are named without the
    `Error` suffix (e.g. `InvalidInitData`, `BudgetExceeded`); disabled to match that established
    convention rather than rename 50+ references across 12 files.
  - `E501` (line too long) is also off (line length is enforced structurally at 100 instead).
  - `flake8-bugbear`'s `B008` (no function calls in defaults) is narrowly relaxed via
    `extend-immutable-calls` for FastAPI's DI markers (`Depends`, `Query`, `Cookie`, `Body`,
    `Path`, `Form`, `File`, `HTTPBearer`) plus `app.api.deps.require_role` — not a blanket disable.
- `mypy --strict` is scoped to **`app/services` and `app/schemas` only** (the CI-gated scope) —
  the rest of the codebase (`app/api`, `app/models`, `parsing/`, task modules) is not type-checked
  in CI. Within that scope: `app.services.*` additionally sets `disallow_any_explicit = True`
  (with narrow, commented carve-outs for `alert_service`'s polymorphic JSONB predicate
  interpreter); `app.schemas.*` relaxes `disallow_any_explicit` (Pydantic's own internal stubs
  otherwise false-positive). `parsing.*` is exempted from errors entirely (`ignore_errors = True`)
  even when a gated service transitively imports it — a gated module's own bugs still fail the
  gate, but `parsing/`'s ungated issues can't leak in through the import.
- Run both together the same way CI does: `ruff check .` then the two scoped `mypy` invocations
  above — `mypy app/services` and `mypy app/schemas` are two separate commands, not one glob.

**Frontend (per app, no shared root config):**

- `dashboard/` — ESLint via `dashboard/eslint.config.mjs`, run with `npx eslint` (script:
  `npm run lint`) plus `npx tsc --noEmit` (script: `npm run typecheck`). No Prettier config in the
  repo.
- `webapp/` — ESLint via `webapp/.eslintrc.cjs`, run with `eslint . --ext ts,tsx
  --report-unused-disable-directives --max-warnings 0` (script: `npm run lint`) plus `tsc --noEmit`.
- `portal/` — ESLint via `portal/eslint.config.js` (script: `npm run lint`) plus `tsc --noEmit`
  (script: `npm run typecheck`); the build script (`npm run build`) is
  `tsc -b tsconfig.build.json && npm run build:client && npm run build:server` — a bare `tsc -b`
  on a `noEmit` composite project hits TS6310, hence the separate `tsconfig.build.json`.
- All three run `--max-warnings 0` — CI treats any lint warning as a failure, not just errors.
- None of the three apps ships a `.prettierrc*`/`biome.json`, and there is no repo-root
  `.editorconfig` — code style is enforced by ESLint + TypeScript alone.

## Adding things (backend)

**A new ingest adapter** — implement the `SourceAdapter` Protocol
(`backend/app/ingest/base.py`: `async fetch(source) -> list[RawItemDraft]`, `async
test(config) -> TestResult`) under `backend/app/ingest/<type>/adapter.py`. Adapters
**self-register at import time** into `backend/app/ingest/registry.py` — registration only
happens in the process that actually imports the module, so **it must be imported in both**:
- `backend/app/main.py` (verified: lines importing `app.ingest.cbu_rates`, `html_table`,
  `llm_page`, `rss`, `telegram_channel`, `uzex`, `xarid` at module scope) — the API process, so
  the dashboard "Test" button and `GET /admin/source-types` can resolve it.
- `backend/app/tasks/ingest.py` (verified: local imports of `app.ingest.uzex` and
  `app.ingest.xarid` inside their fetch tasks) — the worker process. Skipping either import means
  the worker (or the API) rejects the type as "No adapter registered."

**A new Celery task module** — must be added to `_TASK_MODULES` in
`backend/app/tasks/celery_app.py` (verified list: `ingest`, `ingest_cbu`, `ingest_llm_page`,
`ingest_html_table`, `ingest_rss`, `parse`, `parse_telegram`, `notify`, `userbot_health`,
`nightly_catchup`, `rescore`, `reports`, `events`, `verification`, `contracts`, `deals`,
`payments`, `rfq_push`, `portal_notify`). `autodiscover_tasks` is a no-op in this layout (it would
look for a nonexistent `app.tasks.tasks` module); an unlisted module fails at dispatch with
"unregistered task." New tasks must also be routed to one of the five queues (`ingest`, `parse`,
`notify`, `default`, `verify`) via `task_routes`, and the queue set must stay in sync with the
compose `-Q` flag in **both** `deploy/docker-compose.yml` and `deploy/docker-compose.dev.yml`.

**A new ORM model** — add the import to `backend/app/models/__init__.py`, respecting FK
dependency order (the file's own docstring documents the intended ordering: enums → reference →
sources → counterparties → staff → signals → requests → prices → alerts → reports, with later
domains such as companies/verification/contracts/deals/compliance/lab layered on top). Alembic's
`env.py` builds `target_metadata` from `Base.metadata`, which is only complete once every model
module has been imported here — a model left out is invisible to `alembic revision
--autogenerate`.

**A new alembic migration** — the chain currently runs `backend/alembic/versions/0001` through
`0034`. Generate with `alembic revision --autogenerate -m "..."` from `backend/` after your model
change, review the generated diff, and apply locally with `alembic upgrade head` (or let
`app/entrypoint.py` do it — it's advisory-locked and idempotent for concurrent workers/replicas).

**A new prompt version** — prompts under `backend/parsing/prompts/` are **immutable and
versioned**; never edit an existing `*_vN.md` file in place. To change a prompt, add
`prompts/<family>_v{N+1}.md` and bump the pin. Families on disk (verified):
`extract_v1.md`, `news_extract_v1.md`/`v2.md`/`v3.md`, `report_v1.md`–`v6.md`,
`analyze_request_v1.md`, `substance_match_v1.md`. Pin mechanism differs by family — `extract`
(`LLM_PROMPT_VERSION`), `report` (`REPORT_PROMPT_VERSION`), and `analyze_request`
(`REQUEST_AI_ANALYSIS_PROMPT_VERSION`) are env vars (see
[`docs/CONFIGURATION.md`](CONFIGURATION.md)); `news_extract` is instead selected at **runtime**
via the `news_prompt_version` app-setting, changeable from the dashboard without a redeploy. The
resolved version is journaled per-run in `parse_runs.prompt_version` so extraction is always
replayable against the exact prompt that produced a given signal.

## Frontend conventions

**`portal/`** — Vite/React 18/TypeScript (strict), built with **Feature-Sliced Design**. Verified
layer list under `portal/src/` (`app/`, `pages/`, `widgets/`, `features/`, `entities/`, `shared/`)
matches `portal/CLAUDE.md`'s documented layout. The FSD import rule is enforced by convention, not
tooling: a layer may only import from layers below it —
`shared ⇐ entities ⇐ features ⇐ widgets ⇐ pages ⇐ app` — and `shared/` must never import from
`entities/` (the fetch client stays business-agnostic via `shared/api/authBridge.ts`, which the
account store registers callbacks into at boot). The portal also has a **dual-render split**: the
public marketplace routes (`/`, `/market`, company directories, `/prices`, `/news`) are
server-rendered (`entry-server.tsx`) for SEO; everything behind login is a client-rendered app
shell (`entry-client.tsx`), because the access token lives in memory and the SSR process has no
session to render a cabinet page from. Dev runs `npm run dev` (SSR dev server on `:5173`);
production runs `npm start` (`node server.js` against a built `dist/`).

**`dashboard/`** — Next.js 16 **App Router** with `app/[locale]/...` and `next-intl`. The
`(dashboard)/` route group holds every authed page (signal side: feed, signals, offers, prices,
requests, sources, alerts; marketplace/sourcing: moderation, offer-requests, sourcing, partners,
inventory, intel, substances, lab-orders, lab-partners; news: reports, admin/news; plus
admin/users, admin/products); `login/` sits outside the group. `.next/types/routes.d.ts` is
gitignored and `next-env.d.ts` imports it, so `npx next typegen` must run before `tsc --noEmit` on
a clean checkout (CI's `dashboard` job does this explicitly as its own step, before typecheck).

**`webapp/`** — React 18 + Vite (plain Vite app, separate ESLint/tsconfig from `dashboard/`), runs
both inside Telegram (Mini App, `X-Telegram-Init-Data` auth) and standalone in a browser
(Telegram Login Widget → cookie session). Forms use react-hook-form + zod; wizard/role state lives
in zustand, not the URL/router.

## i18n: keeping locale files in sync

Each frontend app ships its own independent locale set — there is no shared translation
package. A missing key in one locale is a runtime error in that app, so every locale file within
an app must carry an identical key tree. Verified locale files on disk:

| App | Locales | Files |
|---|---|---|
| `dashboard/` | `ru` (primary), `uz`, `tr`, `fa`, `zh` — **no `en`** | `dashboard/messages/{ru,uz,tr,fa,zh}.json` |
| `webapp/` | `ru` (primary), `en`, `uz`, `tr`, `fa`, `zh` — `fa` is RTL | `webapp/src/i18n/{ru,en,uz,tr,fa,zh}.json` |
| `portal/` | `ru` (primary), `uz`, `en` — smaller, portal-launch set only | `portal/src/shared/i18n/locales/{ru,uz,en}.json` |

When adding a user-facing string, add the key to **every** locale file for that app in the same
change — a partially-translated key ships a broken string (or a runtime error) in whichever
locale you forgot.

## Branch conventions & PR process

There is no `.github/PULL_REQUEST_TEMPLATE.md`, `CONTRIBUTING.md`, or `.github/ISSUE_TEMPLATE/`
in this repository, so the conventions below are inferred from the actual git history rather than
a documented policy:

- **Two long-lived branches drive CI and deploy**: `main` (push → `deploy` job, production) and
  `dev` (push → `deploy-dev` job, the auto-deploying dev server). Both are also the two
  `pull_request` target branches CI runs against.
- **Feature/fix branches** observed in history follow `<type>/<short-description>` — e.g.
  `feat/imex-ai-landing-and-browser-auth`, `fix/landing-body-container`. Planning-only branches
  use `plan/...`.
- **Commit messages** consistently follow Conventional Commits with a scope, e.g.
  `feat(portal): manufacturer, logistics and laboratory company profiles`,
  `fix(portal-api): serve company logos through the API, not presigned S3`,
  `chore(seed): add showcase dataset for the demo environment`,
  `test: make the suite hermetic and unpin the migration head guard`. Match this style
  (`type(scope): summary`) for new commits.
- **Before opening a PR**, run the same commands CI runs for whichever component(s) you touched
  (see the CI gates table above) — a red CI run blocks `build-images` and therefore both deploy
  jobs.
- Merges into `redesign-architecture`/feature branches in this history went through GitHub PRs
  (`Merge pull request #19 from ...`); there is no further documented review-process policy beyond
  CI passing.
