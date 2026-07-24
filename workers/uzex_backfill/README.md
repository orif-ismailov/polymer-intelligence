# UZEX Offer Archive Backfill Worker

A **standalone** crawler that walks the uzex.uz offer-detail ID space, fetches
each server-rendered detail page, parses it generically into `{label: value}`
JSON, and stores every offer in PostgreSQL.

It is deliberately isolated from the main application:

- **No imports from the app.** Own entrypoint, own `requirements.txt`, own DB
  tables (additive-only, no foreign keys).
- **Own process.** Runs as a systemd unit / `tmux`+`nohup`, never inside the
  app's Celery. The main project can be deployed or restarted at any time with
  zero effect on a running walk, and vice versa.

## What it does

- Detail route: `https://uzex.uz/trade/offer/{id}` (confirmed from the listing
  pages' `href`s — override with `UZEX_DETAIL_URL`).
- Pins Russian rendering once via `/Home/ChangeLang?culture=ru` so stored labels
  are stable Russian strings.
- **Generic parse** — every row of the `table.custom-table-dark` details table
  becomes a `{label: value}` pair with original labels preserved. No hardcoded
  field list, **no LLM**. Value cells containing links are stored href-aware:
  `{"text": ..., "href": ...}` (and `"hrefs": [...]` when a cell has several).
- **Failure signatures** (learned via `probe`, confirmed live):
  - `ok` — HTTP 200 + details table + ≥1 pair (~19 fields on a real offer).
  - `not_found` — HTTP 200 but no details table (the ~58 KB empty template) — an
    id gap, skipped.
  - `parse_empty` — page rendered but nothing usable (malformed/truncated, or a
    table with zero pairs). Raw HTML is kept for forensics.
  - `fetch_failed` — network/5xx persisted through retries; retryable later.

## raw_html policy (anomaly-only)

Raw HTML is **not** stored for normal pages (the archive is publicly
re-fetchable; the JSONB `fields` is the record). Gzip'd `raw_html` is kept ONLY
when: `status = parse_empty`, OR a 200 page parsed `< 5` fields, OR the page
contains a label never seen before (first occurrence only).

## Install

```bash
cd workers/uzex_backfill
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## Configuration (all via env)

| Var | Default | Notes |
|-----|---------|-------|
| `DATABASE_URL` | — (required) | Postgres DSN; a `+psycopg`/`+asyncpg` driver suffix is stripped automatically. |
| `UZEX_DETAIL_URL` | `https://uzex.uz/trade/offer/{id}` | `{id}` is substituted per request. |
| `UZEX_CHANGE_LANG_URL` | `https://uzex.uz/Home/ChangeLang?culture=ru&returnUrl=%2F` | Pins Russian rendering. |
| `USER_AGENT` | `IMEX-Research/1.0 (+orifismailov08@gmail.com)` | Identify yourself. |
| `WORKER_NAME` | `uzex_offer_detail` | Checkpoint key **and** the `source` column value. |
| `MIN_ID` / `MAX_ID` | `1` / `400000` | Walk bounds. |
| `RATE_LIMIT_RPS` | `1.0` | Global rate limit (single worker, no parallel fetch). |
| `ENV` | `prod` | `dev` enables the hard cap below. |
| `DEV_MAX_ID_CAP` | `1000` | In `dev`, the effective max id is capped here so a misconfiguration cannot start a full walk; `run` also *requires* explicit `--from/--to`. |
| `HTTP_TIMEOUT_SECONDS` | `30` | |
| `MAX_RETRIES` | `3` | Per-id quick retries before a long backoff. |
| `BACKOFF_START_SECONDS` / `BACKOFF_MAX_SECONDS` | `60` / `3600` | 429/403/outage backoff, doubling 60s→1h. |
| `MAX_HARD_RETRIES` | `8` | Long-backoff cycles to insist on one failing id before marking `fetch_failed` and advancing. Blocks (429/403) are never given up on. |
| `CHECKPOINT_EVERY` / `CHECKPOINT_INTERVAL_SECONDS` | `25` / `30` | Checkpoint cadence. |
| `STALE_LOCK_SECONDS` | `300` | Concurrent-run guard window (also the heartbeat freshness target). |

## Commands

```bash
python -m uzex_backfill init-db          # apply the standalone schema (idempotent)
python -m uzex_backfill probe            # characterize good/bad/boundary ids; writes nothing
python -m uzex_backfill run              # walk from checkpoint to configured max
python -m uzex_backfill run --from 100 --to 110
python -m uzex_backfill retry-failed     # re-fetch ids marked fetch_failed
python -m uzex_backfill status           # checkpoint, counts by status, ETA
```

Logs are JSON-lines on stdout: one `id` line per fetch (id, status, duration,
field count) and a `summary` every 1000 ids.

## Safety rails

- **Concurrent-run guard.** `run`/`retry-failed` refuse to start if another
  worker with the same `WORKER_NAME` updated its checkpoint within
  `STALE_LOCK_SECONDS`. A heartbeat keeps this fresh *during* long backoffs, so a
  second process never starts mid-outage. Override with `--force`.
- **The full walk runs ONCE, against the production/data DB only.** UZEX must
  never be crawled from two environments at the same time.
- **Dev never runs a full walk.** With `ENV=dev`, `run` requires explicit
  `--from/--to` and the effective max id is hard-capped at `DEV_MAX_ID_CAP`. Read
  archived data in dev via a `pg_dump` snapshot / read-only access to the raw
  tables instead.
- **Killable at any moment.** `SIGTERM`/`SIGINT` finish the in-flight request,
  commit, and exit 0. A `kill -9` loses at most the ids since the last checkpoint;
  a resume re-fetches those and dedups them (zero duplicate rows).

## Resume / idempotency

The checkpoint is a monotonic high-water mark in `uzex_backfill_progress`. A
resume (`run` with no `--from`) starts at `checkpoint + 1`. Every row upserts on
`(source, external_id, content_hash)` with `ON CONFLICT DO NOTHING`, so:
re-running a completed range inserts **zero** duplicates, and a genuine content
change lands as a **new revision** row (the first copy is never mutated). To fully
reset the resume point, delete the worker's `uzex_backfill_progress` row.

## Deploy (systemd)

See `deploy/uzex-backfill.service.example`. Run it on the data-DB host, once:

```bash
sudo cp deploy/uzex-backfill.service.example /etc/systemd/system/uzex-backfill.service
sudoedit /etc/systemd/system/uzex-backfill.service   # set DATABASE_URL, paths
sudo systemctl daemon-reload
sudo systemctl enable --now uzex-backfill
journalctl -u uzex-backfill -f
```

Or with tmux: `ENV=prod DATABASE_URL=... python -m uzex_backfill run`.

## Tests

```bash
cd workers/uzex_backfill
pip install pytest
pytest tests/ -q                                    # parser + config (offline)
UZEX_BACKFILL_TEST_DSN=postgresql://... pytest tests/ -q   # + DB idempotency
```
