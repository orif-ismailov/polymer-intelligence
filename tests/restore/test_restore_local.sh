#!/usr/bin/env bash
# =============================================================================
# test_restore_local.sh — D-04 / TZ §6.1.5 local restore drill
#
# Proves the DB restore *procedure* end-to-end on a CLEAN PostgreSQL 16 server
# (a fresh disposable container) before handover. It:
#   1. Records a start epoch (wall-clock timing begins).
#   2. Takes a `pg_dump --format=custom --compress=6` of the running dev DB.
#   3. Captures source row counts for signals / raw_items / sources.
#   4. Spins up a FRESH disposable `postgres:16-alpine` container (distinct name +
#      port + ephemeral tmpfs storage — NEVER the dev `postgres_data` volume) as
#      the "clean server" the customer would restore onto.
#   5. Restores into it via the SAME commands as runbook §3 (CREATE DATABASE +
#      `pg_restore --jobs=4`), then applies pending Alembic migrations via the
#      runbook Step-4 `python -m app.entrypoint` (idempotent — safe on a current
#      schema).
#   6. Verifies: per-table row-count equality, the 14 locked ENUMs are present,
#      and `SELECT COUNT(*) FROM v_live_feed` succeeds (the view restored).
#   7. Records an end epoch, prints elapsed seconds, and ASSERTS elapsed < 7200
#      (the ≤2h / TZ §6.1.5 budget).
#   8. Tears down the disposable container + dump file on exit (trap).
#
# Usage (manual):
#   ./tests/restore/test_restore_local.sh
#   COMPOSE_FILE=deploy/docker-compose.dev.yml ./tests/restore/test_restore_local.sh
#
# Environment variables (all have sensible dev defaults):
#   PGHOST          — dev Postgres host                (default: localhost)
#   PGPORT          — dev Postgres port                (default: 5432)
#   PGUSER          — Postgres superuser/role          (default: pi_user)
#   PGDATABASE      — Database name                     (default: polymer_intelligence)
#   PGPASSWORD      — Postgres password                 (default: devpassword)
#   COMPOSE_FILE    — dev compose file                  (default: deploy/docker-compose.dev.yml)
#   PG_IMAGE        — disposable server image           (default: postgres:16-alpine)
#   RESTORE_PORT    — host port for disposable server   (default: 55432)
#   API_IMAGE       — image carrying app.entrypoint     (default: deploy-api)
#   DOCKER_NET      — docker network linking api↔restore (default: deploy_default)
#   RESTORE_BUDGET  — restore budget in seconds         (default: 7200, the 2h target)
#   SKIP_MIGRATIONS — set to 1 to skip the Step-4 alembic upgrade head
#
# Data / security contract (T-06-03 / T-06-05):
#   - Operates on locally-SEEDED SYNTHETIC reference/demo data only. NO production
#     rows and NO real credentials are present — the dev DB uses the documented
#     `devpassword`. Do not point this at a real customer DB.
#   - The dump is written to a `mktemp` path under `umask 077` and removed on exit
#     (trap), so no world-readable dump is left behind.
#   - The disposable restore target is a distinct container/port/tmpfs server; it
#     can never overwrite the dev `postgres_data` volume (T-06-04). The dev DB is a
#     read-only source here.
# =============================================================================
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-pi_user}"
PGDATABASE="${PGDATABASE:-polymer_intelligence}"
PGPASSWORD="${PGPASSWORD:-devpassword}"
COMPOSE_FILE="${COMPOSE_FILE:-deploy/docker-compose.dev.yml}"
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"
RESTORE_PORT="${RESTORE_PORT:-55432}"
API_IMAGE="${API_IMAGE:-deploy-api}"
DOCKER_NET="${DOCKER_NET:-deploy_default}"
RESTORE_BUDGET="${RESTORE_BUDGET:-7200}"   # ≤2h = 7200s (TZ §6.1.5)
SKIP_MIGRATIONS="${SKIP_MIGRATIONS:-0}"

# Unique names so we never collide with the dev stack containers/volumes.
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RESTORE_CTR="pi-restore-drill-${RUN_ID}"
RESTORE_ALIAS="pi-restore-drill"          # stable network alias for the api image
COMPOSE="docker compose -f ${COMPOSE_FILE}"

export PGPASSWORD

# ── mktemp dump path with owner-only perms (T-06-03) ─────────────────────────
umask 077
DUMP_FILE="$(mktemp -t pi_restore_drill.XXXXXX.pgdump)"

# ── Cleanup trap — remove the disposable container + dump on ANY exit ─────────
cleanup() {
    local rc=$?
    echo "[restore-drill] Cleaning up disposable container + dump file…"
    docker rm -f "${RESTORE_CTR}" >/dev/null 2>&1 || true
    rm -f -- "${DUMP_FILE}" >/dev/null 2>&1 || true
    exit "${rc}"
}
trap cleanup EXIT INT TERM

fail() { echo "[restore-drill] FAIL: $*" >&2; exit 1; }
note() { echo "[restore-drill] $*"; }

# Run psql inside the disposable restore container (it ships pg client tools).
restore_psql() {
    docker exec -e PGPASSWORD="${PGPASSWORD}" "${RESTORE_CTR}" \
        psql -U "${PGUSER}" -d "$1" -tAc "$2"
}

# ── 0. Preflight ─────────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || fail "docker is required but not found."
docker info >/dev/null 2>&1 || fail "docker daemon is not running."

note "Checking the dev stack postgres is up (read-only source)…"
${COMPOSE} ps postgres >/dev/null 2>&1 || fail "dev compose not available."
docker compose -f "${COMPOSE_FILE}" exec -T postgres pg_isready -U "${PGUSER}" -d "${PGDATABASE}" >/dev/null 2>&1 \
    || fail "dev postgres not ready (start it: ${COMPOSE} up -d postgres)."

# ── 1. Start the wall-clock ───────────────────────────────────────────────────
START_EPOCH="$(date +%s)"
note "Restore drill START — budget ${RESTORE_BUDGET}s (≤2h, TZ §6.1.5)."

# ── 1a. Seed the source DB if empty so row counts are non-trivial ────────────
SRC_SIGNALS="$(docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    psql -U "${PGUSER}" -d "${PGDATABASE}" -tAc 'SELECT count(*) FROM signals;' | tr -d '[:space:]')"
if [ "${SRC_SIGNALS:-0}" -eq 0 ]; then
    note "Source DB has 0 signals — seeding synthetic reference/demo data first…"
    ${COMPOSE} exec -T api python -m app.seed.seed_reference >/dev/null 2>&1 || true
    ${COMPOSE} exec -T api python -m app.seed.seed_sources   >/dev/null 2>&1 || true
    ${COMPOSE} exec -T api python -m app.seed.seed_demo      >/dev/null 2>&1 || true
fi

# ── 2. pg_dump the running dev DB (custom format) ────────────────────────────
note "Dumping ${PGDATABASE} (custom format, compress=6) → ${DUMP_FILE}"
docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    pg_dump -U "${PGUSER}" -d "${PGDATABASE}" \
        --format=custom --compress=6 --no-owner --no-privileges \
    > "${DUMP_FILE}"
[ -s "${DUMP_FILE}" ] || fail "dump file is empty."
note "Dump complete: $(wc -c < "${DUMP_FILE}") bytes."

# ── 3. Capture source row counts ─────────────────────────────────────────────
declare -A SRC_COUNTS
for tbl in signals raw_items sources; do
    SRC_COUNTS[$tbl]="$(docker compose -f "${COMPOSE_FILE}" exec -T postgres \
        psql -U "${PGUSER}" -d "${PGDATABASE}" -tAc "SELECT count(*) FROM ${tbl};" | tr -d '[:space:]')"
    note "source ${tbl} = ${SRC_COUNTS[$tbl]}"
done

# ── 4. Spin up a FRESH disposable postgres:16-alpine (clean server) ──────────
# Distinct name + host port + tmpfs data dir (no volume) so the dev
# postgres_data volume can NEVER be touched (T-06-04). Attached to the dev
# network with a stable alias so the api image can reach it for migrations.
note "Starting disposable ${PG_IMAGE} as '${RESTORE_CTR}' (port ${RESTORE_PORT}, tmpfs)…"
docker run -d \
    --name "${RESTORE_CTR}" \
    --network "${DOCKER_NET}" \
    --network-alias "${RESTORE_ALIAS}" \
    -e POSTGRES_USER="${PGUSER}" \
    -e POSTGRES_PASSWORD="${PGPASSWORD}" \
    -e POSTGRES_DB="${PGDATABASE}" \
    -p "${RESTORE_PORT}:5432" \
    --tmpfs /var/lib/postgresql/data \
    "${PG_IMAGE}" >/dev/null

note "Waiting for the disposable server to become ready…"
for _ in $(seq 1 30); do
    if docker exec "${RESTORE_CTR}" pg_isready -U "${PGUSER}" -d "${PGDATABASE}" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done
docker exec "${RESTORE_CTR}" pg_isready -U "${PGUSER}" -d "${PGDATABASE}" >/dev/null 2>&1 \
    || fail "disposable postgres never became ready."

# ── 5. Restore into the clean server (runbook §3 Steps 2-3) ──────────────────
# Step 2 — clean target DB. The POSTGRES_DB above already auto-creates
# polymer_intelligence; DROP/CREATE here mirrors the runbook verbatim so the
# drill exercises the exact documented commands.
note "Restore Step 2 — recreate a clean target database…"
restore_psql postgres "DROP DATABASE IF EXISTS ${PGDATABASE};" >/dev/null
restore_psql postgres "CREATE DATABASE ${PGDATABASE} OWNER ${PGUSER};" >/dev/null

note "Restore Step 3 — pg_restore --jobs=4…"
docker exec -i -e PGPASSWORD="${PGPASSWORD}" "${RESTORE_CTR}" \
    pg_restore --username="${PGUSER}" --dbname="${PGDATABASE}" \
        --no-owner --no-privileges --jobs=4 < "${DUMP_FILE}"

# ── 5a. Apply pending migrations (runbook Step 4) ────────────────────────────
if [ "${SKIP_MIGRATIONS}" != "1" ]; then
    note "Restore Step 4 — alembic upgrade head via app.entrypoint (idempotent)…"
    docker run --rm \
        --network "${DOCKER_NET}" \
        -e DATABASE_URL="postgresql+psycopg://${PGUSER}:${PGPASSWORD}@${RESTORE_ALIAS}:5432/${PGDATABASE}" \
        "${API_IMAGE}" python -m app.entrypoint \
        || fail "alembic upgrade head failed on the restored DB."
else
    note "SKIP_MIGRATIONS=1 — skipping the Step-4 alembic upgrade head."
fi

# ── 6. Verify the restored DB ─────────────────────────────────────────────────
note "Verifying restored schema + rows + view + ENUMs…"

# 6a. Per-table row-count equality
for tbl in signals raw_items sources; do
    got="$(restore_psql "${PGDATABASE}" "SELECT count(*) FROM ${tbl};" | tr -d '[:space:]')"
    want="${SRC_COUNTS[$tbl]}"
    [ "${got}" = "${want}" ] || fail "row count mismatch for ${tbl}: restored=${got} source=${want}"
    note "OK ${tbl}: ${got} rows match source."
done

# 6b. ENUM presence — assert the 14 locked ENUMs are present
ENUM_COUNT="$(restore_psql "${PGDATABASE}" "SELECT count(*) FROM pg_type WHERE typcategory='E';" | tr -d '[:space:]')"
[ "${ENUM_COUNT}" -ge 14 ] || fail "expected ≥14 ENUMs, restored DB has ${ENUM_COUNT}."
note "OK ENUMs: ${ENUM_COUNT} present (pg_type WHERE typcategory='E')."

# 6c. v_live_feed view exists and is queryable
FEED_COUNT="$(restore_psql "${PGDATABASE}" "SELECT count(*) FROM v_live_feed;" | tr -d '[:space:]')"
note "OK v_live_feed: ${FEED_COUNT} rows (view restored, SELECT COUNT(*) succeeds)."

# ── 7. Stop the clock + assert ≤2h budget ────────────────────────────────────
END_EPOCH="$(date +%s)"
ELAPSED=$(( END_EPOCH - START_EPOCH ))
note "Restore drill ELAPSED: ${ELAPSED}s (budget ${RESTORE_BUDGET}s / ≤2h, TZ §6.1.5)."
if [ "${ELAPSED}" -lt "${RESTORE_BUDGET}" ]; then
    note "PASS — elapsed ${ELAPSED}s is UNDER the ${RESTORE_BUDGET}s (2h) budget."
else
    fail "elapsed ${ELAPSED}s EXCEEDS the ${RESTORE_BUDGET}s (2h) budget."
fi

note "RESTORE DRILL PASSED."
# cleanup() runs on EXIT (removes disposable container + dump).
