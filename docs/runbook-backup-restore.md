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

Connect to PostgreSQL as a superuser:

```bash
docker compose -f deploy/docker-compose.dev.yml exec postgres \
  psql -U postgres -c "DROP DATABASE IF EXISTS polymer_intelligence;"
docker compose -f deploy/docker-compose.dev.yml exec postgres \
  psql -U postgres -c "CREATE DATABASE polymer_intelligence OWNER pi_user;"
```

> If you are restoring to a new/blank server, ensure `pi_user` exists first:
> ```sql
> CREATE USER pi_user WITH PASSWORD '<secret>';
> ```

### Step 3: Restore the dump

Run `pg_restore` against the dump file. Adjust paths to match where the dump is
accessible from the postgres container (bind-mount or host path).

```bash
# If the dump is on the host and the postgres container is running:
docker compose -f deploy/docker-compose.dev.yml exec postgres \
  pg_restore \
    --host=localhost \
    --username=pi_user \
    --dbname=polymer_intelligence \
    --no-password \
    --jobs=4 \
    /path/to/dump/pg_polymer_intelligence_<timestamp>.pgdump
```

Or run `pg_restore` directly on the VPS host (if postgres client tools are installed):

```bash
PGPASSWORD=<secret> pg_restore \
  --host=localhost \
  --port=5432 \
  --username=pi_user \
  --dbname=polymer_intelligence \
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
      `POST /admin/sources/{id}/enable` — requires a passing test first, per
      the source-enable invariant)

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
