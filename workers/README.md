<!-- generated-by: gsd-doc-writer -->
# workers/

Home for **standalone** Python workers that run outside the main
`backend/` application — no shared imports, no shared database schema,
no shared process supervisor (Celery). Each subdirectory here is its own
self-contained tool with its own dependencies, its own entrypoint, and its
own deployment.

See the root [`README.md`](../README.md) for what Polymer Intelligence is as
a whole, and [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for how the
main application's ingest → signals pipeline works. This directory is
deliberately **outside** that architecture.

## Why this directory is isolated

The main app's ingest pipeline (`backend/app/ingest/`) already has a
`uzex_offers` adapter that reads UZEX's *live* listing pages on a schedule
via Celery. The worker in this directory does something different in kind,
not just in scope: it walks the **entire historical offer-detail ID space**
on `uzex.uz` (a slow, long-running, potentially multi-day crawl), and it
needs to do that without:

- competing with the app's Celery queues/workers for capacity,
- being restarted or redeployed every time the main app ships,
- risking any coupling between a scraper's schema/parsing quirks and the
  app's `raw_items`/`signals` tables.

So each package under `workers/` gets its own Postgres tables (additive
only, **no foreign keys** into the app's schema), its own
`requirements.txt`, and its own long-lived OS process (systemd unit or
`tmux`/`nohup`) — **never** a Celery task. The main app can be deployed,
restarted, or torn down at any time with zero effect on a worker crawl
in progress, and vice versa.

## Packages

| Package | What it does |
|---|---|
| [`uzex_backfill/`](uzex_backfill/) | Crawls `uzex.uz` offer-detail pages by walking their sequential integer ID space (`https://uzex.uz/trade/offer/{id}`), generically parses each page's details table into `{label: value}` JSON (no hardcoded field list, no LLM), and archives every offer into its own `uzex_raw_offers` table. |

`uzex_backfill/` is currently the only worker in this directory. Its own
[`uzex_backfill/README.md`](uzex_backfill/README.md) is the authoritative,
detailed reference — this file is an orientation index. The summary below
mirrors it but may drift; when in doubt, read the package README and the
source directly.

### `uzex_backfill/` at a glance

- **Entrypoint:** `python -m uzex_backfill <command>` (`cli.py` /
  `__main__.py`), with subcommands `init-db`, `probe`, `run`,
  `retry-failed`, `status`.
- **Config:** environment variables only, loaded fail-fast by
  `config.py` (`load_config()`) — no config files, no imports from
  `backend/`. `DATABASE_URL` is the only required variable; everything else
  (`UZEX_DETAIL_URL`, `WORKER_NAME`, `MIN_ID`/`MAX_ID`, `RATE_LIMIT_RPS`,
  `ENV`, retry/backoff/checkpoint tuning) has a documented default. See the
  full table in [`uzex_backfill/README.md`](uzex_backfill/README.md#configuration-all-via-env).
- **Storage:** its own schema, `uzex_backfill/schema.sql`, applied
  idempotently by `init-db` (and automatically at the top of `run` /
  `retry-failed`): `uzex_raw_offers` (one row per fetch attempt outcome,
  deduped on `(source, external_id, content_hash)`), `uzex_backfill_progress`
  (one checkpoint row per `WORKER_NAME`), and `uzex_discovered_labels`
  (first-seen tracking for new field labels).
- **Resumability:** the walk keeps a monotonic checkpoint
  (`uzex_backfill_progress.last_id`); `run` with no `--from` always resumes
  from `checkpoint + 1`. `SIGTERM`/`SIGINT` finish the in-flight request,
  commit, and exit cleanly — a `kill -9` loses at most the ids since the
  last checkpoint, and resuming re-fetches them without creating duplicate
  rows (`ON CONFLICT DO NOTHING` on the dedup key).
- **Rate limiting & backoff:** a single global rate limit
  (`RATE_LIMIT_RPS`, default 1 req/s, no parallel fetching), with retry and
  exponential backoff (`BACKOFF_START_SECONDS` → `BACKOFF_MAX_SECONDS`) on
  429/403/5xx before an id is marked `fetch_failed` and the walk advances.
- **Concurrency guard:** `run`/`retry-failed` refuse to start if another
  process with the same `WORKER_NAME` updated its checkpoint within
  `STALE_LOCK_SECONDS` (default 300s) — override with `--force`.
- **Dev safety rail:** with `ENV=dev`, `run` requires explicit `--from`/`--to`
  and the effective max id is hard-capped by `DEV_MAX_ID_CAP` — a
  misconfigured environment cannot accidentally trigger a full production
  crawl.
- **Monitoring:** JSON-lines logs on stdout (one line per fetched id plus a
  periodic summary); `python -m uzex_backfill status` reports the checkpoint,
  per-status counts, discovered label count, and a rough ETA.
- **Deploy:** a systemd unit template lives at
  `uzex_backfill/deploy/uzex-backfill.service.example`. <!-- VERIFY: where/whether this worker is actually deployed and running in production — not determinable from the repository alone --> The template
  and its own README both state it is meant to run as a single long-lived
  instance on the data-DB host, independent of the app's deploy process.

## Adding a new worker

Follow the same isolation pattern as `uzex_backfill/`:

1. New subdirectory under `workers/`, its own `requirements.txt`, and an
   entrypoint runnable with `python -m <package>`.
2. No imports from `backend/`, `telegram/`, `userbot/`, or any other app
   package.
3. Own Postgres tables — additive only, no foreign keys into the app's
   schema — applied by an idempotent schema file or migration owned by the
   package itself.
4. Own OS process for deployment (systemd unit or equivalent) — never a
   Celery task in `backend/app/tasks/`.
5. Document it in this file's package table and give it its own
   package-level README, matching the depth of
   [`uzex_backfill/README.md`](uzex_backfill/README.md).
