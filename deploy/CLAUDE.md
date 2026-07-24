# CLAUDE.md — deploy/

Scoped guidance for `deploy/` (containers, nginx, backup). See the repo-root `CLAUDE.md`
for the big picture and `docs/deployment-guide.md` for the full first-run procedure.

## Layout

| Path | Role |
|------|------|
| `docker-compose.yml` | **Production** stack: postgres, redis, minio (+ `minio-init`), api, worker, beat, dashboard, nginx. Opt-in profiles: `userbot` (profile `userbot`) and `webapp-build` (profile `build`). |
| `docker-compose.dev.yml` | **Dev** stack with source bind-mounts + live reload (no dashboard service; userbot still profile-gated). |
| `dev-compose.sh`, `env.dev-server.example` | Helper + env contract for the shared **dev-server** deployment (auto-pulls the `dev` branch; behind the host TLS front door on its own `dev.*` hostnames). |
| `Dockerfile.dashboard` | Next.js standalone image (built from `../dashboard`). |
| `Dockerfile.webapp` | Vite build image for the Telegram Web App bundle. |
| `Dockerfile.portal` | Vite build image for the client-cabinet portal bundle (R1). |
| `nginx/nginx.conf` | Prod TLS (443 + 80→443, letsencrypt). `nginx.behind-proxy.conf` | prod HTTP-only behind a TLS-terminating front door. `nginx.dev-server.behind-proxy.conf` | dev-server variant (`dev.*` hosts). `nginx.dev.conf` | local dev HTTP-only. `host-vhost.ai-imex{,-dev}.conf.example` | example host-side nginx vhosts for the behind-proxy topology. |
| `backup/pg_backup.sh` | pg_dump backup sidecar (14-daily/8-weekly retention); see `backup/README.md`. |
| `.env.example` | **Authoritative env contract** — every variable, with `[SECRET]` markers. |

(The backend image is built from `backend/Dockerfile`, not from this directory. The standalone
`workers/uzex_backfill` crawler is **not** part of any compose file — it runs under systemd/tmux; see
`workers/uzex_backfill/deploy/uzex-backfill.service.example`.)

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
- **Worker queues** must match: `-Q ingest,parse,notify,default,verify` ↔ the Celery
  `task_queues`/`task_routes`. Five queues: the News Engine (news fetch/parse, report generation,
  breaking-news publish) routes onto the four original queues via `task_routes` (no extra worker
  service); **R1 company verification adds `verify`** — `app.tasks.verification.*` runs there so a
  slow/dead external provider (gov registry, bank, E-IMZO) can't starve ingest/parse/notify.
  Extending the queue set means editing BOTH compose `-Q` flags (`docker-compose.yml`,
  `docker-compose.dev.yml`) in lockstep with `task_queues`.
- **nginx is the only externally-exposed service** (least privilege); everything else is reachable
  only on the internal docker network.
- **The `userbot` is opt-in** (`profiles: ["userbot"]`) — it does **not** start on a plain
  `docker compose up`. Bring it up explicitly (`--profile userbot up -d userbot`) only once a
  DEDICATED `TG_SESSION_STRING` exists, so two processes never share one session (AuthKeyDuplicated
  permanently kills it).
- **New env-var groups** in `.env.example` beyond the original Phase-6 contract (all with safe
  defaults except where noted): News Engine (`NEWS_CHANNEL_ID`), report/extraction models
  (`LLM_REPORT_MODEL`, `REPORT_PROMPT_VERSION`), buyer-request AI (`REQUEST_AI_ANALYSIS_*`,
  `REQUEST_NOTIFY_CHAT_ID`, `NOTIFY_TOPIC_BUYERS/SELLERS`), UZEX LLM fallback
  (`UZEX_LLM_FALLBACK_ENABLED`), and browser Web-App login (`BOT_USERNAME`, `CLIENT_SESSION_TTL_SECONDS`).
- **Client portal (R1)** is a Vite bundle in the `portal_static` volume: `make portal-bundle`
  (= `docker compose --profile build run --rm --build portal-build`). nginx serves it at the root
  of **cabinet.ai-imex.com** + proxies `/api/` → `api:8000` same-origin (server block in
  `nginx.behind-proxy.conf`). Prod needs DNS `cabinet.*` + a host cert (behind-proxy: host nginx
  terminates TLS → docker nginx :8080). New envs (R1): `VERIFICATION_ENC_KEY` (**secret**, ≥32
  urlsafe-b64 chars), `SMS_PROVIDER` (`console` dev / `eskiz` prod) + `ESKIZ_EMAIL`/`ESKIZ_PASSWORD`
  (secret, required when eskiz), `VERIFICATION_NOTIFY_CHAT_ID` (optional). Enforcement app-settings
  (`verification_auto_approve`, `bank_verification_required`, `verification_required_for_publish`)
  default OFF — R1 ships badge-only.
- **Web App bundle** is built separately into the `webapp_static` volume: `make webapp-bundle`
  (= `docker compose --profile build run --rm --build webapp-build`).

## Make targets (run from repo root)

```bash
make smoke          # production-compose smoke test (synthetic data + placeholder env)
make webapp-bundle  # build + load the Telegram Web App into the nginx-served volume
make portal-bundle  # build + load the client cabinet into the portal_static volume (cabinet.*)
```
Both use `docker compose --env-file .env -f deploy/docker-compose.yml` — the `--env-file .env` is
required so Compose interpolates from the repo-root `.env`.
