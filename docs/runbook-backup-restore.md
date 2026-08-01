# Runbook: Backup & Restore — Polymer Intelligence

**Restore target:** ≤ 2 hours (TZ §6.1.5 — from dump selection to service-healthy)

**Retention policy (REQ-nfr-reliability):**
- **14 daily** dumps retained (≈ 2 weeks of daily point-in-time recovery)
- **8 weekly** dumps retained (≈ 2 months of weekly coverage, created every Monday)

---

## Table of Contents

1. [Backup schedule](#1-backup-schedule)
2. [Selecting the right dump](#2-selecting-the-right-dump)
3. [Restore procedure](#3-restore-procedure)
4. [Post-restore checklist](#4-post-restore-checklist)
5. [Restore time target](#5-restore-time-target)
6. [Offsite storage](#6-offsite-storage)

---

## 1. Backup Schedule

| Frequency | Retention | Directory               | Format                          |
|-----------|-----------|-------------------------|---------------------------------|
| Daily     | 14 dumps  | `BACKUP_DIR/daily/`     | `pg_<db>_<timestamp>.pgdump`    |
| Weekly    | 8 dumps   | `BACKUP_DIR/weekly/`    | `pg_<db>_week_<timestamp>.pgdump` |

Backups are triggered by the cron configured in `deploy/backup/README.md`.
Each dump uses `pg_dump --format=custom --compress=6` (PostgreSQL 16 custom format,
compatible only with `pg_restore`).

---

## 2. Selecting the Right Dump

```bash
# List daily backups newest-first
ls -1t /var/backups/polymer/daily/*.pgdump

# List weekly backups newest-first
ls -1t /var/backups/polymer/weekly/*.pgdump
```

Select the dump that predates the incident (or the most recent one for
hardware-failure recovery). Copy the dump filename — you will need it in the
next section.

```bash
DUMP=/var/backups/polymer/daily/pg_polymer_intelligence_20260615T020000Z.pgdump
```

---

## 3. Restore Procedure

> **Time budget:** target ≤ 2 hours for the full sequence below.
> On a typical dataset (< 5 GB) this takes 15–30 minutes.

### Step 1: Stop the application

```bash
docker compose -f deploy/docker-compose.dev.yml stop api worker beat
```

### Step 2: Create a clean target database

Connect to PostgreSQL as a superuser. **The bootstrap superuser is `pi_user`**
(the `POSTGRES_USER` the container is initialised with) — there is **no separate
`postgres` role** in this deployment, so use `-U pi_user`:

```bash
docker compose -f deploy/docker-compose.dev.yml exec postgres \
  psql -U pi_user -d postgres -c "DROP DATABASE IF EXISTS polymer_intelligence;"
docker compose -f deploy/docker-compose.dev.yml exec postgres \
  psql -U pi_user -d postgres -c "CREATE DATABASE polymer_intelligence OWNER pi_user;"
```

> Connect to the maintenance `postgres` database (`-d postgres`) while dropping
> `polymer_intelligence` — you cannot drop the database you are connected to.
>
> If you are restoring to a brand-new/blank server where `pi_user` does not yet
> exist, the simplest path is to let the postgres container create it: set
> `POSTGRES_USER=pi_user` / `POSTGRES_PASSWORD=<secret>` / `POSTGRES_DB=polymer_intelligence`
> in the env so the entrypoint provisions the superuser and database on first
> boot. Otherwise create it manually as an existing superuser:
> ```sql
> CREATE USER pi_user WITH SUPERUSER PASSWORD '<secret>';
> ```

### Step 3: Restore the dump

Run `pg_restore` against the dump file.

> **Important — `--jobs` needs a file, not a pipe.** Parallel restore
> (`--jobs=N`) requires a **seekable dump file**; it fails with
> *"parallel restore from standard input is not supported"* if you pipe the dump
> in via stdin. The dump must therefore be reachable as a **file path** inside
> whichever process runs `pg_restore`. When restoring through the container, copy
> the dump in first (e.g. `docker cp <dump> deploy-postgres-1:/tmp/restore.pgdump`)
> and pass that in-container path. When restoring on the host, pass the host path
> directly. Use `--no-owner --no-privileges` so the restore does not fail on role
> grants that may differ between source and target.

```bash
# Option A — restore through the postgres container (host has no pg client tools):
docker cp "${DUMP}" deploy-postgres-1:/tmp/restore.pgdump
docker compose -f deploy/docker-compose.dev.yml exec postgres \
  pg_restore \
    --username=pi_user \
    --dbname=polymer_intelligence \
    --no-owner \
    --no-privileges \
    --jobs=4 \
    /tmp/restore.pgdump
docker compose -f deploy/docker-compose.dev.yml exec postgres rm -f /tmp/restore.pgdump
```

```bash
# Option B — restore directly on the VPS host (postgres client tools installed):
PGPASSWORD=<secret> pg_restore \
  --host=localhost \
  --port=5432 \
  --username=pi_user \
  --dbname=polymer_intelligence \
  --no-owner \
  --no-privileges \
  --jobs=4 \
  "${DUMP}"
```

### Step 4: Apply any pending Alembic migrations

After restoring the dump, bring the schema to the current migration head to
account for any migrations applied since the dump was taken:

```bash
docker compose -f deploy/docker-compose.dev.yml run --rm api \
  python -m app.entrypoint
```

> `app.entrypoint` runs `alembic upgrade head` under an advisory lock and is
> safe to run against an already-current schema (idempotent).
>
> **Migration scripts must be at least as new as the dump.** A custom-format dump
> carries the source `alembic_version` (e.g. `0004`). The image/source you run
> `app.entrypoint` from must contain that revision and any later ones, otherwise
> alembic aborts with *"Can't locate revision identified by '<rev>'"*. Use the
> `api` image **built from the current repo** (the dev compose bind-mounts
> `../backend:/app`, so a `compose run --rm api` already sees the current
> migrations). If you restore using a stale/baked image, rebuild it
> (`docker compose build api`) or mount the current source before this step.

### Step 5: Re-seed reference data (if needed)

If the dump predates important reference data changes, re-run the seeders:

```bash
docker compose -f deploy/docker-compose.dev.yml run --rm api \
  python -m app.seed.seed_reference

docker compose -f deploy/docker-compose.dev.yml run --rm api \
  python -m app.seed.seed_staff

docker compose -f deploy/docker-compose.dev.yml run --rm api \
  python -m app.seed.seed_sources
```

These seeders are idempotent (`ON CONFLICT DO NOTHING`) — safe to run even if
the rows already exist.

### Step 6: Restart services and verify health

```bash
docker compose -f deploy/docker-compose.dev.yml up -d

# Wait 30 seconds, then check health
sleep 30
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
docker compose -f deploy/docker-compose.dev.yml ps
```

Expected: `api` returns `{"status":"ok","db":"ok","redis":"ok"}`, all containers
show `healthy` or `running`.

---

## 4. Post-Restore Checklist

- [ ] `GET /api/v1/health` returns `200 OK` with `db: ok, redis: ok`
- [ ] `docker compose ps` shows `api`, `worker`, `beat` all **Up**
- [ ] Spot-check a recent signal via the dashboard — data looks consistent with
      the expected recovery point
- [ ] `worker` and `beat` containers are running (check `restart: unless-stopped`
      auto-restart in compose confirms REQ-nfr-reliability)
- [ ] Alert the team: announce the recovery point (dump timestamp) so analysts
      know which time window may have data gaps
- [ ] Re-enable any sources that were disabled before the incident (via
      `PATCH /api/v1/sources/{source_id}` with `{"is_enabled": true}` — requires a
      passing test first, per the source-enable invariant)

---

## 5. Restore Time Target

TZ §6.1.5 requires restore to be achievable in **≤ 2 hours** from declaration
of a disaster event. The target covers:

| Activity                              | Estimated time |
|---------------------------------------|----------------|
| Dump selection and transfer           | 5–15 min       |
| `pg_restore` (< 5 GB dataset)         | 10–30 min      |
| Alembic `upgrade head`               | < 2 min        |
| Seeders (idempotent re-run)          | < 1 min        |
| Service restart + health verification | 2–5 min        |
| **Total**                             | **≈ 20–50 min** |

The 14-daily / 8-weekly retention policy (see §1) ensures a dump within 24 hours
of the incident is always available — meeting the ≤ 2-hour window comfortably.

### Validated by local restore drill

This procedure is exercised end-to-end by `tests/restore/test_restore_local.sh`
(D-04), which `pg_dump`s the live DB, restores it onto a **fresh disposable
PostgreSQL 16 container** (a clean server), brings the schema to head, and
verifies row counts + the 14 ENUMs + `v_live_feed`, gating on the ≤ 2-hour
budget.

| Run | Date | Dataset | Measured elapsed | Budget | Result |
|-----|------|---------|------------------|--------|--------|
| Local drill (this repo) | 2026-06-22 | dev DB (signals 45 / sources 3 / raw_items 0; `v_live_feed` 51) | **4 s** | 7200 s (≤2h) | **PASS** |

> **Validated 2026-06-22:** local restore drill completed in 4 s (well under the
> ≤2 h / TZ §6.1.5 budget) on a < 1 MB dev dataset. The wall-clock scales with
> data volume; the < 5 GB production estimate above (≈ 20–50 min) keeps a wide
> margin under the 2-hour target. A hardware-timing rerun on the customer VPS is
> recorded as a deploy-day row in `06-ACCEPTANCE.md`.

---

## 6. Offsite Storage

The daily cron stores dumps on the **same VPS disk** — sufficient for
application-level data loss recovery but insufficient if the disk itself fails.
For production hardening:

- **rclone** to S3-compatible storage (MinIO offsite, Cloudflare R2, AWS S3)
- **scp/rsync** to a secondary server
- Consider encrypting dumps before transfer (`pg_dump | gpg --symmetric > dump.gpg`)
- Offsite storage setup is a post-MVP operational task; the `BACKUP_DIR` on
  local disk satisfies the TZ §6.1.5 acceptance criterion for Phase 1.
