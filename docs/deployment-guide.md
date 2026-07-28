# Deployment Guide — Polymer Intelligence

**Audience:** the operator standing the production stack up on a fresh VPS.
**Scope:** from a bare server to a healthy, smoke-verified production deployment.
**Restore is documented separately:** see [`docs/runbook-backup-restore.md`](./runbook-backup-restore.md) — this guide links to it for backups/restore rather than duplicating it.

> **Secrets safety.** This guide contains **placeholder values only**. The real
> `.env` lives **one level above the repo root** (`../.env`), is **never committed**
> (it is in `.gitignore`), and every `[SECRET]` must be supplied before first run.
> Store secrets in a password manager / secrets vault and **rotate** them on staff
> changes or suspected exposure. The production `deploy/docker-compose.yml` holds
> **no** secret literals — each secret is interpolated from `.env` with no inline
> default, so a missing secret fails fast at the app layer instead of running with a
> weak default.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment / secrets matrix](#2-environment--secrets-matrix)
3. [TLS certificates via certbot](#3-tls-certificates-via-certbot)
4. [First run — stand up the stack](#4-first-run--stand-up-the-stack)
5. [Telegram bot webhook](#5-telegram-bot-webhook)
6. [Userbot session setup](#6-userbot-session-setup)
7. [Backup cron](#7-backup-cron)
8. [Acceptance](#8-acceptance)

---

## 1. Prerequisites

| Requirement | Detail |
|-------------|--------|
| Server OS | Linux x86_64 (Ubuntu 22.04 LTS or similar) with Docker Engine + the Docker Compose v2 plugin |
| Domain / DNS | A registered domain with an **A record** pointing at the VPS public IP (required for TLS and for Telegram to reach the webhook over HTTPS) |
| Open ports | **80 and 443 only**, externally. nginx is the only externally-exposed service; api/worker/beat/userbot/postgres/redis/minio/dashboard are reachable only on the internal Docker network (least privilege) |
| Repo | This repository cloned onto the VPS (e.g. `/opt/polymer/polymer-intelligence`) |
| Disk | Enough headroom for Postgres data + MinIO objects + a `BACKUP_DIR` (estimate ≈100 MB–1 GB per dump) |

> **Note:** Do NOT publish Postgres (5432), Redis (6379), or MinIO (9000/9001) on
> host ports in production. The production compose deliberately exposes no host
> ports except nginx 80/443.

---

## 2. Environment / Secrets Matrix

Copy `deploy/.env.example` to `../.env` (one level above the repo root) and fill in
every `[SECRET]`. **All values below are placeholders.**

| VAR | Description | Source | Example (placeholder) |
|-----|-------------|--------|------------------------|
| `POSTGRES_PASSWORD` | Postgres superuser (`pi_user`) password | You generate a strong random string | `REPLACE_strong_random` |
| `DATABASE_URL` | Full SQLAlchemy URL (uses `POSTGRES_PASSWORD`) | Derived | `postgresql+psycopg://pi_user:REPLACE@postgres:5432/polymer_intelligence` |
| `REDIS_URL` | Celery broker / cache | Fixed for the compose network | `redis://redis:6379/0` |
| `S3_ENDPOINT` | Object storage endpoint | MinIO (internal) or external S3 | `http://minio:9000` |
| `S3_ACCESS_KEY` | S3/MinIO access key | You generate (MinIO root user) | `REPLACE_minio_access` |
| `S3_SECRET_KEY` | S3/MinIO secret key | You generate (MinIO root password) | `REPLACE_minio_secret` |
| `S3_BUCKET` | Bucket for request file uploads | You choose | `polymer-files` |
| `JWT_SECRET` | Signs dashboard JWTs | Random hex ≥64 chars | `REPLACE_random_64_hex` |
| `ANTHROPIC_API_KEY` | LLM extraction / reports | console.anthropic.com | `sk-ant-REPLACE_ME` |
| `BOT_TOKEN` | Telegram bot token (webhook + pushes) | @BotFather | `REPLACE_botfather_token` |
| `WEBHOOK_SECRET` | Secret in the webhook URL path **and** the `X-Telegram-Bot-Api-Secret-Token` header | Random string ≥32 chars | `REPLACE_random_32_char` |
| `PUBLIC_WEBAPP_URL` | Public HTTPS base URL of this deployment | Your domain | `https://your-domain.example` |
| `TG_API_ID` | Telegram userbot API id | https://my.telegram.org | `REPLACE_api_id` |
| `TG_API_HASH` | Telegram userbot API hash | https://my.telegram.org | `REPLACE_api_hash` |
| `TG_SESSION_STRING` | Userbot login session string | Generated once (see §6) | _(blank until generated)_ |
| `LLM_DAILY_TOKEN_LIMIT` | Daily LLM token budget (UTC reset) | Tuning | `500000` |
| `LLM_PROMPT_VERSION` | Prompt version pin | Tuning | `v1` |
| `TZ_DISPLAY` | Display timezone | Fixed | `Asia/Tashkent` |
| `SENTRY_DSN` | Optional error reporting | Sentry (leave blank to disable) | _(blank)_ |

> **Note:** `WEBHOOK_SECRET` is checked **twice** on every inbound webhook (URL path
> segment **and** the `X-Telegram-Bot-Api-Secret-Token` header, constant-time
> compare) — a mismatch on either returns HTTP 403. Use a long random value.

---

## 3. TLS Certificates via certbot

The production nginx config (`deploy/nginx/nginx.conf`) is **TLS-terminating**: it
listens on 443, redirects 80→443, and references Let's Encrypt cert paths. Out of the
box it ships with the **placeholder** `server_name _;` and cert paths under
`/etc/letsencrypt/live/example.com/`. You must (a) set your real domain and (b)
obtain certs into the `letsencrypt` volume.

### Step 1: Point your domain at the VPS

Create an **A record** for your domain → VPS public IP. Confirm it resolves before
requesting a certificate.

### Step 2: Set the real domain in nginx.conf

Edit `deploy/nginx/nginx.conf`:

- Replace `server_name _;` with your domain (both the `:80` and `:443` server blocks).
- Replace the two `example.com` cert paths with your domain:

  ```nginx
  ssl_certificate     /etc/letsencrypt/live/your-domain.example/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/your-domain.example/privkey.pem;
  ```

### Step 3: Obtain the certificate (webroot / ACME http-01)

The nginx `:80` block serves the ACME challenge from `/var/www/certbot` (mounted into
the `certbot_www` volume). Issue the cert with certbot into the shared `letsencrypt`
volume — for example:

```bash
docker run --rm \
  -v polymer-intelligence_letsencrypt:/etc/letsencrypt \
  -v polymer-intelligence_certbot_www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d your-domain.example --email you@your-domain.example --agree-tos --no-eff-email
```

> **Note:** The `letsencrypt` and `certbot_www` volume names are prefixed with the
> compose project name (default: the directory name). Run `docker volume ls` to
> confirm the exact names, and bring nginx up at least once (Step 4) so the `:80`
> ACME path is reachable, or use certbot `--standalone` on a temporarily free port 80.

### Step 4: Renewal

Schedule `certbot renew` (e.g. a daily cron on the host using the same volume mounts);
nginx serves renewals from the same `/var/www/certbot` webroot. Reload nginx after a
successful renewal (`docker compose -f deploy/docker-compose.yml exec nginx nginx -s reload`).

---

## 4. First Run — Stand Up the Stack

With `../.env` filled in and TLS certs in place:

```bash
docker compose -f deploy/docker-compose.yml up -d
```

The `api` service runs its migrate + seed chain **before** serving (idempotent, so
re-deploys are safe):

```
python -m app.entrypoint            # alembic upgrade head (advisory-locked)
&& python -m app.seed.seed_reference  # products / grades
&& python -m app.seed.seed_staff      # initial staff accounts
&& python -m app.seed.seed_sources    # source catalog
&& uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Verify health

```bash
# from inside the api container (no host port is published):
docker compose -f deploy/docker-compose.yml exec api \
  curl -s http://localhost:8000/api/v1/health
```

Expected: `{"status":"ok","db":"ok","redis":"ok"}`. Externally, once TLS is up,
`https://your-domain.example/api/v1/health` returns the same through nginx.

### Prove the stack end-to-end (smoke)

```bash
make smoke
```

`make smoke` runs `tests/smoke/test_smoke_full_stack.sh` (D-02), which stands up the
production compose on a runtime-generated placeholder `.env` (removed on exit),
health-gates `/api/v1/health`, inserts a synthetic request and confirms it reaches
`v_live_feed`, and forces a fake-source failure to confirm per-source isolation +
exactly one `source_failure` alert — printing `[smoke] PASSED`. This is the same
stand-up sequence this guide describes, so a green smoke confirms the deployment path.

> **Note:** `make smoke` brings up its own isolated stack for the synthetic test and
> tears it down (`compose down -v`). Run it on a deploy host, not against live
> production data.

---

## 4a. Load the Telegram Web App bundle

nginx serves the Telegram Web App at `/webapp/` from the `webapp_static` volume,
which is **empty until you populate it**. A one-shot `webapp-build` compose service
(profile `build`) builds the Vite bundle and loads it into that volume — run it at
deploy time and after every webapp change:

```bash
make webapp-bundle
# equivalently:
docker compose -f deploy/docker-compose.yml --profile build run --rm --build webapp-build
```

It prints `[webapp-build] bundle loaded into webapp_static` on success. Because it
runs as a compose service, the project-prefixed `webapp_static` volume is resolved
automatically — no need to know the `COMPOSE_PROJECT_NAME` prefix. nginx serves the
files live from the shared volume, so no nginx restart is needed (re-run on each
webapp update). The webapp calls the API at the relative `/api/v1` path (proxied by
nginx), so the build needs no environment or secrets.

---

## 5. Telegram Bot Webhook

The bot runs as a **webhook endpoint inside the api container** (no separate bot
container). Webhook registration is **automatic on api startup** — there is no manual
`curl setWebhook` step:

1. Set `BOT_TOKEN`, `WEBHOOK_SECRET`, and a public-HTTPS `PUBLIC_WEBAPP_URL` in `../.env`.
2. On `api` startup, when `PUBLIC_WEBAPP_URL` is non-empty, the app calls
   `telegram.bot.setup_webhook()`, which registers:
   ```
   {PUBLIC_WEBAPP_URL}/api/v1/telegram/webhook/{WEBHOOK_SECRET}
   ```
   passing `WEBHOOK_SECRET` as Telegram's `secret_token`, and installs the persistent
   Web App menu button pointing at `PUBLIC_WEBAPP_URL`.
3. Confirm registration in the api logs: look for `setup_webhook.start` and
   `lifespan.telegram_webhook_registered` (the logged URL masks the secret).

> **Spoofing protection (T-03-11).** The webhook endpoint requires the secret to match
> in **both** the URL path **and** the `X-Telegram-Bot-Api-Secret-Token` header
> (constant-time compare); mismatch → 403. Register the webhook **only** over public
> HTTPS — never plaintext HTTP.

> **Note:** In dev/CI, `PUBLIC_WEBAPP_URL` is empty so Telegram is never called. If
> the webhook does not register in production, verify `PUBLIC_WEBAPP_URL` is set,
> resolves over HTTPS, and that the bot token is valid.

---

## 6. Userbot Session Setup

Channel monitoring runs as a separate long-lived `userbot` MTProto process. It needs
three customer-provided values: `TG_API_ID`, `TG_API_HASH`, and a one-time-generated
`TG_SESSION_STRING`.

1. Obtain `TG_API_ID` and `TG_API_HASH` from https://my.telegram.org.
2. Generate `TG_SESSION_STRING` **once**, interactively, on a trusted machine. The
   one-time `StringSession` login procedure is documented in `userbot/session.py`; it
   logs the userbot account in and prints the session string. For example:

   ```bash
   python - << 'EOF'
   from telethon.sync import TelegramClient
   from telethon.sessions import StringSession

   api_id   = int(input("TG_API_ID: "))
   api_hash = input("TG_API_HASH: ")
   with TelegramClient(StringSession(), api_id, api_hash) as client:
       print("Session string (copy to .env TG_SESSION_STRING):")
       print(client.session.save())
   EOF
   ```
3. Paste the printed string into `../.env` as `TG_SESSION_STRING`. **Never commit it.**
4. Restart the userbot: `docker compose -f deploy/docker-compose.yml up -d userbot`.
   It connects, subscribes to enabled `telegram_channel` sources, writes new messages
   to `raw_items`, and emits a Redis heartbeat. The `check_userbot_health` beat task
   raises a deduped admin alert if the heartbeat goes silent >5 min.

> **Note:** With `TG_SESSION_STRING` empty the userbot fails fast at startup with a
> clear message (it will not run unauthenticated). Per the contract (TZ §7.2) the
> userbot account is customer-provided and may be subject to Telegram rate limits.

---

## 7. Backup Cron

Daily/weekly Postgres backups are handled by `deploy/backup/pg_backup.sh`
(`pg_dump --format=custom`, 14-daily / 8-weekly retention). **Setup and cron details
are in [`deploy/backup/README.md`](../deploy/backup/README.md)** — install that cron;
this guide does not duplicate it.

Quick reference (full instructions in the backup README):

```cron
# /etc/crontab — daily at 02:00 UTC
0 2 * * * PGHOST=localhost PGUSER=pi_user PGDATABASE=polymer_intelligence \
  PGPASSWORD=<secret> BACKUP_DIR=/var/backups/polymer \
  /opt/polymer/pg_backup.sh >> /var/log/pg_backup.log 2>&1
```

**Restore is documented separately:** follow [`docs/runbook-backup-restore.md`](./runbook-backup-restore.md)
for the ≤2 h restore procedure (validated end-to-end by `tests/restore/test_restore_local.sh`).

> **Offsite hardening:** dumps land on the same VPS disk by default. For
> disaster-recovery, replicate `BACKUP_DIR` offsite (rclone to S3/R2, scp to a
> secondary host); consider encrypting dumps before transfer. See runbook §6.

---

## 8. Acceptance

After the stack is healthy and smoke-green, run the Phase-1 acceptance steps in
[`.planning/phases/06-acceptance-handover/06-ACCEPTANCE.md`](../.planning/phases/06-acceptance-handover/06-ACCEPTANCE.md)
(the consolidated TZ §6.1.1–§6.1.6 sign-off spine + the single Deploy-Day Checklist).

---

## R1 — Company Verification & Portal rollout checklist

R1 ships **badge-only**: verification is required only to publish offers; no other gate is
flipped. Rollout (dev → prod):

1. **Merge to `dev`** — the dev stack auto-pulls `dev` and redeploys. Migration `0017`
   applies automatically (advisory-locked). The `portal` CI job (lint · tsc · build) must be green.
2. **Run the demo on the dev stack** (R1-PLAN Definition of Done): register by phone — three ways
   to get the code, all requiring `DEBUG=true` + `SMS_PROVIDER=console`: set `OTP_DEV_CODE=000000`
   and just type it, read the worker log (`sms.console.send`), or call
   `GET /portal/auth/otp/peek?phone=` → create 2 companies → submit → approve one from dashboard `/verification`, the
   other from the Telegram group → switch active company → publish an offer → moderate → offer
   appears in the public market with `company_verified: true`.
3. **Bundle the frontends** — only needed for a MANUAL deploy: `make portal-bundle`
   (+ `make webapp-bundle` if changed). On a push to `dev`/`main` the CI deploy job already
   pulls the prebuilt `…-portal` image and runs `portal-build` itself, so nothing compiles on
   the server. Either way the step is not optional: the bundle lives in the `portal_static`
   volume, not in any long-running image, so a deploy that skips it serves the PREVIOUS
   cabinet build — or, on a fresh server, an empty volume that answers 404.
4. **Prod prep** (in the prod `../.env`, one level above the repo root):
   - `VERIFICATION_ENC_KEY` — a **new required secret** (≥32 urlsafe-b64 chars). Generate once and
     store securely; **rotating it makes existing encrypted bank numbers/PINFL undecryptable**.
   - `SMS_PROVIDER=eskiz` + `ESKIZ_EMAIL` / `ESKIZ_PASSWORD` (secrets). Leave `console` for staging.
   - `VERIFICATION_NOTIFY_CHAT_ID` (optional; falls back to `REQUEST_NOTIFY_CHAT_ID`).
   - Leave the enforcement app-settings OFF (`verification_auto_approve`,
     `bank_verification_required`, `verification_required_for_publish`) — badge-only.
5. **DNS + TLS + the host vhost** — three steps, and the third is the one that gets missed:
   - `cabinet.ai-imex.com` DNS → the host front door;
   - a **host** nginx server block for that name forwarding to `127.0.0.1:8080`. The inner
     nginx routes by `Host`, so a domain with no host-side block never reaches it, no matter
     how healthy the container is. The block ships in
     `deploy/nginx/host-vhost.ai-imex.conf.example` — copy the file, `nginx -t`, reload;
   - the cert: add `-d cabinet.ai-imex.com` to the certbot invocation in that file's header.

   (The inner `cabinet.*` block has been in `nginx.behind-proxy.conf` since R1; the dev stack's
   equivalent is `dev-cabinet.ai-imex.com` in `nginx.dev-server.behind-proxy.conf`.)
6. **Verify** (from outside the server, so the host front door is in the path):
   ```bash
   curl -sI https://cabinet.ai-imex.com/            | head -1   # 200, not 404/502
   curl -s   https://cabinet.ai-imex.com/companies  -o /dev/null -w '%{http_code}\n'  # 200 — SPA fallback
   curl -s   https://cabinet.ai-imex.com/api/v1/health                                 # same-origin API
   ```
   A **404 at the root** means `portal_static` is empty → run `portal-build`. A **502** means the
   inner nginx is unreachable → check the container. **Landing on another site** means the host
   vhost for `cabinet.*` is missing → step 5.
7. **Announce**: verified companies now carry a «проверено» badge and can publish from the cabinet.

---

*No real secret values appear in this guide.*
