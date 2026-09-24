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
# Env: everything reads the ONE `.env` at the repo root. It used to be
# `backend/.env`, because pydantic resolved `env_file` relative to the process
# CWD and these processes run from backend/ — which meant the stack you started
# here and the stack compose started read different files, disagreeing on ten
# keys including JWT_SECRET. `Settings` now takes an absolute path to the root
# file and `backend/.env` is gone.

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
[ -f "$ROOT/.env" ] || die ".env is missing from the repo root — the API needs it (see deploy/.env.example)."
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

# A container is matched by NAME alone, so an existing one is started and trusted
# whatever shape it is in. That is not hypothetical: pi-pg spent weeks attached to
# NO network, with its port binding recorded in HostConfig but never published
# (`NetworkSettings.Ports` = {"5432/tcp":[]}), because it had been created outside
# this script and Docker lost the endpoint. It was reused on every run.
#
# So verify what the container actually DOES, not what it was asked to do.
ensure_container() {
  local name=$1; shift
  local want_ports=() a prev=""
  for a in "$@"; do
    [ "$prev" = "-p" ] && want_ports+=("${a%%:*}")
    prev="$a"
  done

  if [ -z "$(docker ps -aq -f "name=^${name}$")" ]; then
    log "creating $name"
    docker run -d --name "$name" --restart unless-stopped "$@" >/dev/null
  elif [ -z "$(docker ps -q -f "name=^${name}$")" ]; then
    log "starting $name"
    docker start "$name" >/dev/null
  fi

  # `docker inspect` reports two different things and only one of them is real:
  # HostConfig.PortBindings is the REQUEST, NetworkSettings.Ports is what got
  # published. Check the second.
  local published p
  published=$(docker inspect "$name" --format '{{json .NetworkSettings.Ports}}')
  for p in ${want_ports[@]+"${want_ports[@]}"}; do
    case "$published" in
      *"\"HostPort\":\"$p\""*) ;;
      *) die "$name is up but does NOT publish host port $p — docker ps shows: $(docker ps --filter "name=^${name}$" --format '{{.Ports}}')

   A container of that name exists, so this script reused it, but it was created by
   something else (or Docker dropped its network endpoint). Nothing on this machine
   can reach it, and every host-side connection will be refused.

   Its data is in a volume and survives the container, but CHECK WHICH VOLUME before
   you delete anything — a container created outside this script may hold an
   anonymous volume, and recreating it here would mount ${name}-data instead and
   hand you a different, apparently-empty database:

       docker inspect $name --format '{{json .Mounts}}'

   Same volume, fresh container (recommended — replace <vol> with the Name above):
       docker rm -f $name
       docker run -d --name $name --restart unless-stopped $* -v <vol>:<dst>

   Or let this script recreate it against its own named volume:
       docker rm -f $name && make dev" ;;
    esac
  done
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

# Readiness is checked from the HOST, by the same route the app takes — and with a
# real connection, not a port probe.
#
# Two traps, both of which produced a confident wrong answer here:
#
#   * `docker exec pi-pg pg_isready` speaks to the Unix socket INSIDE the container.
#     It stays green when the container publishes no port and nothing on this machine
#     can reach 5432 — the script announced postgres ready and then died several steps
#     later on a raw psycopg "connection refused" from alembic, the one place the
#     failure had nothing to do with migrations. It also reports an exit code and no
#     reason, so a 60s timeout says nothing about why.
#
#   * a bare TCP connect is not a readiness check either. Docker's userland proxy
#     binds the published host port the moment the container exists and accepts
#     connections with NOTHING listening inside, so it passes instantly and always.
#     (The unpublished-port bug is caught by ensure_container reading
#     NetworkSettings.Ports directly, which is authoritative.)
#
# So: open a real connection through SQLAlchemy using the app's own DATABASE_URL,
# and let the last exception be the error message.
log "waiting for postgres (real connection, 127.0.0.1:5432)"
( cd "$ROOT/backend" && uv run python - <<'PY'
import sys, time
from sqlalchemy import create_engine, text
from app.core.config import settings

last = None
deadline = time.time() + 90
while time.time() < deadline:
    try:
        engine = create_engine(settings.DATABASE_URL, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 — the reason IS the output
        last = exc
        time.sleep(1)
print(f"postgres never accepted a connection: {type(last).__name__}: {last}", file=sys.stderr)
sys.exit(1)
PY
) || die "postgres did not accept a connection in 90s (reason above; also: docker logs pi-pg)."

# MinIO next, because the bucket step below talks to it. Its own liveness endpoint,
# which answers only once the server is actually serving.
log "waiting for minio (127.0.0.1:9000)"
for _ in $(seq 1 60); do
  curl -fsS -o /dev/null "http://127.0.0.1:9000/minio/health/live" 2>/dev/null && break
  sleep 1
done
curl -fsS -o /dev/null "http://127.0.0.1:9000/minio/health/live" 2>/dev/null \
  || die "minio is not serving at 127.0.0.1:9000 after 60s (docker logs pi-minio)."

# Redis: a real PING, not a port probe.
log "waiting for redis (127.0.0.1:6379)"
for _ in $(seq 1 60); do
  [ "$(docker exec pi-redis redis-cli PING 2>/dev/null)" = "PONG" ] && break
  sleep 1
done
[ "$(docker exec pi-redis redis-cli PING 2>/dev/null)" = "PONG" ] \
  || die "redis did not answer PING in 60s (docker logs pi-redis)."

# ── schema + reference data ──────────────────────────────────────────────────

cd "$ROOT/backend"
log "alembic upgrade head"
uv run alembic upgrade head

# The S3 bucket is NOT created by the app: nothing calls ensure_bucket() at startup
# or from the core seeder. Compose has a whole `createbuckets` service for it
# (mc mb --ignore-existing) and runs it BEFORE the api; this script had no
# equivalent, so a fresh MinIO volume left uploads failing with NoSuchBucket.
#
# It must come BEFORE seeding, not after: seed_contract_templates writes the three
# template bodies to S3 via storage_service.store_contract_template, so on an empty
# bucket the seeder dies there and takes seed_substances — and, on the retry you
# then run, nothing — with it. Uses the app's own idempotent helper so it honours
# S3_BUCKET/S3_ENDPOINT from the one .env everything else reads.
log "ensuring the S3 bucket exists"
uv run python -c "from app.core.storage import ensure_bucket; ensure_bucket()" \
  || die "could not create the S3 bucket — is minio up? contract templates and every upload need it."

# Idempotent (ON CONFLICT). Without them a fresh database has no staff user, so
# the dashboard cannot be logged into at all. Set DEV_SEED=0 to skip.
#
# This ran three of the five seeders until 09.09.2026, so `make dev` built a
# database with no contract_templates and no substances — a database where the
# contract chain and the compliance gate cannot be exercised, which reads as two
# broken features rather than a short list. The list lives in app/seed/__main__.py.
if [ "${DEV_SEED:-1}" = "1" ]; then
  log "seeding reference data, staff, sources, contract templates and substances"
  # Fatal, not a warn. This swallowed its own failure into a yellow line until
  # 22.09.2026, which is how a fresh stack came up with no admin user, no contract
  # templates and no substances — read as three broken features rather than one
  # failed command whose traceback had already scrolled past.
  uv run python -m app.seed >/dev/null \
    || die "seeding failed — traceback above. Retry by hand: cd backend && uv run python -m app.seed"
fi

cd "$ROOT"

# ── processes ────────────────────────────────────────────────────────────────

# `telegram` and `userbot` are repo-root packages, NOT inside backend/ — and these
# processes run from backend/, so neither is on sys.path. Compose solves it with
# `PYTHONPATH: /app` plus read-only mounts (see the api/worker/beat services); this
# is the same thing for the local stack, where the repo root IS the import root.
#
# Without it the stack looks completely healthy and every notify-queue task dies on
# ModuleNotFoundError at dispatch: send_status_change_notification,
# publish_report_to_channel, publish_breaking_news, check_userbot_health. Which is
# the exact failure mode this script exists to prevent — a missing piece reading as
# four broken features rather than one absent path entry.
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

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
