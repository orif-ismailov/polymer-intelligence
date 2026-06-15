# pg_backup.sh — Cron Setup Instructions

`deploy/backup/pg_backup.sh` takes a `pg_dump` (custom format) of the
Polymer Intelligence database and rotates dumps using a 14-daily / 8-weekly
retention policy (REQ-nfr-reliability, TZ §6.1.5).

## Prerequisites

- PostgreSQL 16 client tools (`pg_dump`) available in PATH on the backup host
- A dedicated `BACKUP_DIR` on a non-web-served filesystem with adequate space
  (estimate: ≈ 100 MB–1 GB per dump depending on data volume)

## Environment Variables

| Variable      | Default                   | Description                              |
|---------------|---------------------------|------------------------------------------|
| `PGHOST`      | `localhost`               | Postgres host                            |
| `PGPORT`      | `5432`                    | Postgres port                            |
| `PGUSER`      | `pi_user`                 | Postgres user with read access           |
| `PGDATABASE`  | `polymer_intelligence`    | Database name to dump                    |
| `PGPASSWORD`  | _(must be set via env)_   | Never pass as CLI argument (T-02-23)     |
| `BACKUP_DIR`  | `/var/backups/polymer`    | Root directory for dump storage          |
| `DAILY_KEEP`  | `14`                      | Number of daily dumps to keep            |
| `WEEKLY_KEEP` | `8`                       | Number of weekly dumps to keep           |

## Install as a Daily Cron (recommended)

1. Copy the script to the server:

   ```bash
   scp deploy/backup/pg_backup.sh user@vps:/opt/polymer/pg_backup.sh
   chmod 700 /opt/polymer/pg_backup.sh
   ```

2. Create a crontab entry (runs daily at 02:00 UTC):

   ```bash
   crontab -e
   ```

   Add:

   ```cron
   0 2 * * * PGHOST=localhost PGUSER=pi_user PGDATABASE=polymer_intelligence PGPASSWORD=<secret> BACKUP_DIR=/var/backups/polymer /opt/polymer/pg_backup.sh >> /var/log/pg_backup.log 2>&1
   ```

3. Verify the cron entry:

   ```bash
   crontab -l
   ```

## Run as a Docker Compose One-Shot

If you prefer to trigger a backup from inside the compose stack:

```bash
docker compose -f deploy/docker-compose.dev.yml run --rm \
  -e PGHOST=postgres \
  -e PGUSER=pi_user \
  -e PGPASSWORD=<secret> \
  -e PGDATABASE=polymer_intelligence \
  -e BACKUP_DIR=/backups \
  -v /var/backups/polymer:/backups \
  api sh -c "apt-get install -y postgresql-client && /app/deploy/backup/pg_backup.sh"
```

## Manual Test Run

```bash
PGHOST=localhost PGUSER=pi_user PGDATABASE=polymer_intelligence \
PGPASSWORD=devpassword BACKUP_DIR=/tmp/test_backup \
bash deploy/backup/pg_backup.sh
ls -lh /tmp/test_backup/daily/
```

## Security Notes (T-02-23)

- Dump files are created with `chmod 600` (owner-read-only). The `BACKUP_DIR`
  should be owned by the backup user and not accessible to the web server.
- `PGPASSWORD` is consumed via environment variable — never appears in
  `ps aux` output.
- Consider storing dumps off-VPS (S3, SFTP, rclone to offsite) for
  disaster-recovery coverage. The `BACKUP_DIR` on the same disk is insufficient
  if the disk fails.
