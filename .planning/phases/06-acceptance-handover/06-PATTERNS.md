# Phase 6: Acceptance & Handover - Pattern Map

**Mapped:** 2026-06-19
**Files analyzed:** 9 new/modified artifacts
**Analogs found:** 8 / 9

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `.planning/phases/06-acceptance-handover/06-ACCEPTANCE.md` | doc/acceptance | request-response | `.planning/phases/04-dashboard-source-constructor/04-ACCEPTANCE.md` | exact |
| `tests/smoke/test_smoke_full_stack.sh` (or Makefile target) | test/script | batch (compose up → sequential steps) | `backend/tests/test_source_failure_alert.py` + runbook steps | role-match |
| `backend/tests/test_telegram_channel_close.py` | test | request-response + event-driven | `backend/tests/test_parse_telegram.py`, `backend/tests/test_source_wizard.py` | exact |
| `tests/restore/test_restore_local.sh` | test/script | batch (pg_dump → restore → verify) | `deploy/backup/pg_backup.sh`, `docs/runbook-backup-restore.md` | role-match |
| `deploy/docker-compose.yml` | config/infra | batch | `deploy/docker-compose.dev.yml` | exact |
| `docs/deployment-guide.md` | doc | n/a | `docs/polymer-intelligence-dev-spec.md`, `docs/runbook-backup-restore.md` | role-match |
| `docs/admin-guide-ru.md` | doc | n/a | `docs/polymer-intelligence-dev-spec.md` (structure only) | partial |
| `HANDOVER.md` | doc/index | n/a | `.planning/phases/05-telegram-monitoring-ai/05-UAT.md` (index pattern) | partial |
| `backend/uv.lock` (or pinned deps) | config | n/a | `backend/pyproject.toml` | exact |

---

## Pattern Assignments

### `06-ACCEPTANCE.md` (doc/acceptance)

**Analog:** `.planning/phases/04-dashboard-source-constructor/04-ACCEPTANCE.md`

**Document header pattern** (lines 1–10):
```markdown
# Phase 4: Dashboard + Source Constructor — Acceptance Document

**Phase:** 04-dashboard-source-constructor
**Requirements:** REQ-live-feed, REQ-purchase-requests, ...
**Created:** 2026-06-18
**Status:** Pending deploy-time verification (see Deferred Items)
```

**Per-criterion section structure** (lines 20–50, repeated per SC):
```markdown
## SC#1 — Live Feed (REQ-live-feed)

**Full criterion:** <verbatim TZ §6.1.x text>

### Automated CI Proxy

```bash
cd backend && pytest tests/test_feed_api.py -x -q
```

**Proxy coverage:**
- `test_X.py` (N tests): <what it proves>

### Deploy-Time Live Drill

1. Step …
2. Step …

**Pass criteria:** All N steps succeed.
```

**Deferred items table pattern** (lines 276–281):
```markdown
| Category | Item | Status | Deferred At |
|---|---|---|---|
| UAT / Phase 4 SC#1–SC#5 | Live dashboard drill … Prerequisites: … CI gate: … | Pending — deploy-time UAT | 2026-06-18 |
```

**Adaptation for Phase 6:** Replace SC#1–SC#5 with TZ §6.1.1–§6.1.6. Add a "Blocked on customer input" column per D-01. Consolidate deferred items from `02-UAT.md`, `03-UAT.md`, `05-UAT.md` into a single deploy-day checklist section. Retire SC#5 telegram caveat explicitly once D-03 passes.

---

### `tests/smoke/test_smoke_full_stack.sh` (bash script / Makefile target)

**Analog A:** `backend/tests/test_source_failure_alert.py` — pattern for live-DB guard + isolation test structure

**Live-DB guard pattern** (lines 33–42 of `test_source_failure_alert.py`):
```python
_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and ("localhost" in _DB_URL or "postgres" in _DB_URL) and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "source failure alert DB tests require a live PostgreSQL 16 instance. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)
```

**Analog B:** `docs/runbook-backup-restore.md` — ordered shell step pattern for compose-based sequencing:
```bash
# Step 1: Stop services
docker compose -f deploy/docker-compose.dev.yml stop api worker beat

# Step 6: Restart and verify health
docker compose -f deploy/docker-compose.dev.yml up -d
sleep 30
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
docker compose -f deploy/docker-compose.dev.yml ps
```

**Analog C:** `deploy/docker-compose.dev.yml` — healthcheck pattern to gate sequenced steps:
```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -f http://localhost:8000/api/v1/health || exit 1"]
  interval: 30s
  timeout: 10s
  retries: 3
```

**Smoke script structure to follow:**
```bash
#!/usr/bin/env bash
set -euo pipefail

COMPOSE="docker compose -f deploy/docker-compose.yml"

# 1. compose up (full stack)
$COMPOSE up -d
echo "[smoke] Waiting for health..."
until curl -sf http://localhost:8000/api/v1/health | grep -q '"status":"ok"'; do sleep 5; done

# 2. migrate + seed (idempotent — already in api entrypoint command)

# 3. /health check
curl -sf http://localhost:8000/api/v1/health

# 4. submit synthetic request → verify in v_live_feed

# 5. force fake-source failure → observe isolation + source_failure alert
#    Pattern: exercise run_source_fetch_isolated via direct task call
celery -A app.tasks.celery_app call ingest.run_source_fetch_isolated \
  --args '[<fake_source_id>]'

$COMPOSE down
echo "[smoke] PASSED"
```

**Key: invoke `run_source_fetch_isolated` and `source_failure` dedupe** the same way `test_source_failure_alert.py` exercises them — by patching the adapter's `fetch()` to raise an exception 3× and asserting exactly one `alerts` row with `kind='source_failure'`.

---

### `backend/tests/test_telegram_channel_close.py` (test, event-driven)

**Primary analog:** `backend/tests/test_parse_telegram.py`

**Mock helper pattern** (lines 31–60 of `test_parse_telegram.py`):
```python
def _make_raw_item(
    id_: int = 1,
    source_id: int = 100,
    parse_status: str = "pending",
    content: str | None = "Продаю ПП Т30С 50 тонн, $900/т, у.е. EXW Ташкент",
) -> MagicMock:
    """Return a mock RawItem with sensible defaults."""
    ri = MagicMock()
    ri.id = id_
    ri.source_id = source_id
    ri.parse_status = parse_status
    ri.content = content
    ri.event_at = None
    ri.payload = {}
    return ri
```

**Import pattern** (lines 1–23 of `test_parse_telegram.py`):
```python
from __future__ import annotations
from decimal import Decimal
from unittest.mock import MagicMock, call, patch
import pytest
from parsing.schemas import BudgetExceeded, ExtractionResult, SignalKind, UrgencyLevel
```

**Secondary analog:** `backend/tests/test_source_wizard.py` — for the enable-gate and pending-source pattern:

**Auth headers + mock source pattern** (lines 34–60 of `test_source_wizard.py`):
```python
def _make_staff_user(role: str, user_id: int = 1, is_active: bool = True):
    from app.models.enums import StaffRole
    user = MagicMock()
    user.id = user_id
    user.email = f"{role}@polymer.uz"
    user.role = StaffRole(role)
    user.is_active = is_active
    return user

def _auth_headers(user_id: int, role: str) -> dict[str, str]:
    from app.core.security import create_access_token
    token = create_access_token(subject=str(user_id), role=role)
    return {"Authorization": f"Bearer {token}"}
```

**Key-free fixture contract** (from `test_telegram_accuracy.py` docstring):
```python
"""
Key-free CI contract:
  The gate test NEVER makes a live Anthropic call — it reads frozen predictions.
  The test imports are safe under ANTHROPIC_API_KEY=sk-ant-ci-placeholder.
"""
```

**Test structure for D-03 close:**
```python
class TestTelegramChannelClose:
    """Prove the full telegram_channel slice without real credentials (D-03)."""

    def test_enable_gate_rejects_unverified_source(self, client, admin_headers):
        """is_enabled=True on source with last_test_ok_at=NULL → 422."""
        # Use pattern from test_source_wizard.py::test_enable_gate_returns_422_when_no_test_passed

    def test_fixture_message_through_parse_telegram_item(self):
        """Feed a fixture raw_item through parse_telegram_item → signal in v_live_feed."""
        # Use _make_raw_item() + patch("app.tasks.parse.extract_signal") pattern
        # from test_parse_telegram.py happy-path test

    def test_signal_lands_in_v_live_feed(self):
        """Assert the extracted signal is queryable via the feed view."""
```

---

### `tests/restore/test_restore_local.sh` (bash script, batch)

**Primary analog:** `deploy/backup/pg_backup.sh`

**Script header pattern** (lines 1–32 of `pg_backup.sh`):
```bash
#!/usr/bin/env bash
# =============================================================================
# <script name> — <one-line description>
#
# Usage (manual):
#   VAR=value ./script.sh
#
# Environment variables (all have sensible defaults for dev):
#   PGHOST       — Postgres host   (default: localhost)
#   ...
# =============================================================================
set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-pi_user}"
PGDATABASE="${PGDATABASE:-polymer_intelligence}"
```

**Restore sequence to follow** (`docs/runbook-backup-restore.md` §3, Steps 1–6):
```bash
# Step 1: Stop services
docker compose -f deploy/docker-compose.dev.yml stop api worker beat

# Step 2: Create clean target DB
docker compose -f deploy/docker-compose.dev.yml exec postgres \
  psql -U postgres -c "DROP DATABASE IF EXISTS polymer_intelligence;"
docker compose -f deploy/docker-compose.dev.yml exec postgres \
  psql -U postgres -c "CREATE DATABASE polymer_intelligence OWNER pi_user;"

# Step 3: Restore
pg_restore --host=localhost --port=5432 --username=pi_user \
  --dbname=polymer_intelligence --jobs=4 "${DUMP}"

# Step 4: Apply pending migrations
docker compose -f deploy/docker-compose.dev.yml run --rm api python -m app.entrypoint

# Step 6: Verify health
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

**Post-restore verification to add beyond the runbook:**
- Row count check per major table (`SELECT COUNT(*) FROM signals`, `raw_items`, `sources`)
- ENUM presence check: `SELECT typname FROM pg_type WHERE typcategory='E'`
- `v_live_feed` query: `SELECT COUNT(*) FROM v_live_feed`
- Record wall-clock start/end time against ≤2 h budget (TZ §6.1.5)

---

### `deploy/docker-compose.yml` (config/infra, production)

**Primary analog:** `deploy/docker-compose.dev.yml` (full file read above)

**Service block pattern — postgres** (lines 16–35 of dev compose):
```yaml
postgres:
  image: postgres:16-alpine
  restart: unless-stopped
  env_file:
    - path: ../.env
      required: false
  environment:
    POSTGRES_DB: polymer_intelligence
    POSTGRES_USER: pi_user
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-devpassword}
  volumes:
    - postgres_data:/var/lib/postgresql/data
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U pi_user -d polymer_intelligence"]
    interval: 10s
    timeout: 5s
    retries: 5
```

**Service block pattern — api** (lines 71–109 of dev compose):
```yaml
api:
  build:
    context: ../backend
    dockerfile: Dockerfile
  restart: unless-stopped
  env_file:
    - path: ../.env
      required: false
  environment:
    DATABASE_URL: postgresql+psycopg://pi_user:${POSTGRES_PASSWORD:-devpassword}@postgres:5432/polymer_intelligence
    REDIS_URL: redis://redis:6379/0
    S3_ENDPOINT: http://minio:9000
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  command: sh -c "python -m app.entrypoint && python -m app.seed.seed_reference && python -m app.seed.seed_staff && uvicorn app.main:app --host 0.0.0.0 --port 8000"
  healthcheck:
    test: ["CMD-SHELL", "curl -f http://localhost:8000/api/v1/health || exit 1"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Service block pattern — userbot** (lines 158–197 of dev compose):
```yaml
userbot:
  build:
    context: ../backend
    dockerfile: Dockerfile
  restart: unless-stopped
  env_file:
    - path: ../.env
      required: false
  environment:
    DATABASE_URL: postgresql+psycopg://...
    TG_API_ID: ${TG_API_ID:-}
    TG_API_HASH: ${TG_API_HASH:-}
    TG_SESSION_STRING: ${TG_SESSION_STRING:-}
    USERBOT_CHANNEL_REREAD_SECONDS: ${USERBOT_CHANNEL_REREAD_SECONDS:-600}
    USERBOT_HEARTBEAT_SECONDS: ${USERBOT_HEARTBEAT_SECONDS:-60}
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  command: python -m userbot.main
```

**Production delta vs. dev compose:**
- Remove `volumes: - ../backend:/app` (no live-reload in prod)
- Remove `--reload` from uvicorn command
- Add `dashboard` service: build from `deploy/Dockerfile.dashboard`, serve built static files
- nginx mounts `deploy/nginx/nginx.conf` (TLS) instead of `nginx.dev.conf`
- No ports exposed on api/worker/beat/userbot (only nginx:80/443 exposed externally)
- `minio` service stays for S3 file storage (or swap for external S3 env vars)
- Add `RUN_MIGRATIONS_ON_STARTUP=true` env var or keep entrypoint command pattern

**nginx pattern for prod** (`deploy/nginx/nginx.conf` lines 1–5):
```nginx
# Polymer Intelligence — nginx reverse proxy
# TLS-ready: certbot cert paths referenced; plain HTTP → HTTPS redirect stub.
# Serves the built static webapp, proxies /api to the api container.
```

---

### `docs/deployment-guide.md` (doc, ops)

**Analog:** `docs/polymer-intelligence-dev-spec.md` (section structure), `docs/runbook-backup-restore.md` (step-by-step shell commands pattern)

**Section structure from `runbook-backup-restore.md`:**
```markdown
# Runbook: Backup & Restore — Polymer Intelligence

**Restore target:** ≤ 2 hours (TZ §6.1.5)

## Table of Contents
1. [Section A](#section-a)
2. [Section B](#section-b)

---

## 1. Section A

| Column | Column |
|---|---|
| Row | Row |

### Step N: <action>

```bash
<exact command>
```

> **Note:** Callout for important caveats
```

**Deployment guide sections to cover (D-05.2):**
1. Prerequisites (server OS, domain, ports)
2. Env/secrets matrix — table: `VAR`, `Description`, `Source`, `Example`
3. TLS via certbot
4. First-run: `docker compose up`, migrate+seed, verify `/health`
5. Aiogram bot webhook setup (`BOT_TOKEN`, webhook URL registration)
6. Userbot session setup (`TG_API_ID/HASH/SESSION_STRING` via `python -m userbot.session`)
7. Backup cron (`deploy/backup/README.md` already exists — reference it)

---

### `docs/admin-guide-ru.md` (doc, RU)

**No exact analog in the codebase** — new document. Structure should mirror `04-ACCEPTANCE.md`'s task-oriented drill steps but in Russian prose.

**Language:** Russian (D-06 decision). Technical English terms (Docker, Telegram, API) kept as-is.

**Sections to cover (D-05.3 / CONTEXT.md):**
1. Добавление источника — сайт (html_table / rss)
2. Добавление источника — Telegram-канал
3. Построитель правил алертов
4. Очередь `needs_review`
5. Мониторинг бюджета токенов

---

### `HANDOVER.md` (doc/index)

**Partial analog:** `05-UAT.md` front-matter + `.planning/phases/05-telegram-monitoring-ai/05-VERIFICATION.md` (summary table pattern)

**Index/table pattern from 05-UAT.md:**
```markdown
## Tests

| # | Name | Status |
|---|---|---|
| 1 | Live userbot ingestion drill | deferred |
| 2 | Real-data §6.1.3 gate | deferred |
```

**HANDOVER.md structure (D-05.4, §9 compliance):**
```markdown
# Handover Index — Polymer Intelligence

**Milestone:** Phase 1 (Client)
**Date:** 2026-06-XX

## §9 Deliverables

| Artifact | Location | Description |
|---|---|---|
| Source code (repo) | <repo URL> | Full codebase |
| Production compose | `deploy/docker-compose.yml` | Full container set |
| Deployment guide | `docs/deployment-guide.md` | First-run + secrets matrix |
| Backup/restore runbook | `docs/runbook-backup-restore.md` | ≤2 h restore procedure |
| Admin guide (RU) | `docs/admin-guide-ru.md` | Operator instructions |
| Extraction schema | `docs/extraction-schema.json` | Published signal schema |
| Acceptance sign-off | `.planning/phases/06-acceptance-handover/06-ACCEPTANCE.md` | TZ §6.1.1–6.1.6 |
```

---

### `backend/uv.lock` / pinned deps (config)

**Analog:** `backend/pyproject.toml` — existing toolchain already uses `uv`-compatible `pyproject.toml`

**Existing dev pin pattern** (lines 58–66 of `pyproject.toml`):
```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    # Pinned to known-good versions for a reproducible CI lint/type gate (UAT Gap 2 / SC#5).
    # Do not upgrade without verifying ruff check . and mypy gates stay green.
    "ruff==0.15.17",
    "mypy==2.1.0",
    "types-redis==4.6.0.20241004",
]
```

**Action:** Run `uv lock` in `backend/` to generate `uv.lock` alongside `pyproject.toml`. If `uv` is not the active tool, generate `requirements-pinned.txt` via `pip freeze > requirements-pinned.txt` after a clean install. The lock file must be committed so `docker build` is reproducible.

**Stale route-introspection tests:** Located in `backend/tests/test_init_data_auth.py` (FastAPI/Starlette drift). Fix pattern: update route path strings to match current router prefix, or use `client.app.url_path_for("endpoint_name")` instead of hardcoded strings.

---

## Shared Patterns

### Shell script header (apply to smoke + restore scripts)
**Source:** `deploy/backup/pg_backup.sh` lines 1–33
```bash
#!/usr/bin/env bash
# =============================================================================
# <name> — <description>
# Usage: VAR=value ./script.sh
# =============================================================================
set -euo pipefail
VAR="${VAR:-default}"
```

### Docker Compose healthcheck-gated depends_on
**Source:** `deploy/docker-compose.dev.yml` lines 86–93
**Apply to:** `deploy/docker-compose.yml` (all services that depend on postgres/redis)
```yaml
depends_on:
  postgres:
    condition: service_healthy
  redis:
    condition: service_healthy
```

### Test mock helper pattern (MagicMock user + auth headers)
**Source:** `backend/tests/test_source_wizard.py` lines 34–52 + `backend/tests/test_source_failure_alert.py` lines 48–67
**Apply to:** `backend/tests/test_telegram_channel_close.py`
```python
def _make_staff_user(role: str, user_id: int = 1) -> MagicMock: ...
def _auth_headers(user_id: int, role: str) -> dict[str, str]: ...
```

### Key-free / no-live-credentials test contract
**Source:** `backend/tests/parsing/test_telegram_accuracy.py` docstring (lines 1–20)
**Apply to:** `backend/tests/test_telegram_channel_close.py`, smoke script
```
Never make live API calls — use fixtures/mocks.
Safe under placeholder env vars (ANTHROPIC_API_KEY=sk-ant-ci-placeholder, TG_API_ID=0).
```

### Runbook step + verification pattern
**Source:** `docs/runbook-backup-restore.md` §3 (Steps 1–6) + §4 Post-restore Checklist
**Apply to:** `tests/restore/test_restore_local.sh`, `docs/deployment-guide.md`
```markdown
- [ ] `GET /api/v1/health` returns `200 OK` with `db: ok, redis: ok`
- [ ] `docker compose ps` shows `api`, `worker`, `beat` all **Up**
```

### Acceptance section structure
**Source:** `.planning/phases/04-dashboard-source-constructor/04-ACCEPTANCE.md` (full structure)
**Apply to:** `06-ACCEPTANCE.md`
Each TZ §6.1.x item gets: Full criterion → Automated CI Proxy (bash + coverage) → Deploy-Time Live Drill (numbered steps) → Pass criteria → Blocked-on (customer input).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `docs/admin-guide-ru.md` | doc (RU) | n/a | No Russian-language operator docs exist; nearest is English dev-spec (wrong audience/language) |

---

## Metadata

**Analog search scope:** `.planning/phases/`, `deploy/`, `backend/tests/`, `docs/`, `backend/pyproject.toml`
**Files scanned:** 14
**Pattern extraction date:** 2026-06-19
