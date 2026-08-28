#!/usr/bin/env bash
#
# Bring up the whole local stack with one command (`make dev`).
#
# The repo-root CLAUDE.md says "running the stack means all of it", and lists the
# six things that have to be up. The reason it is a script rather than a note is
# that a MISSING piece does not look like a missing process — it looks like a
# broken feature:
#
#   * no worker  -> verification checks sit at «Ожидает» forever, the case never
#                   reaches pending_review, and «Одобрить» reports a decision
#                   nobody made;
#   * no beat    -> poll_didox_documents never runs, and that poller is the only
#                   way we learn a counterparty signed in their own EDI cabinet,
#                   because Didox publishes no webhooks.
#
# Both were missing from a stack reported as "fully up". So this starts all of
# them, and if any one dies it takes the rest down instead of leaving you to
# debug a feature that is merely unplugged.
#
# Not started here: the userbot (needs real TG_API_* credentials) and the
# Telegram Web App (`webapp/`, built as a bundle — see `make webapp-bundle`).
#
# Env: the backend reads `backend/.env` (pydantic-settings resolves env_file
# relative to the process CWD, and these processes run from backend/).

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$PWD"

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; OFF=$'\033[0m'

log()  { printf '%s==>%s %s\n' "$GREEN" "$OFF" "$*"; }
warn() { printf '%s!! %s%s\n' "$YELLOW" "$*" "$OFF"; }
die()  { printf '%s!! %s%s\n' "$RED" "$*" "$OFF" >&2; exit 1; }

# ── preflight ────────────────────────────────────────────────────────────────

docker info >/dev/null 2>&1 || die "Docker is not running — start Docker Desktop first."
command -v uv >/dev/null 2>&1 || die "uv not found (backend is uv-managed): https://docs.astral.sh/uv/"
[ -f "$ROOT/backend/.env" ] || die "backend/.env is missing — the API needs it (see deploy/.env.example)."
[ -d "$ROOT/backend/.venv" ] || die "backend/.venv missing — run: cd backend && uv sync --frozen --extra dev"

for app in portal dashboard; do
  [ -d "$ROOT/$app/node_modules" ] || die "$app/node_modules missing — run: cd $app && npm ci"
done

# A port already in use is the confusing failure: the new process dies, the OLD
# one keeps answering, and you debug code that is not the code you are running.
for port_and_name in "8000 api" "5173 portal" "3000 dashboard"; do
  set -- $port_and_name
  if lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; then
    die "Port $1 ($2) is already in use. Stop the process holding it, then retry."
  fi
done

# ── infrastructure containers ────────────────────────────────────────────────

ensure_container() {
  local name=$1; shift
  if [ -z "$(docker ps -aq -f "name=^${name}$")" ]; then
    log "creating $name"
    docker run -d --name "$name" --restart unless-stopped "$@" >/dev/null
  elif [ -z "$(docker ps -q -f "name=^${name}$")" ]; then
    log "starting $name"
    docker start "$name" >/dev/null
  fi
}

ensure_container pi-pg \
  -p 5432:5432 \
  -e POSTGRES_DB=polymer -e POSTGRES_USER=pi -e POSTGRES_PASSWORD=pi \
  -v pi-pg-data:/var/lib/postgresql/data \
  postgres:16-alpine
ensure_container pi-redis -p 6379:6379 -v pi-redis-data:/data redis:7-alpine
ensure_container pi-minio \
  -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minio -e MINIO_ROOT_PASSWORD=minio12345 \
  -v pi-minio-data:/data \
  minio/minio:latest server /data --console-address ":9001"

printf '%s' "$(log "waiting for postgres")"
for _ in $(seq 1 60); do
  docker exec pi-pg pg_isready -U pi -d polymer >/dev/null 2>&1 && break
  printf '.'; sleep 1
done
printf '\n'
docker exec pi-pg pg_isready -U pi -d polymer >/dev/null 2>&1 \
  || die "postgres did not become ready in 60s (docker logs pi-pg)."

# ── schema + reference data ──────────────────────────────────────────────────

cd "$ROOT/backend"
log "alembic upgrade head"
uv run alembic upgrade head

# Idempotent (ON CONFLICT). Without them a fresh database has no staff user, so
# the dashboard cannot be logged into at all. Set DEV_SEED=0 to skip.
if [ "${DEV_SEED:-1}" = "1" ]; then
  log "seeding reference data, staff and sources"
  for seeder in seed_reference seed_staff seed_sources; do
    uv run python -m "app.seed.$seeder" >/dev/null || warn "$seeder failed (continuing)"
  done
fi
cd "$ROOT"

# ── processes ────────────────────────────────────────────────────────────────

# Monitor mode so each background job becomes its own process group leader. That
# is what makes shutdown work: uvicorn --reload and vite both fork children, and
# killing the job's pid alone would orphan them holding the ports.
set -m

PIDS=""
NAMES=""

run() {
  local name=$1 color=$2 dir=$3; shift 3
  local tag
  tag=$(printf '\033[%sm%-9s\033[0m' "$color" "[$name]")
  (
    cd "$ROOT/$dir"
    "$@" 2>&1 | awk -v tag="$tag" '{ print tag, $0; fflush() }'
  ) &
  PIDS="$PIDS $!"
  NAMES="$NAMES $name"
}

cleanup() {
  trap - EXIT INT TERM
  printf '\n%s==>%s stopping the stack\n' "$GREEN" "$OFF"
  for pid in $PIDS; do
    kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  printf '%sinfrastructure containers left running (make dev-stop)%s\n' "$DIM" "$OFF"
}

# Ctrl-C and a crash are different endings and must not print the same thing.
# The signal handler is separate so that a deliberate stop exits 0 through the
# EXIT trap, instead of falling back into the watchdog — which would then see the
# processes it just killed and announce that one of them had died.
SHUTTING_DOWN=0
on_signal() { SHUTTING_DOWN=1; exit 0; }
trap cleanup EXIT
trap on_signal INT TERM

run api       36 backend   uv run uvicorn app.main:app --reload --port 8000
run worker    33 backend   uv run celery -A app.tasks.celery_app worker -Q ingest,parse,notify,default,verify --loglevel=info
run beat      35 backend   uv run celery -A app.tasks.celery_app beat --loglevel=info
run portal    32 portal    npm run dev
run dashboard 34 dashboard npm run dev

cat <<BANNER

${GREEN}==>${OFF} stack up
      API        http://localhost:8000        (docs: /docs when DEBUG=true)
      portal     http://localhost:5173/cabinet
      dashboard  http://localhost:3000
      MinIO      http://localhost:9001        (minio / minio12345)
    ${DIM}Ctrl-C stops every process. Infra containers keep running.${OFF}

BANNER

# If one process dies the others are still up, which is exactly the state that
# makes a working feature look broken. Take the whole thing down instead.
while true; do
  set -- $PIDS
  i=1
  for pid in "$@"; do
    if [ "$SHUTTING_DOWN" = "0" ] && ! kill -0 "$pid" 2>/dev/null; then
      name=$(echo "$NAMES" | awk -v i="$i" '{print $i}')
      warn "$name exited — shutting the rest down so you do not debug a half-stack"
      exit 1
    fi
    i=$((i + 1))
  done
  sleep 2
done
