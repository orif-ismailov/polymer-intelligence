#!/usr/bin/env bash
# =============================================================================
# test_smoke_full_stack.sh — Full-stack production-compose smoke (D-02)
#
# Stands up the PRODUCTION stack (deploy/docker-compose.yml) against
# SYNTHETIC / PLACEHOLDER data only — NO production data and NO real
# credentials are ever used or committed. The placeholder .env this script
# generates is created at runtime, used for the run, and removed on exit.
#
# Sequence (each step gates the next; any failure tears the stack down):
#   1. Generate a placeholder ./.env (functional fake secrets; gitignored) and
#      `docker compose up -d` the full production stack.
#   2. Poll /api/v1/health (via `compose exec api curl` — see the nginx note
#      below) until it returns "status":"ok" (the api command runs migrate+seed
#      before uvicorn, so this also proves the schema is applied).
#   3. Submit a SYNTHETIC purchase request through the app's ORM and assert it
#      becomes queryable in v_live_feed (the request leg of the feed view).
#   4. FORCE a deliberately-failing fake source: run run_source_fetch_isolated
#      against a fake adapter 3x (fetch() raises) alongside a healthy sibling,
#      then assert (a) the sibling recorded success (per-source isolation) and
#      (b) exactly ONE alerts row with kind='source_failure' for the fake source
#      (the 3-strike deduped alert).
#   5. `docker compose down -v` teardown (bash trap — runs even on mid-run
#      failure, so no orphaned containers/volumes/synthetic state remain).
#
# Prints `[smoke] PASSED` ONLY if every step succeeded.
#
# nginx note (deviation): the production nginx is TLS-only on 443 with
# Let's Encrypt cert paths for a real domain (example.com placeholder); a
# key-free local smoke cannot terminate TLS through it. We therefore probe
# /api/v1/health by exec'ing curl INSIDE the api container — the exact path
# nginx proxies to internally (http://api:8000/api/v1/health) — which proves
# the real api + migrate+seed without requiring certs.
#
# Usage:
#   make smoke
#   bash tests/smoke/test_smoke_full_stack.sh
#
# Requires: docker + docker compose v2. No host ports are published by the
# stack except nginx 80/443; this smoke reaches the api over the compose
# network via `compose exec`, so it needs no published api port.
# =============================================================================
set -euo pipefail

# ── Resolve repo root (this script lives at <root>/tests/smoke/) ──────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

COMPOSE_FILE="deploy/docker-compose.yml"
# The prod compose reads `env_file: ../.env` (relative to deploy/ → repo-root
# ./.env) and interpolates ${VAR} from --env-file. A single repo-root .env
# serves both. It is gitignored (.env) so it is NEVER committed.
ENV_FILE="${REPO_ROOT}/.env"
COMPOSE="docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} -p pismoke"

HEALTH_TIMEOUT="${SMOKE_HEALTH_TIMEOUT:-300}"   # seconds to wait for /health ok
ENV_PREEXISTING="false"

echo "[smoke] ============================================================"
echo "[smoke] Polymer Intelligence — full-stack smoke (D-02)"
echo "[smoke] SYNTHETIC DATA + PLACEHOLDER ENV ONLY — no real credentials"
echo "[smoke] ============================================================"

# ── Teardown trap: always down -v + remove the placeholder env we created ─────
cleanup() {
  local rc=$?
  echo "[smoke] --- teardown: docker compose down -v ---"
  ${COMPOSE} down -v --remove-orphans >/dev/null 2>&1 || true
  if [ "${ENV_PREEXISTING}" = "false" ] && [ -f "${ENV_FILE}" ]; then
    rm -f "${ENV_FILE}"
    echo "[smoke] removed generated placeholder ${ENV_FILE}"
  fi
  if [ "${rc}" -ne 0 ]; then
    echo "[smoke] FAILED (exit ${rc})"
  fi
  return "${rc}"
}
trap cleanup EXIT

# ── Step 1: placeholder .env + compose up ─────────────────────────────────────
if [ -f "${ENV_FILE}" ]; then
  # Never clobber a real operator .env; reuse it but do NOT delete it on exit.
  ENV_PREEXISTING="true"
  echo "[smoke] reusing existing ${ENV_FILE} (will NOT be deleted on exit)"
else
  echo "[smoke] writing placeholder ${ENV_FILE} (fake secrets; gitignored)"
  cat > "${ENV_FILE}" <<'ENVEOF'
# AUTO-GENERATED placeholder env for the full-stack smoke — NO REAL SECRETS.
# Removed automatically on smoke exit. Values are fake-but-functional.
POSTGRES_PASSWORD=smoke_pg_password
ANTHROPIC_API_KEY=sk-ant-smoke-placeholder
BOT_TOKEN=123456789:SMOKEsmokeSMOKEsmokeSMOKEsmoke
WEBHOOK_SECRET=smoke_webhook_secret_at_least_32_chars
TG_API_ID=12345678
TG_API_HASH=smokeapihashsmokeapihashsmoke12
TG_SESSION_STRING=
JWT_SECRET=smoke_jwt_secret_at_least_thirty_two_chars_long
S3_ACCESS_KEY=smoke_s3_access_key
S3_SECRET_KEY=smoke_s3_secret_key
S3_BUCKET=polymer-files
ENVEOF
fi

echo "[smoke] step 1: docker compose up -d (full production stack)"
# Bring up everything EXCEPT nginx (TLS-only, needs real certs) and the
# dashboard (Next.js build is heavy and not exercised by this backend smoke).
# api/worker/beat/userbot + postgres/redis/minio cover the request→feed and
# source-isolation paths this smoke asserts.
${COMPOSE} up -d --build postgres redis minio api worker beat

# ── Step 2: health-gated wait ─────────────────────────────────────────────────
echo "[smoke] step 2: waiting for /api/v1/health == ok (timeout ${HEALTH_TIMEOUT}s)"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
healthy="false"
while [ "$(date +%s)" -lt "${deadline}" ]; do
  if ${COMPOSE} exec -T api curl -sf http://localhost:8000/api/v1/health 2>/dev/null \
       | grep -q '"status":"ok"'; then
    healthy="true"
    break
  fi
  sleep 5
done
if [ "${healthy}" != "true" ]; then
  echo "[smoke] ERROR: /api/v1/health never returned status=ok within ${HEALTH_TIMEOUT}s"
  ${COMPOSE} exec -T api curl -s http://localhost:8000/api/v1/health 2>/dev/null || true
  echo
  ${COMPOSE} logs --tail=40 api || true
  exit 1
fi
echo "[smoke] /api/v1/health: ok"

# ── Step 3: synthetic request → v_live_feed ───────────────────────────────────
echo "[smoke] step 3: submit a synthetic request and assert it lands in v_live_feed"
${COMPOSE} exec -T api python - <<'PYEOF'
import sys
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.db import engine

marker = f"SMOKE-{uuid.uuid4().hex[:10]}"

with Session(engine) as session:
    # seed_reference populates products; FK target for requests.product_id.
    product_id = session.execute(
        sa.text("SELECT id FROM products ORDER BY id LIMIT 1")
    ).scalar()
    if product_id is None:
        print("[smoke] FAIL: no seeded products (seed_reference did not run)", file=sys.stderr)
        sys.exit(1)

    # Synthetic client (no real PII).
    client_id = session.execute(
        sa.text(
            """
            INSERT INTO clients (company_name, contact_name, language)
            VALUES (:co, :ct, 'ru')
            RETURNING id
            """
        ),
        {"co": f"Smoke Co {marker}", "ct": "Smoke Tester"},
    ).scalar()

    # Synthetic purchase request — the `request` leg of v_live_feed.
    request_id = session.execute(
        sa.text(
            """
            INSERT INTO requests
              (number, client_id, product_id, volume, currency, urgency, status)
            VALUES
              (:num, :cid, :pid, 50, 'USD', 'medium', 'new')
            RETURNING id
            """
        ),
        {"num": marker, "cid": client_id, "pid": product_id},
    ).scalar()
    session.commit()

    # Assert the request is queryable through the feed view.
    found = session.execute(
        sa.text(
            "SELECT COUNT(*) FROM v_live_feed WHERE origin = 'request' AND id = :rid"
        ),
        {"rid": request_id},
    ).scalar()

    if found != 1:
        print(
            f"[smoke] FAIL: synthetic request {request_id} not found in v_live_feed "
            f"(count={found})",
            file=sys.stderr,
        )
        sys.exit(1)

print(f"[smoke] synthetic request {marker} (id={request_id}) visible in v_live_feed")
PYEOF
echo "[smoke] request→feed: ok"

# ── Step 4: forced fake-source failure → isolation + one source_failure alert ─
echo "[smoke] step 4: force a fake-source failure 3x; assert isolation + 1 alert"
${COMPOSE} exec -T api python - <<'PYEOF'
import sys
from unittest.mock import MagicMock, patch

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.db import engine
from app.models.sources import Source
from app.tasks.ingest import run_source_fetch_isolated


def _make_source(session, name):
    return session.execute(
        sa.text(
            """
            INSERT INTO sources (kind, adapter, name, is_enabled, config, created_at)
            VALUES ('exchange', 'uzex_offers', :name, true, '{}', NOW())
            RETURNING id
            """
        ),
        {"name": name},
    ).scalar()


with Session(engine) as session:
    import uuid

    tag = uuid.uuid4().hex[:8]
    sibling_id = _make_source(session, f"smoke_sibling_{tag}")
    fake_id = _make_source(session, f"smoke_fake_{tag}")
    session.commit()

    try:
        sibling = session.get(Source, sibling_id)
        fake = session.get(Source, fake_id)
        adapter = MagicMock()

        # Healthy sibling: fetch returns no drafts, success recorded.
        with patch("app.tasks.ingest._run_fetch_for_source", return_value=[]), \
             patch("app.tasks.ingest.save_raw_items", return_value=(0, [])):
            run_source_fetch_isolated(session, sibling, adapter)
            session.commit()

        # Fake source: fetch() raises 3x. Isolation means this never re-raises;
        # the 3rd strike fires exactly one deduped source_failure alert.
        for _ in range(3):
            with patch(
                "app.tasks.ingest._run_fetch_for_source",
                side_effect=Exception("smoke: simulated source failure"),
            ):
                run_source_fetch_isolated(session, fake, adapter)
                session.commit()

        # (a) Isolation: sibling still recorded a successful fetch.
        sib_row = session.execute(
            sa.text(
                "SELECT last_success_at, consecutive_failures FROM sources WHERE id = :id"
            ),
            {"id": sibling_id},
        ).fetchone()
        if sib_row is None or sib_row[0] is None or sib_row[1] != 0:
            print(
                f"[smoke] FAIL: sibling source not isolated/healthy: {sib_row}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Fake source took the failures.
        fake_failures = session.execute(
            sa.text("SELECT consecutive_failures FROM sources WHERE id = :id"),
            {"id": fake_id},
        ).scalar()
        if fake_failures < 3:
            print(
                f"[smoke] FAIL: fake source consecutive_failures={fake_failures} (<3)",
                file=sys.stderr,
            )
            sys.exit(1)

        # (b) Exactly ONE source_failure alert for the fake source (deduped).
        alert_count = session.execute(
            sa.text(
                """
                SELECT COUNT(*) FROM alerts
                WHERE kind = 'source_failure'
                  AND dedupe_key LIKE :pattern
                """
            ),
            {"pattern": f"source_failure:{fake_id}:%"},
        ).scalar()
        if alert_count != 1:
            print(
                f"[smoke] FAIL: expected exactly 1 source_failure alert, got {alert_count}",
                file=sys.stderr,
            )
            sys.exit(1)

        print(
            f"[smoke] isolation ok: sibling healthy, fake failed {fake_failures}x, "
            f"exactly 1 source_failure alert"
        )
    finally:
        # Clean the synthetic rows (stack is also torn down -v on exit).
        for sid in (sibling_id, fake_id):
            session.execute(
                sa.text("DELETE FROM alerts WHERE dedupe_key LIKE :p"),
                {"p": f"source_failure:{sid}:%"},
            )
            session.execute(sa.text("DELETE FROM sources WHERE id = :id"), {"id": sid})
        session.commit()
PYEOF
echo "[smoke] source isolation + single source_failure alert: ok"

# ── Done ──────────────────────────────────────────────────────────────────────
echo "[smoke] PASSED"
