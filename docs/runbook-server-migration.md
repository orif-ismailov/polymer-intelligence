# Runbook: Server Migration (fresh stand-up on a new Ubuntu server)

**Scenario this covers:** move the production deployment to a **new Ubuntu server**,
**keeping the same domain** (`ai-imex.com` + `admin.` + `api.`), by standing up a
**fresh stack from scratch** — *no database or object-storage migration*.

> ⚠️ **This is a from-scratch deploy — existing data does NOT carry over.**
> On day one the new server has only the seeded reference/staff/source catalog
> (`seed_reference`, `seed_staff`, `seed_sources`). All previously collected
> **signals, raw_items, client requests, and uploaded files are left behind on the
> old server.** If you later decide you want that data, stop and follow
> [`runbook-backup-restore.md`](./runbook-backup-restore.md) instead — this runbook
> assumes you accepted a clean slate.

**Related docs (do not duplicate — follow the links):**
- First-run details, secrets matrix, Telegram/userbot setup → [`deployment-guide.md`](./deployment-guide.md)
- Restore-from-dump (the *other* migration path) → [`runbook-backup-restore.md`](./runbook-backup-restore.md)
- Container/nginx/backup specifics → [`../deploy/CLAUDE.md`](../deploy/CLAUDE.md)

---

## Production topology you must reproduce

```
Internet ─HTTPS─▶ HOST nginx (installed on the Ubuntu box; certbot --nginx)
                   terminates TLS for ai-imex.com / www / admin. / api.
                      │  proxy_pass http://127.0.0.1:8080   (Host header preserved)
                      ▼
                  Docker "nginx" service  (nginx.behind-proxy.conf, HTTP-only, 127.0.0.1:8080)
                      │  routes by Host header
        ┌─────────────┼──────────────────┐
   dashboard         api            webapp_static  (landing + Telegram Web App)
   admin.ai-imex     api.ai-imex    ai-imex.com / www
```

Two nginx layers: the **host** nginx (TLS, from
`deploy/nginx/host-vhost.ai-imex.conf.example`) and the **inner** Docker nginx
(`nginx.behind-proxy.conf`, published only on `127.0.0.1:8080`). The compose stack
exposes **no** other host ports — postgres/redis/minio/api/dashboard are internal-only.

---

## The two hard cutover rules

1. **Only one userbot may hold the Telegram session at a time.** The userbot logs in
   with `TG_SESSION_STRING` (MTProto). Running the *same* session string from two
   processes simultaneously can trigger `AUTH_KEY_DUPLICATED` and **invalidate the
   session**. → **Stop the old userbot before starting the new one.**
2. **The Telegram webhook is a single global setting on the bot.** Whichever `api`
   last called `setup_webhook()` wins. As long as the domain is unchanged the URL is
   identical, so the new `api` simply re-registers the same URL — harmless — but don't
   leave both `api` services live for long, and do the DNS flip in the window below.

---

## Phase 0 — Pre-flight (do this a day ahead, zero downtime)

- [ ] **Lower DNS TTL** on the `A` records for `ai-imex.com`, `www.ai-imex.com`,
      `admin.ai-imex.com`, `api.ai-imex.com` to **300s** (or the minimum your DNS
      provider allows). This shrinks the cutover propagation gap. Do NOT change the
      IPs yet — only the TTL.
- [ ] **Collect the secrets to REUSE verbatim** from the old server's `.env`
      (it lives **one level above the repo root**). See the reuse table in the
      Appendix — the Telegram/Anthropic/domain values must match.
- [ ] Note the **git ref currently deployed** on the old box (normally `main`) — the
      new box must check out the same ref so the schema/seed match.
- [ ] Pick a low-traffic **maintenance window** for the cutover (Phase 5). Expect a
      few minutes of downtime plus the DNS-propagation + certbot gap.

---

## Phase 1 — Provision the new Ubuntu server (zero downtime; old box still live)

Everything here happens on the **new** server while the old one keeps serving.

```bash
# 1. A non-root sudo user + firewall (only 22/80/443 externally)
sudo adduser deploy && sudo usermod -aG sudo deploy
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
# Note: the Docker nginx binds 127.0.0.1:8080 only, so it is never exposed publicly.

# 2. Docker Engine + Compose v2 plugin (official convenience script)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy          # log out/in for group to take effect
docker compose version                   # must show Compose v2.x

# 3. Host nginx + certbot (the TLS front door)
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx make

# 4. Clone the repo and check out the deployed ref
sudo mkdir -p /opt/polymer && sudo chown deploy:deploy /opt/polymer
cd /opt/polymer
git clone <YOUR_REPO_URL> polymer-intelligence
cd polymer-intelligence
git checkout main          # the same ref the old server runs
```

---

## Phase 2 — Configure `../.env` (still zero downtime)

The prod stack reads `.env` from **one level above the repo root**
(`/opt/polymer/.env`), **not** `deploy/.env`.

```bash
cp /opt/polymer/polymer-intelligence/deploy/.env.example /opt/polymer/.env
chmod 600 /opt/polymer/.env
# then edit /opt/polymer/.env
```

Fill in every `[SECRET]`. `deploy/.env.example` is the authoritative contract; use the
Appendix table to decide **reuse vs. regenerate**. Two must-not-forget items:

- Set `DATABASE_URL` to embed the **new** `POSTGRES_PASSWORD` you generate.
- **Leave `PUBLIC_WEBAPP_URL` BLANK for now.** With it blank, `api` startup skips
  `setup_webhook()` — so pre-staging the stack does **not** steal the bot from the old
  server. You set the real value at cutover (Phase 5).

---

## Phase 3 — Pre-stage the stack with Telegram disabled (zero downtime)

Bring up everything **except the userbot**, and with the webhook still disabled
(`PUBLIC_WEBAPP_URL` blank from Phase 2). This validates DB migrate+seed, the API, the
dashboard, and the inner nginx routing — all without touching the live bot/userbot.

```bash
cd /opt/polymer/polymer-intelligence

# Bring up core services, NOT userbot (it must not run while the old one is live)
docker compose -f deploy/docker-compose.yml up -d \
  postgres redis minio minio-init api worker beat dashboard nginx
# api auto-runs: alembic upgrade head → seed_reference → seed_staff → seed_sources

# Build + load the Telegram Web App bundle into the webapp_static volume
make webapp-bundle
```

Verify **internally** (no DNS/TLS yet — test the inner nginx by faking the Host):

```bash
# API health straight from the container
docker compose -f deploy/docker-compose.yml exec api \
  curl -s http://localhost:8000/api/v1/health
# → {"status":"ok","db":"ok","redis":"ok"}

# Whole inner chain (host:8080 → docker nginx → api), routed by Host header
curl -s -H "Host: api.ai-imex.com" http://127.0.0.1:8080/api/v1/health
```

If both return `ok`, the fresh stack is healthy and ready to receive traffic.

---

## Phase 4 — Install the host nginx front door (zero downtime; HTTP only for now)

```bash
sudo cp /opt/polymer/polymer-intelligence/deploy/nginx/host-vhost.ai-imex.conf.example \
        /etc/nginx/sites-available/ai-imex.conf
sudo ln -sf /etc/nginx/sites-available/ai-imex.conf /etc/nginx/sites-enabled/ai-imex.conf
# If the default site is in the way:
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Certs are **not** issued yet — `certbot --nginx` uses an HTTP-01 challenge that needs
the domain resolving to *this* box, which only happens after the DNS flip in Phase 5.

---

## Phase 5 — Cutover (the maintenance window)

Do these **in order**. This is the only step with downtime.

```
1. STOP the old server's stack   (frees the userbot session + releases the webhook)
2. FLIP DNS to the new IP         (all four A records)
3. ENABLE Telegram on the new box (set PUBLIC_WEBAPP_URL, start api + userbot)
4. ISSUE TLS certs on the new box (certbot, once DNS resolves here)
```

**1. On the OLD server — take it fully down** (this is what makes the new userbot safe
to start and hands over the bot):

```bash
docker compose -f deploy/docker-compose.yml down
```

**2. At your DNS provider — repoint all four A records to the NEW server's public IP:**
`ai-imex.com`, `www.ai-imex.com`, `admin.ai-imex.com`, `api.ai-imex.com`.
(TTL was already lowered in Phase 0, so propagation is quick.)

**3. On the NEW server — enable Telegram and start the userbot:**

```bash
# Set the real public base URL in /opt/polymer/.env — reuse the OLD value verbatim:
#   PUBLIC_WEBAPP_URL=https://ai-imex.com
# Then re-create api (re-registers the webhook) and start the userbot for the first time:
cd /opt/polymer/polymer-intelligence
docker compose -f deploy/docker-compose.yml up -d api userbot
```

On `api` startup, watch for `setup_webhook.start` and
`lifespan.telegram_webhook_registered` (URL masks the secret):

```bash
docker compose -f deploy/docker-compose.yml logs -f api | grep -i webhook
```

**4. On the NEW server — issue TLS certs** (only works once the domain resolves here;
check with `dig +short api.ai-imex.com` → new IP):

```bash
sudo certbot --nginx \
  -d ai-imex.com -d www.ai-imex.com -d admin.ai-imex.com -d api.ai-imex.com
# certbot rewrites the vhost in place: adds `listen 443 ssl`, cert paths, 80→443 redirect
sudo systemctl reload nginx
```

> **Zero-gap TLS alternative:** if you can't tolerate the HTTP-only window between the
> DNS flip and cert issuance, pre-issue the certs **before** flipping DNS using a
> DNS-01 challenge (`certbot certonly --preferred-challenges dns ...`), then install
> them into the vhost. Otherwise the short HTTP window is usually acceptable.

---

## Phase 6 — Verify (still in the window)

- [ ] `https://api.ai-imex.com/api/v1/health` → `{"status":"ok","db":"ok","redis":"ok"}`
- [ ] `https://admin.ai-imex.com` loads and you can log in with a seeded staff account
      (then **rotate that password**).
- [ ] `https://ai-imex.com` serves the landing / Telegram Web App bundle.
- [ ] Telegram **bot** replies to `/start` and opens the Web App menu button (proves
      the webhook re-registered to the new box).
- [ ] **Userbot heartbeat** is fresh (no `check_userbot_health` admin alert). Confirm
      only ONE userbot is running — the old one was stopped in Phase 5.1.
- [ ] `docker compose -f deploy/docker-compose.yml ps` shows api/worker/beat/userbot/
      dashboard/nginx all Up.
- [ ] (Optional, on a throwaway stack — not against this live data) `make smoke`.

---

## Phase 7 — Backup cron on the new server

Re-establish the daily/weekly `pg_dump` per [`../deploy/backup/README.md`](../deploy/backup/README.md):

```bash
scp deploy/backup/pg_backup.sh deploy@<new-ip>:/opt/polymer/pg_backup.sh   # or cp locally
chmod 700 /opt/polymer/pg_backup.sh
crontab -e
# 0 2 * * * PGHOST=localhost PGUSER=pi_user PGDATABASE=polymer_intelligence \
#   PGPASSWORD=<secret> BACKUP_DIR=/var/backups/polymer \
#   /opt/polymer/pg_backup.sh >> /var/log/pg_backup.log 2>&1
```

> Postgres publishes no host port in prod, so either run the backup as the compose
> one-shot (see the backup README) or install `postgresql-client-16` on the host and
> point `PGHOST` at the container. Also re-schedule `certbot renew` (a daily cron is
> installed automatically by the `certbot` apt package on Ubuntu — verify with
> `systemctl list-timers | grep certbot`).

---

## Phase 8 — Decommission the old server (after a soak period)

Keep the old box **powered off but intact** for a few days as a fallback. Once the new
server has run clean through at least one full ingest + backup cycle:

- [ ] Confirm a successful backup exists on the new server.
- [ ] Restore the old server's DNS TTL to its normal (higher) value.
- [ ] Snapshot/retain the old server's `postgres_data` + `minio_data` volumes offsite
      **before** deleting the box — this is your only copy of the pre-migration data.
- [ ] Destroy the old server.

---

## Rollback (if the new server misbehaves during the window)

Because the old server was only stopped (not destroyed):

```bash
# On the NEW server — stop it so it releases the webhook + userbot session:
docker compose -f deploy/docker-compose.yml down
# Repoint DNS back to the OLD server's IP.
# On the OLD server — bring it back up (re-registers its webhook, restarts its userbot):
docker compose -f deploy/docker-compose.yml up -d
```

The TTL you lowered in Phase 0 makes this reversal fast too.

---

## Appendix — secrets: reuse vs. regenerate

Same domain + same bot/userbot ⇒ the identity-bearing secrets **must be reused**;
data-plane secrets can be freshly generated because the data itself is fresh.

| Variable | Same domain / fresh data | Why |
|----------|--------------------------|-----|
| `PUBLIC_WEBAPP_URL` | **Reuse verbatim** | Webhook URL + Web App button must stay identical. |
| `BOT_TOKEN` | **Reuse** | Same Telegram bot. |
| `WEBHOOK_SECRET` | Reuse (rotation optional) | If you rotate it the webhook still re-registers on startup — just keep URL path + header in sync. |
| `TG_API_ID` / `TG_API_HASH` | **Reuse** | Same userbot Telegram app. |
| `TG_SESSION_STRING` | **Reuse** (or regenerate once) | Same userbot account. If regenerated, do it *after* the old userbot is stopped (Phase 5.1). |
| `ANTHROPIC_API_KEY` | Reuse | Same LLM billing account. |
| `TZ_DISPLAY`, `LLM_PROMPT_VERSION`, `LLM_DAILY_TOKEN_LIMIT`, `SENTRY_DSN` | Reuse | Config, not identity. |
| `POSTGRES_PASSWORD` (+ `DATABASE_URL`) | **Regenerate** | Brand-new DB; keep `DATABASE_URL` in sync. |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | **Regenerate** | Brand-new MinIO; bucket auto-created by `minio-init`. |
| `JWT_SECRET` | **Regenerate** | No existing sessions to preserve. |

> Every `[SECRET]` has **no default** — a missing one fails fast at `api` startup
> (pydantic `Settings`). No secret literals live in tracked source; keep `/opt/polymer/.env`
> at `chmod 600` and out of git.

---

*Placeholder values only. The real `.env` is never committed.*
