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
  `nginx.behind-proxy.conf`; the dev stack's is `dev-cabinet.ai-imex.com` in
  `nginx.dev-server.behind-proxy.conf`). Prod needs DNS `cabinet.*` + a host cert (behind-proxy:
  host nginx terminates TLS → docker nginx :8080).
  **The bundle is in a VOLUME, not an image** — so it is refreshed only when `portal-build` runs.
  CI now does that on every deploy (it pulls `…-portal:<branch>`, built by `build-images`, and
  runs the one-shot service — nothing compiles on the 2-core box). A deploy that skips it leaves
  the previous cabinet build; a fresh server with an empty volume answers **404**.
  **Every public domain also needs a HOST-side vhost.** The inner nginx routes by `Host` and
  never sees a request for a name the host front door has no block for — that request just lands
  on the default site. `cabinet.*` was inner-only until now;
  `host-vhost.ai-imex{,-dev}.conf.example` ship the block, and the certbot line in each header
  covers the name. If the cabinet is unreachable while the container is healthy, check there first. New envs (R1): `VERIFICATION_ENC_KEY` (**secret**, ≥32
  urlsafe-b64 chars), `SMS_PROVIDER` (`console` dev / `eskiz` prod) + `ESKIZ_EMAIL`/`ESKIZ_PASSWORD`
  (secret, required when eskiz), `VERIFICATION_NOTIFY_CHAT_ID` (optional). Enforcement app-settings
  (`verification_auto_approve`, `bank_verification_required`, `verification_required_for_publish`)
  default OFF — R1 ships badge-only.
- **Web App bundle** is built separately into the `webapp_static` volume: `make webapp-bundle`
  (= `docker compose --profile build run --rm --build webapp-build`).
- **E-IMZO sidecar (R3)** — `eimzo-server` is the UNICON Java verification server that checks
  national O'zDSt PKCS#7 signatures (stock crypto libs can't). It is **profile-gated** (`profiles:
  ["eimzo"]`) in BOTH compose files, so a plain `docker compose up` never requires it: when it's
  absent the gateway adapter (`backend/app/integrations/eimzo/`) opens its circuit and the API
  returns 503 (`ProviderUnavailable`) while the manual verification path stays fully usable
  (degradation invariant). **Operator prerequisite (hard blocker for Stage-A E-IMZO):** obtain the
  distribution per UNICON licensing, push it to the private registry, and set `EIMZO_SERVER_IMAGE`
  in `.env`. Bring it up with `docker compose --env-file .env -f deploy/docker-compose.yml --profile
  eimzo up -d eimzo-server`. New envs (all non-secret, safe defaults): `EIMZO_SERVER_URL`
  (default `http://eimzo-server:8080`), `EIMZO_CHALLENGE_TTL_SECONDS` (default `300`), plus the
  compose-only `EIMZO_SERVER_IMAGE` (**required** to activate the `eimzo` profile).
  **Root trust:** the sidecar verifies certificate chains against the UZ root/intermediate CA
  bundle mounted read-only at `/opt/eimzo/truststore` from `deploy/eimzo/truststore/` (git-tracked
  placeholder; the real production certs are supplied out of band and are **not** committed).
  *Refresh procedure:* download the current O'zDSt root + intermediate certs from the E-IMZO / soliq
  distribution, drop the PEM/DER files into `deploy/eimzo/truststore/` on the host, then
  `docker compose ... --profile eimzo restart eimzo-server`. Review the bundle at least annually and
  whenever UNICON rotates a CA.
  **NOTE (`.env.example`):** the three E-IMZO variables above must be appended to the tracked
  `deploy/.env.example` env contract; they were not added automatically here because the local
  tooling denies edits to `.env*` files.
- **Contracts (R3 Stage B)** — the contract PDF renderer uses **WeasyPrint**, whose native libs
  (Pango/Cairo/GDK-Pixbuf + `fonts-dejavu`/`fonts-liberation` for Cyrillic) are installed in
  `backend/Dockerfile` and the CI backend job; without them the PDF render test skips. The api
  startup command runs `python -m app.seed.seed_contract_templates` (idempotent) which uploads the
  supply-contract template body to S3 and inserts the `contract_templates` row — the bundled body is
  a **DEV placeholder**; the production text + legal sign-off are a launch blocker (see
  `docs/contracts-legal-checklist.md`). Nightly beats `verify_contract_integrity` (PDF sha256 drift
  → admin-channel alert) and `expire_stale_contracts` (`contract_pending_ttl_days`, default 30) run
  on the existing `default` queue — no queue/compose change. `EIMZO_STUB=true` (dev/CI only) lets the
  whole sign flow run without the sidecar; **must be false in production**.
- **Compliance (R5 / P5)** — the api startup command also runs
  `python -m app.seed.seed_substances` (idempotent) which digitizes the ПКМ lists into
  `substances`. The shipped revision is `v1-provisional` and **deliberately incomplete** — only the
  entries confirmed by `.planning/deal-lifecycle/INTEGRATIONS.md` §4. Re-running never duplicates a
  row and never overwrites one an operator edited in the admin panel (`seed_revision` goes NULL on
  a hand edit). The publish gate `dangerous_check_enforced` is a runtime setting that ships **off**;
  turning it on before the legal review of the lists would block trade on an incomplete registry.

- **Live integrations (R6 / P7)** — two operator-facing rails, both shipping OFF.
  *Escrow callbacks (P7.b):* nginx must pass `POST /api/v1/webhooks/escrow/{provider}` through
  to the api like the rest of `/api/`, and the bank sends a shared secret in `X-Escrow-Token`.
  New env **`ESCROW_WEBHOOK_SECRET`** (**secret**, empty default — the route answers **404**
  while it is empty, so a deployment that never enables escrow does not advertise the
  endpoint; conditionally required, same shape as `ESKIZ_*`, because the rail is a RUNTIME
  setting a startup validator cannot see). Two new beats on existing queues — no compose
  change: `sweep_provider_events` (`default`, every 5 min — the safety net for a dropped
  dispatch) and `reconcile_escrow_payments` (`verify`, every 30 min — the only OUTBOUND call
  on the rail; a no-op until `escrow_mode=live` AND a bank adapter exists). Divergences
  (bank released without confirmed delivery; bank refunded) alert the admin channel and are
  never auto-applied.
  *Gov registries (P7.c):* new runtime setting `gov_registry_mode` (ships `stub`; `live`
  raises until ПЦД access exists). No new env, no sidecar. The channel that works today is
  the operator's manual check — its screenshots land in S3 under `evidence/registry/`, so
  they are covered by the same bucket/backup policy as `evidence/eimzo/`.
  **NOTE (`.env.example`):** `ESCROW_WEBHOOK_SECRET` must be appended by hand to the tracked
  `deploy/.env.example` env contract — the local tooling denies edits to `.env*` files (the
  same constraint that left the three R3 E-IMZO variables to be pasted in). Paste:
  ```
  # ── Escrow provider callbacks (R6 / P7.b) ─────────────────────────────────────
  # Shared secret the partner bank sends in `X-Escrow-Token` on every callback to
  # POST /api/v1/webhooks/escrow/{provider}. Empty by default and required only once
  # the bank rail is on: `escrow_mode` is a RUNTIME setting a startup validator cannot
  # see, so a mandatory value would burden every deployment. Same shape as ESKIZ_*.
  # While empty the webhook answers 404 — an unconfigured deployment does not
  # advertise the endpoint.
  ESCROW_WEBHOOK_SECRET=                     # [SECRET] required only for escrow_mode=live
  ```

## Make targets (run from repo root)

```bash
make smoke          # production-compose smoke test (synthetic data + placeholder env)
make webapp-bundle  # build + load the Telegram Web App into the nginx-served volume
make portal-bundle  # build + load the client cabinet into the portal_static volume (cabinet.*)
```
Both use `docker compose --env-file .env -f deploy/docker-compose.yml` — the `--env-file .env` is
required so Compose interpolates from the repo-root `.env`.
