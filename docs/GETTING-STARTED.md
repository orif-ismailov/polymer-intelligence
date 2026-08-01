<!-- generated-by: gsd-doc-writer -->
# Getting Started

This guide gets a developer with repo access from a fresh clone to a running local stack.
For the full environment-variable reference see [`docs/CONFIGURATION.md`](CONFIGURATION.md);
for the system design see [`docs/ARCHITECTURE.md`](ARCHITECTURE.md). This doc only covers
what is needed to boot the stack for the first time.

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| [Docker](https://docs.docker.com/get-docker/) + Docker Compose v2 | any recent release (`docker compose` v2 CLI) | Runs Postgres, Redis, MinIO, the API, Celery worker/beat, and nginx. |
| [Python](https://www.python.org/) | `>=3.12` (pinned in `backend/pyproject.toml`, CI uses `3.12`) | Only needed if you run the API outside Docker (`uv run uvicorn ...`) or the backend test suite locally. |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | any recent release (CI pins the GitHub Action to `0.11.2`) | Manages the backend's Python environment; `uv.lock` is authoritative. |
| [Node.js](https://nodejs.org/) | `20.x` (pinned via `NODE_ENV`/`NODE_VERSION: "20"` in `.github/workflows/ci.yml`; no `.nvmrc` in the repo) | Runs `dashboard/`, `webapp/`, and `portal/` — each has its own `package.json`. |
| `git` | any | Clone the repo. |

You do **not** need Postgres, Redis, or MinIO installed locally — the dev Docker Compose
stack provides all three.

## 1. Clone and set up the environment file

```bash
git clone <repo-url> polymer-intelligence
cd polymer-intelligence
cp deploy/.env.example .env
```

The real `.env` lives at the **repo root** (this matches where `deploy/docker-compose.dev.yml`
and the `make` targets read it from) and is gitignored — only `deploy/.env.example` is tracked.

Open `.env` and fill in the required secrets. The full variable reference — required vs.
optional, defaults, and validation rules — lives in
[`docs/CONFIGURATION.md`](CONFIGURATION.md) and in `backend/app/core/config.py` (`Settings`).
For a first local boot, at minimum set:

- `JWT_SECRET` — any string ≥ 32 characters (staff auth signing secret).
- `VERIFICATION_ENC_KEY` — a Fernet key ≥ 32 characters. Generate one with:
  ```bash
  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- `BOT_TOKEN`, `WEBHOOK_SECRET` — Telegram bot credentials (a placeholder value is enough to
  boot the API; real values are only needed to actually receive Telegram traffic).
- `ANTHROPIC_API_KEY` — required for `Settings` to construct at all; a placeholder key lets
  the API start, but LLM extraction/report calls will fail until a real key is set.
- `TG_API_ID`, `TG_API_HASH` — required for `Settings` to construct; the userbot process
  itself is not part of the dev Compose stack, so a placeholder is enough here too.

`docker-compose.dev.yml` supplies safe fallback defaults for the infra credentials
(`POSTGRES_PASSWORD`, `S3_ACCESS_KEY`/`S3_SECRET_KEY`) so a bare copy of `.env.example` still
boots those services even before you touch it.

`deploy/.env.example` is missing a few variable groups that exist in `Settings` but have not
yet been appended to the tracked file (E-IMZO, `ESCROW_WEBHOOK_SECRET`, `OTP_DEV_CODE`) — see
[`docs/CONFIGURATION.md`](CONFIGURATION.md) for the authoritative list and current defaults if
you need one of those for local work.

## 2. Bring up the backend stack

```bash
docker compose -f deploy/docker-compose.dev.yml up
```

This starts: `postgres` (16-alpine), `redis` (7-alpine), `minio` (S3-compatible file storage),
`api` (FastAPI/uvicorn with `--reload`), `worker` (Celery, queues
`ingest,parse,notify,default,verify`), `beat` (Celery scheduler), and `nginx` (HTTP-only
reverse proxy on port 80). The `userbot` and `dashboard` services are **not** part of this
dev scaffold — the dashboard runs separately via `npm run dev` (step 4), and the userbot is
profile-gated (`--profile userbot up -d userbot`) since it needs a dedicated
`TG_SESSION_STRING`.

Ports published to the host:

| Service | Host port |
|---|---|
| `nginx` | `80` |
| `api` | `8000` |
| `postgres` | `5432` |
| `redis` | `6379` |
| `minio` | `9000` (S3 API), `9001` (console) |

## 3. Migrations and seed data

You do not need to run these manually — the `api` service's startup command applies the
schema and seeds reference data automatically, every time the container starts
(`deploy/docker-compose.dev.yml`, `api.command`):

```bash
python -m app.entrypoint \
  && python -m app.seed.seed_reference \
  && python -m app.seed.seed_staff \
  && python -m app.seed.seed_contract_templates \
  && python -m app.seed.seed_substances \
  && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- `app.entrypoint` runs `alembic upgrade head` under a Postgres advisory lock
  (`backend/app/entrypoint.py`), so concurrent container starts never race on DDL.
- The four seed steps are idempotent (`ON CONFLICT` inserts) — safe to re-run on every
  restart. They populate reference/synonym data, a staff login, the default contract
  template, and the chemical-substance reference list.
- Additional seed modules exist under `backend/app/seed/` for demo/showcase data
  (`seed_demo.py`, `seed_showcase*.py`) but are **not** run automatically by the dev stack —
  run them manually inside the `api` container if you want sample signals/offers/news to
  populate the feed:
  ```bash
  docker compose -f deploy/docker-compose.dev.yml exec api python -m app.seed.seed_demo
  ```

If you're running the API outside Docker (`uv run uvicorn app.main:app --reload` from
`backend/`), run the same steps manually first with `uv run python -m app.entrypoint` etc.,
against a `DATABASE_URL` you provide.

## 4. First health check

Once `docker compose up` reports the `api` service healthy:

```bash
curl http://localhost:8000/api/v1/health
```

or, through the nginx dev proxy:

```bash
curl http://localhost/api/v1/health
```

Both should return a `200` with a JSON body reporting DB and Redis status. The `nginx` dev
config (`deploy/nginx/nginx.dev.conf`) has no dashboard upstream — a plain `curl
http://localhost/` returns `dev stack up` as a plaintext liveness check rather than
redirecting anywhere.

## 5. Run the frontends

Each frontend is a separate app with its own `package.json` and is **not** started by the
Docker Compose dev stack — run the one(s) you need from a separate terminal:

```bash
# Dashboard (internal staff UI) — proxies /api/* to http://localhost:8000 in dev
cd dashboard
npm ci
npm run dev          # http://localhost:3000 (Next.js default)

# Webapp (Telegram Mini App / browser) — proxies /api to http://localhost:8000
cd webapp
npm ci
npm run dev           # http://localhost:5173 (vite.config.ts pins port 5173)

# Portal (client cabinet + public storefront, SSR) — proxies /api to http://127.0.0.1:8000
cd portal
npm ci
npm run dev           # http://localhost:5173 (server.js: PORT=5173 in the dev script)
```

`webapp` and `portal` both default to port `5173` — run only one at a time, or override
`PORT`/the vite `server.port` if you need both simultaneously.

## Where each surface is reachable (local dev)

| Surface | URL | Notes |
|---|---|---|
| API (direct) | `http://localhost:8000/api/v1/...` | FastAPI, `--reload` enabled, bind-mounted source. |
| API (through nginx) | `http://localhost/api/v1/...` | Dev nginx proxies `/api/` to the `api` container. |
| API docs (Swagger/ReDoc) | `http://localhost:8000/docs`, `/redoc` | Only mounted when `DEBUG=true` in `.env`. |
| MinIO console | `http://localhost:9001` | Login with `S3_ACCESS_KEY`/`S3_SECRET_KEY` (defaults `minioadmin`/`minioadmin` under dev compose). |
| Dashboard | `http://localhost:3000` | Run separately with `npm run dev` in `dashboard/`. |
| Webapp | `http://localhost:5173` | Run separately with `npm run dev` in `webapp/`; also loads as a plain browser page, not just inside Telegram. |
| Portal | `http://localhost:5173` | Run separately with `npm run dev` in `portal/`; SSR dev server via Vite middleware. |

## Troubleshooting

- **`Settings` fails to construct / API container exits immediately on boot** — a required
  env var is missing or fails validation (`JWT_SECRET`/`VERIFICATION_ENC_KEY` under 32
  characters, `OTP_DEV_CODE` not exactly 6 digits, `SMS_PROVIDER=eskiz` without
  `ESKIZ_EMAIL`/`ESKIZ_PASSWORD`, etc.). Check the `api` container logs
  (`docker compose -f deploy/docker-compose.dev.yml logs api`) — `Settings` fails fast with a
  clear validation error rather than starting in a broken state. See
  [`docs/CONFIGURATION.md`](CONFIGURATION.md) for the full validation list.
- **`docker compose up` succeeds but `/api/v1/health` never turns healthy** — the `api`
  healthcheck depends on `postgres` and `redis` reporting healthy first
  (`depends_on: condition: service_healthy`); a slow-starting Postgres volume on first boot
  is the most common cause. Give it a few extra seconds and re-check
  `docker compose -f deploy/docker-compose.dev.yml ps`.
- **`npm ci` fails inside a container with an `@emnapi` mismatch, but works on your host** —
  a known drift between npm 10 and npm 11 lockfile formats in this repo. If you need to
  regenerate a frontend lockfile, do it with `npx npm@10 install` rather than a newer local
  npm.

## Next steps

- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — system overview, data flow, and component
  relationships.
- [`docs/CONFIGURATION.md`](CONFIGURATION.md) — the full environment-variable and
  runtime-settings reference.
- [`docs/DEVELOPMENT.md`](DEVELOPMENT.md) — local development workflow, build commands, and
  code style.
- [`docs/TESTING.md`](TESTING.md) — running and writing tests.
- Each component also has its own scoped `CLAUDE.md` with directory-local commands and
  gotchas: `backend/CLAUDE.md`, `dashboard/CLAUDE.md`, `webapp/CLAUDE.md`, `portal/CLAUDE.md`,
  `telegram/CLAUDE.md`, `userbot/CLAUDE.md`, `deploy/CLAUDE.md`.
