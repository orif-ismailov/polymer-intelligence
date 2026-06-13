# Polymer Intelligence

Market-intelligence platform for Uzbekistan's domestic polymer market.
Collects, structures, and delivers market information to internal dashboard,
Telegram Web App, and Telegram bot/channel.

## Monorepo Layout

```
polymer-intelligence/
├── backend/          # FastAPI + Celery (Python 3.12)
│   ├── app/
│   │   ├── api/      # REST routers
│   │   ├── core/     # config, db, logging, security, time
│   │   ├── models/   # SQLAlchemy 2 ORM models
│   │   ├── schemas/  # Pydantic request/response schemas
│   │   └── services/ # Business logic
│   └── tests/
├── dashboard/        # Next.js 14+ internal dashboard (Phase 2+)
├── webapp/           # React + Vite Telegram Web App (Phase 3+)
├── deploy/           # docker-compose, nginx, backup scripts
└── docs/             # Dev spec, DB architecture, UI mockups
```

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

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | DB + Redis health status |

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Celery, Redis
- **Database**: PostgreSQL 16
- **Frontend**: Next.js 14+ (dashboard), React + Vite (Telegram Web App)
- **Logging**: structlog JSON → stdout
- **Time**: UTC stored, Asia/Tashkent displayed

## Environment

All configuration is read from a `.env` file (see `deploy/.env.example`).
No secrets appear in tracked source code. See `backend/app/core/config.py`
for the full `Settings` class covering every documented env variable.
