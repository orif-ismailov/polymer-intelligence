#!/usr/bin/env bash
# =============================================================================
# pg_backup.sh — PostgreSQL 16 backup with daily + weekly retention
#
# Usage (manual):
#   PGHOST=localhost PGUSER=pi_user PGDATABASE=polymer_intelligence \
#   PGPASSWORD=secret BACKUP_DIR=/var/backups/polymer ./pg_backup.sh
#
# Environment variables (all have sensible defaults for dev):
#   PGHOST       — Postgres host            (default: localhost)
#   PGPORT       — Postgres port            (default: 5432)
#   PGUSER       — Postgres user            (default: pi_user)
#   PGDATABASE   — Database name            (default: polymer_intelligence)
#   PGPASSWORD   — Postgres password        (set via env; not recommended as arg)
#   BACKUP_DIR   — Destination directory    (default: /var/backups/polymer)
#   DAILY_KEEP   — Daily dumps to retain    (default: 14)
#   WEEKLY_KEEP  — Weekly dumps to retain   (default: 8)
#
# Retention policy (REQ-nfr-reliability, TZ §6.1.5):
#   - 14 most-recent daily backups retained (≈ 2 weeks of daily coverage)
#   - 8 most-recent weekly backups retained (≈ 2 months of weekly coverage)
#   - Restore target: ≤ 2 hours (pg_restore of a custom-format dump + schema head)
#
# Security (T-02-23):
#   - Dumps are written with umask 077 / chmod 600 so only the backup user
#     can read them. Store BACKUP_DIR on a non-web-served filesystem.
#   - PGPASSWORD is accepted via environment variable — never pass it as a
#     command-line argument (it would appear in the process table).
#
# Install as a daily cron:
#   See deploy/backup/README.md for cron setup instructions.
# =============================================================================
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-pi_user}"
PGDATABASE="${PGDATABASE:-polymer_intelligence}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/polymer}"
DAILY_KEEP="${DAILY_KEEP:-14}"
WEEKLY_KEEP="${WEEKLY_KEEP:-8}"

# ── Derived paths ──────────────────────────────────────────────────────────────
DAILY_DIR="${BACKUP_DIR}/daily"
WEEKLY_DIR="${BACKUP_DIR}/weekly"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
DOW=$(date -u +"%u")   # 1=Monday … 7=Sunday; weekly dump on Monday (dow=1)

DUMP_FILE="${DAILY_DIR}/pg_${PGDATABASE}_${TIMESTAMP}.pgdump"

# ── Prepare directories ────────────────────────────────────────────────────────
# umask 077 ensures newly created files/dirs are owner-read-only (T-02-23)
umask 077
mkdir -p "${DAILY_DIR}" "${WEEKLY_DIR}"

# ── Run pg_dump (custom format: smallest, fastest, supports selective restore) ─
echo "[pg_backup] Starting dump of ${PGDATABASE} @ ${PGHOST}:${PGPORT} → ${DUMP_FILE}"
pg_dump \
    --host="${PGHOST}" \
    --port="${PGPORT}" \
    --username="${PGUSER}" \
    --dbname="${PGDATABASE}" \
    --format=custom \
    --compress=6 \
    --file="${DUMP_FILE}"

chmod 600 "${DUMP_FILE}"  # belt-and-suspenders on top of umask (T-02-23)
echo "[pg_backup] Dump complete: ${DUMP_FILE}"

# ── Weekly copy (Mondays only) ─────────────────────────────────────────────────
if [ "${DOW}" -eq 1 ]; then
    WEEKLY_FILE="${WEEKLY_DIR}/pg_${PGDATABASE}_week_${TIMESTAMP}.pgdump"
    cp "${DUMP_FILE}" "${WEEKLY_FILE}"
    chmod 600 "${WEEKLY_FILE}"
    echo "[pg_backup] Weekly copy created: ${WEEKLY_FILE}"
fi

# ── Retention pruning (keep newest N, delete the rest) ────────────────────────
# Daily: keep $DAILY_KEEP newest files
echo "[pg_backup] Pruning daily backups (keep ${DAILY_KEEP})"
ls -1t "${DAILY_DIR}"/*.pgdump 2>/dev/null | tail -n "+$((DAILY_KEEP + 1))" | while read -r OLD; do
    echo "[pg_backup] Removing old daily backup: ${OLD}"
    rm -f "${OLD}"
done

# Weekly: keep $WEEKLY_KEEP newest files
echo "[pg_backup] Pruning weekly backups (keep ${WEEKLY_KEEP})"
ls -1t "${WEEKLY_DIR}"/*.pgdump 2>/dev/null | tail -n "+$((WEEKLY_KEEP + 1))" | while read -r OLD; do
    echo "[pg_backup] Removing old weekly backup: ${OLD}"
    rm -f "${OLD}"
done

echo "[pg_backup] Done. Retained: ${DAILY_KEEP} daily, ${WEEKLY_KEEP} weekly."
