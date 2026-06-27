# CLAUDE.md — deploy/

Scoped guidance for `deploy/` (containers, nginx, backup). See the repo-root `CLAUDE.md`
for the big picture and `docs/deployment-guide.md` for the full first-run procedure.

## Layout

| Path | Role |
|------|------|
| `docker-compose.yml` | **Production** stack: postgres, redis, minio, api, worker, beat, userbot, dashboard, nginx (+ `webapp-build` one-shot, profile `build`). |
| `docker-compose.dev.yml` | **Dev** stack with source bind-mounts + live reload (no dashboard service). |
| `Dockerfile.dashboard` | Next.js standalone image (built from `../dashboard`). |
| `Dockerfile.webapp` | Vite build image for the Telegram Web App bundle. |
| `nginx/nginx.conf` | Prod TLS (443 + 80→443, letsencrypt). `nginx.behind-proxy.conf` | HTTP-only behind a TLS-terminating front door. `nginx.dev.conf` | dev HTTP-only. |
| `backup/pg_backup.sh` | pg_dump backup sidecar (14-daily/8-weekly retention); see `backup/README.md`. |
| `.env.example` | **Authoritative env contract** — every variable, with `[SECRET]` markers. |

(The backend image is built from `backend/Dockerfile`, not from this directory.)

## Key facts

- **`.env` location differs by environment**: dev compose + `make` read `../.env` relative to the
  compose file = the **repo root**; prod compose reads `../.env` = **one level above the repo root**.
  The real `.env` is gitignored; only `.env.example` is tracked.
- **No secret literals in compose** — secrets are interpolated `${VAR}` with no inline default, so a
  missing secret fails fast at the app layer (pydantic `Settings`). Prod has no weak dev defaults.
- **Migrations + seed run as pre-start steps** in the api `command` (`python -m app.entrypoint` +
  the idempotent seeders), not via the in-app lifespan, so `--reload`'s file watcher doesn't restart
  uvicorn mid-migration. (`RUN_MIGRATIONS_ON_STARTUP` stays available for no-reload/prod.)
- **Repo-root packages mounted read-only**: `../telegram` (api/worker/beat) and `../userbot`
  (userbot) are outside the backend build context, so compose mounts them into the containers.
- **Worker queues** must match: `-Q ingest,parse,notify,default` ↔ the Celery `task_queues`/`task_routes`.
- **nginx is the only externally-exposed service** (least privilege); everything else is reachable
  only on the internal docker network. The `userbot` is a separate long-lived service.
- **Web App bundle** is built separately into the `webapp_static` volume: `make webapp-bundle`
  (= `docker compose --profile build run --rm --build webapp-build`).

## Make targets (run from repo root)

```bash
make smoke          # production-compose smoke test (synthetic data + placeholder env)
make webapp-bundle  # build + load the Telegram Web App into the nginx-served volume
```
Both use `docker compose --env-file .env -f deploy/docker-compose.yml` — the `--env-file .env` is
required so Compose interpolates from the repo-root `.env`.
