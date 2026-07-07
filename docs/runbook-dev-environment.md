# Runbook: Dev Environment (a prod-mirror stack alongside production)

**What this covers:** standing up a **second, fully-isolated copy of the production
stack on the same server**, so you can `git pull` a branch, test the whole system
end-to-end (dashboard, webapp, bot, userbot, ingest, LLM), and only then promote to
production. Nothing here touches the live prod stack, volumes, bot, or userbot.

**Isolation model — dev never collides with prod because:**

| Axis | Prod | Dev |
|------|------|-----|
| Compose project | `polymer-intelligence` (dir name) | `polymer-dev` (`-p` / `COMPOSE_PROJECT_NAME`) |
| Docker volumes | `polymer-intelligence_*` | `polymer-dev_*` (separate DB, MinIO, redis, webapp) |
| Repo checkout | `/opt/polymer/polymer-intelligence` | `/opt/polymer-dev/polymer-intelligence` |
| `.env` (repo root) | `…/polymer-intelligence/.env` | `…/polymer-dev/polymer-intelligence/.env` |
| Deployed branch | `main` (prod CI job) | `dev` (dev CI job) |
| Inner nginx port | `127.0.0.1:8080` | `127.0.0.1:8081` (`INNER_NGINX_PORT`) |
| Inner nginx conf | `nginx.behind-proxy.conf` | `nginx.dev-server.behind-proxy.conf` (`INNER_NGINX_CONF`) |
| Public domains | `ai-imex.com` / `admin.` / `api.` | `dev.ai-imex.com` / `dev-admin.` / `dev-api.` |
| Telegram bot | prod BotFather token | **separate** dev BotFather token |
| Userbot session | prod account session | **separate** account session |

The **same `deploy/docker-compose.yml`** drives both stacks — dev only overrides the
two nginx knobs (`INNER_NGINX_PORT`, `INNER_NGINX_CONF`) via its `.env`; every other
difference is achieved by the separate project name + separate `.env`. No compose fork,
so prod and dev never drift.

```
Internet ─HTTPS─▶ HOST nginx (one front-door, systemd)
   ├─ ai-imex.com / admin. / api.        → 127.0.0.1:8080  → PROD compose nginx → prod api/dashboard/webapp
   └─ dev.ai-imex.com / dev-admin. / dev-api. → 127.0.0.1:8081 → DEV compose nginx → dev  api/dashboard/webapp
```

---

## Prerequisites (collect before you start)

- [ ] **DNS control** for `ai-imex.com` to add three A-records (Phase 1).
- [ ] **A separate dev bot** created in [@BotFather](https://t.me/BotFather) — new
      token, and run `/setdomain` → `dev.ai-imex.com` for its Login Widget.
- [ ] **A separate Telegram account** for the dev userbot (a spare number). Same-account
      sessions running in two live userbots trigger `AUTH_KEY_DUPLICATED` and invalidate
      the session — do **not** reuse the prod userbot account.
- [ ] Docker Engine + Compose v2 and the host nginx + certbot are already installed
      (they are — prod uses them). No new host packages needed.
- [ ] Server has headroom for a second Postgres/Redis/MinIO/api/worker/beat/userbot/
      dashboard/nginx set (roughly doubles the stack's RAM/CPU footprint).

---

## Phase 1 — DNS (zero downtime)

At your DNS provider add three A-records → **the same server IP prod already uses**:

```
dev.ai-imex.com        A   <server-ip>
dev-admin.ai-imex.com  A   <server-ip>
dev-api.ai-imex.com    A   <server-ip>
```

Verify before continuing (so certbot's HTTP-01 challenge will pass in Phase 4):

```bash
dig +short dev.ai-imex.com dev-admin.ai-imex.com dev-api.ai-imex.com   # all → <server-ip>
```

---

## Phase 2 — Clone the dev checkout + write its `.env`

Give dev its own directory tree, separate from prod.

```bash
sudo mkdir -p /opt/polymer-dev && sudo chown "$USER":"$USER" /opt/polymer-dev
cd /opt/polymer-dev
git clone <YOUR_REPO_URL> polymer-intelligence
cd polymer-intelligence
git checkout dev        # the branch the dev environment tracks (see "Auto-deploy" below)

# Dev .env lives at the DEV REPO ROOT. Verified: both the compose per-service
# `env_file: ../.env` (relative to deploy/ → repo root) and `--env-file .env`
# (relative to CWD → repo root) read THIS one file, so it's a single source of truth.
cp deploy/env.dev-server.example .env
chmod 600 .env
$EDITOR .env
```

Fill every `[SECRET]` in the dev repo-root `.env`. Key points (full guidance is in the
file's comments):

- `COMPOSE_PROJECT_NAME=polymer-dev`, `INNER_NGINX_PORT=8081`,
  `INNER_NGINX_CONF=nginx.dev-server.behind-proxy.conf` — already set; leave them.
- Regenerate `POSTGRES_PASSWORD` (+ keep `DATABASE_URL` in sync), `JWT_SECRET` (≥32),
  `S3_ACCESS_KEY`/`S3_SECRET_KEY` — the dev data plane is brand new.
- `BOT_TOKEN`/`WEBHOOK_SECRET`/`BOT_USERNAME` — the **dev** bot.
- `TG_API_ID`/`TG_API_HASH`/`TG_SESSION_STRING` — the **dev** userbot account
  (generate the session string in Phase 5).
- Keep `LLM_DAILY_TOKEN_LIMIT` low (e.g. `100000`) so dev can't drain prod's budget.
- **Leave `PUBLIC_WEBAPP_URL` / `PUBLIC_API_URL` blank for the first bring-up** — with
  them blank the api skips webhook registration, so you can validate the stack before
  involving Telegram. You set them in Phase 5.

> All dev commands below use the wrapper `deploy/dev-compose.sh`, which pins
> `-p polymer-dev --env-file .env -f deploy/docker-compose.yml`. Run it from the dev
> repo root (`/opt/polymer-dev/polymer-intelligence`). Equivalent long form is shown
> once so you can see what it does.

---

## Phase 3 — Bring up the dev stack (Telegram still off)

```bash
cd /opt/polymer-dev/polymer-intelligence

# Everything EXCEPT the userbot (userbot needs its session string — Phase 5):
deploy/dev-compose.sh up -d \
  postgres redis minio minio-init api worker beat dashboard nginx
# (long form:)
# docker compose -p polymer-dev --env-file .env -f deploy/docker-compose.yml up -d \
#   postgres redis minio minio-init api worker beat dashboard nginx

# api auto-runs: alembic upgrade head → seed_reference → seed_staff → seed_sources
# (fresh seed, NO demo data — matches the prod api command).

# Build + load the Telegram Web App bundle into the DEV webapp_static volume:
deploy/dev-compose.sh --profile build run --rm --build webapp-build
```

Verify **internally**, before any DNS/TLS — fake the Host header against the dev inner
nginx on :8081:

```bash
# API health straight from the dev api container:
deploy/dev-compose.sh exec api curl -s http://localhost:8000/api/v1/health
# → {"status":"ok","db":"ok","redis":"ok"}

# Whole dev inner chain (host:8081 → dev nginx → api), routed by Host header:
curl -s -H "Host: dev-api.ai-imex.com" http://127.0.0.1:8081/api/v1/health
# → {"status":"ok",...}

# Dashboard + webapp reachability through the dev inner nginx:
curl -sI -H "Host: dev-admin.ai-imex.com" http://127.0.0.1:8081/ | head -1   # 200/307
curl -sI -H "Host: dev.ai-imex.com"       http://127.0.0.1:8081/ | head -1   # 200

# Confirm dev is isolated from prod (separate volumes, both stacks listed):
docker volume ls | grep -E 'polymer-dev_|polymer-intelligence_'
deploy/dev-compose.sh ps
```

If health is `ok`, the dev stack is up and serving on `127.0.0.1:8081`, fully separate
from prod on `:8080`.

---

## Phase 4 — Host front-door vhost for the dev domains + TLS

Add the dev vhost **alongside** the existing prod `ai-imex.conf` (do not touch prod's).

```bash
sudo cp /opt/polymer-dev/polymer-intelligence/deploy/nginx/host-vhost.ai-imex-dev.conf.example \
        /etc/nginx/sites-available/ai-imex-dev.conf
sudo ln -sf /etc/nginx/sites-available/ai-imex-dev.conf \
            /etc/nginx/sites-enabled/ai-imex-dev.conf
sudo nginx -t && sudo systemctl reload nginx
```

> If `nginx -t` fails with `could not build server_names_hash ...`, bump the bucket in
> the **main** `/etc/nginx/nginx.conf` `http { }` block (same fix prod needed):
> `server_names_hash_bucket_size 64;` then `sudo nginx -t && sudo systemctl reload nginx`.

Issue certs for the three dev domains (DNS from Phase 1 must already resolve here):

```bash
sudo certbot --nginx -d dev.ai-imex.com -d dev-admin.ai-imex.com -d dev-api.ai-imex.com
# certbot rewrites the dev vhost in place: listen 443 ssl, cert paths, 80→443 redirect
sudo systemctl reload nginx
```

Verify over TLS:

```bash
curl -s https://dev-api.ai-imex.com/api/v1/health   # → {"status":"ok",...}
```

---

## Phase 5 — Enable Telegram for the dev bot + userbot

**5.1 — Generate the dev userbot session** (once, using the separate dev account):

```bash
cd /opt/polymer-dev/polymer-intelligence
# Interactive login for the DEV account → prints a StringSession. Paste it into
# the dev repo-root .env as TG_SESSION_STRING. (See userbot/CLAUDE.md for details.)
python userbot/session.py        # or run inside a container per userbot docs
```

**5.2 — Set the dev public URLs and (re)start api + userbot:**

```bash
# In the dev repo-root .env set:
#   PUBLIC_WEBAPP_URL=https://dev.ai-imex.com
#   PUBLIC_API_URL=https://dev-api.ai-imex.com
# Then recreate api (registers the DEV bot webhook + menu button) and start userbot:
deploy/dev-compose.sh up -d api userbot

# Watch the dev webhook register (URL masks the secret):
deploy/dev-compose.sh logs -f api | grep -i webhook
# look for: setup_webhook.start / lifespan.telegram_webhook_registered
```

Because this is a **different bot token** and a **different userbot account**, none of
this affects prod's webhook or prod's userbot session.

---

## Phase 6 — Verify the dev environment end-to-end

- [ ] `https://dev-api.ai-imex.com/api/v1/health` → `{"status":"ok","db":"ok","redis":"ok"}`
- [ ] `https://dev-admin.ai-imex.com` loads; log in with a seeded staff account, then
      rotate that password in dev.
- [ ] `https://dev.ai-imex.com` serves the Telegram Web App bundle.
- [ ] The **dev bot** replies to `/start` and opens the Web App button (dev webhook live).
- [ ] Dev **userbot heartbeat** is fresh (no `check_userbot_health` alert), and only the
      dev userbot runs on the dev account.
- [ ] `deploy/dev-compose.sh ps` shows api/worker/beat/userbot/dashboard/nginx Up.
- [ ] Prod is untouched: `https://api.ai-imex.com/api/v1/health` still `ok`, and
      `docker compose -f deploy/docker-compose.yml ps` (from the prod checkout) unchanged.

---

## Auto-deploy from `dev` (CI)

Once the one-time setup below is done, the flow is:

```
push/merge → dev ─▶ CI gates (backend·dashboard·webapp·build-images) ─▶ deploy-dev job ─▶ DEV server
merge dev → main  ─▶ CI gates                                         ─▶ deploy job     ─▶ PROD server
```

The `deploy-dev` job (in `.github/workflows/ci.yml`) mirrors the prod `deploy` job:
it only runs on **push to `dev`**, only **after the gates pass**, then SSHes to the
**same server** and, in the **dev** checkout, runs `git reset --hard origin/dev` +
`dev-compose.sh up -d --build` + rebuilds the webapp bundle + restarts the dev nginx.

**One-time setup to enable it:**

1. **Create the `dev` branch** (CI already triggers on it):
   ```bash
   git checkout -b dev && git push -u origin dev
   ```
2. **The dev checkout must be a clean git repo** at `DEV_DEPLOY_PATH` on the server
   (Phase 2 did this) — the job does `git reset --hard origin/dev`, so keep no
   uncommitted changes there. `.env` is gitignored, so it survives the reset.
3. **Add the one new GitHub Actions secret** (Settings → Secrets and variables →
   Actions). The job reuses all the prod `DEPLOY_*` secrets (same server), and adds:

   | Secret | Value | Notes |
   |--------|-------|-------|
   | `DEV_DEPLOY_PATH` | `/opt/polymer-dev/polymer-intelligence` | Dev checkout path. Optional — the job falls back to this default if unset. |

   Reused as-is: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`,
   `DEPLOY_SSH_PASSPHRASE`, `DEPLOY_PORT`.

4. Complete the **first** dev bring-up manually (Phases 3–5) so `.env`, TLS, the dev
   bot webhook, and the userbot session exist. After that, `dev` pushes redeploy
   the code automatically; the job never edits `.env` or re-issues certs.

**Day-to-day:** branch off `dev`, open a PR (CI gates run), merge to `dev` →
dev redeploys within a couple of minutes → verify on the `dev.*` domains → when happy,
open `dev → main` and merge → prod redeploys via the existing `deploy` job.

**Manual override** (deploy a branch to dev without going through `dev`):

```bash
cd /opt/polymer-dev/polymer-intelligence
git fetch origin && git checkout <branch>
deploy/dev-compose.sh up -d --build
deploy/dev-compose.sh --profile build run --rm --build webapp-build   # if webapp changed
```

Notes:
- Dev seeds the **same source catalog** as prod, so the dev worker/userbot actively
  ingest from real sources. That's intended (true mirror). If you want dev quiet,
  disable individual sources in the dev dashboard.
- Schema changes: dev's api runs `alembic upgrade head` on every start, so a new
  migration is applied to the dev DB automatically on each deploy — exactly the
  rehearsal you want before it hits prod.
- The `deploy-dev` and prod `deploy` jobs are gated on separate branches and use
  separate compose projects/paths, so a `dev` deploy never touches prod.

---

## Teardown / reset

```bash
cd /opt/polymer-dev/polymer-intelligence

# Stop dev (keeps volumes/data):
deploy/dev-compose.sh down

# Wipe dev completely (removes the dev DB/MinIO/redis/webapp volumes — prod untouched):
deploy/dev-compose.sh down -v

# Remove the host front-door dev vhost:
sudo rm -f /etc/nginx/sites-enabled/ai-imex-dev.conf
sudo nginx -t && sudo systemctl reload nginx
```

Stopping/removing the dev userbot also frees the dev account's session and removes the
dev bot's webhook only for the **dev** bot — prod is never affected.

---

## Related docs

- Prod first-run + secrets matrix → [`deployment-guide.md`](./deployment-guide.md)
- Prod topology / cutover (same two-nginx shape) → [`runbook-server-migration.md`](./runbook-server-migration.md)
- Container/nginx specifics → [`../deploy/CLAUDE.md`](../deploy/CLAUDE.md)
- Dev `.env` contract → [`../deploy/env.dev-server.example`](../deploy/env.dev-server.example)

*Placeholder values only. The real `.env` is never committed.*
