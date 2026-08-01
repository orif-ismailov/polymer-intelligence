# Polymer Intelligence

Market-intelligence platform for Uzbekistan's domestic polymer market.
Collects, structures, and delivers market information to internal dashboard,
Telegram Web App, and Telegram bot/channel. It also runs a two-sided
marketplace (buyer requests/inquiries, seller offers) and an AI-classified
News Engine on top of that same signal core.

## Monorepo Layout

```
polymer-intelligence/
├── backend/          # FastAPI + Celery + SQLAlchemy 2 (Python 3.12, uv-managed)
│   ├── app/
│   │   ├── api/      # REST routers (staff, webapp, portal, public)
│   │   ├── core/     # config, db, logging, security, time
│   │   ├── models/   # SQLAlchemy 2 ORM models
│   │   ├── schemas/  # Pydantic request/response schemas
│   │   └── services/ # Business logic
│   └── tests/
├── dashboard/        # Next.js 16 (App Router) internal team dashboard
├── webapp/           # React + Vite Telegram Mini App (marketplace, news, request wizard)
├── portal/           # React + Vite (Feature-Sliced Design) client cabinet — cabinet.ai-imex.com
├── telegram/         # aiogram 3 bot (webhook + templates)
├── userbot/          # Telethon MTProto channel monitor (long-lived process)
├── workers/          # Standalone uzex_backfill crawler (own DB, own process)
├── deploy/           # docker-compose, nginx, backup scripts
└── docs/             # Dev spec, DB architecture, UI mockups, runbooks
```

Each component directory has its own scoped `CLAUDE.md` with directory-local commands, layout,
and gotchas: [`backend/CLAUDE.md`](backend/CLAUDE.md), [`dashboard/CLAUDE.md`](dashboard/CLAUDE.md),
[`webapp/CLAUDE.md`](webapp/CLAUDE.md), [`portal/CLAUDE.md`](portal/CLAUDE.md),
[`telegram/CLAUDE.md`](telegram/CLAUDE.md), [`userbot/CLAUDE.md`](userbot/CLAUDE.md),
[`deploy/CLAUDE.md`](deploy/CLAUDE.md).

## Quick Start (dev)

1. Copy the env contract and fill in secrets:

   ```bash
   cp deploy/.env.example .env
   # Edit .env — the real .env lives at the repo root and is gitignored
   ```

2. Bring up the dev stack:

   ```bash
   docker compose -f deploy/docker-compose.dev.yml up
   ```

3. Health check:

   ```bash
   curl http://localhost:8000/api/v1/health
   ```

## Key Endpoints

All routes are mounted under `/api/v1` (`backend/app/main.py`), spread across ~28 routers in
`backend/app/api/` — staff/admin endpoints, a dedicated `webapp/` sub-router for the Telegram
Mini App, a `portal/` sub-router for the client cabinet, and a `public.py` router for the
unauthenticated public marketplace surface. See [`docs/API.md`](docs/API.md) for the full
endpoint reference.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | DB + Redis health status |

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Celery, Redis (uv-managed)
- **Database**: PostgreSQL 16
- **Frontend**: Next.js 16 (App Router, dashboard), React + Vite (webapp — Telegram Mini App),
  React + Vite / Feature-Sliced Design (portal — client cabinet, SSR-rendered)
- **Messaging**: aiogram 3 (Telegram bot), Telethon (userbot, MTProto channel monitor)
- **Logging**: structlog JSON → stdout
- **Time**: UTC stored, Asia/Tashkent displayed

## Environment

All configuration is read from a `.env` file (see `deploy/.env.example`).
No secrets appear in tracked source code. See `backend/app/core/config.py`
for the full `Settings` class covering every documented env variable.

## Testing

```bash
cd backend
uv sync --frozen --extra dev
pytest tests/ -q                    # full backend suite (Postgres-backed in CI)

cd dashboard   # or webapp, or portal
npm ci
npm run lint
npm run typecheck
npm run e2e                          # Playwright
```

See [`docs/TESTING.md`](docs/TESTING.md) for the full breakdown of test types, coverage, and CI
gates.

## Documentation

- [`docs/GETTING-STARTED.md`](docs/GETTING-STARTED.md) — prerequisites, install, first run
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system overview and component relationships
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — local dev workflow, build commands, code style
- [`docs/TESTING.md`](docs/TESTING.md) — running and writing tests
- [`docs/API.md`](docs/API.md) — endpoint reference, auth, request/response formats
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — environment variables and config files
