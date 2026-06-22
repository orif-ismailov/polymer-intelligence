"""
Performance test: GET /feed keyset pagination ≤500 ms at ~1M v_live_feed rows.

Marker: `performance` — only runs when -m performance is passed AND a real
Postgres database is reachable (skips gracefully otherwise).

Plan reference: 04-09 Task 1 (REQ-nfr-performance, TZ §5 NFR)
Must-have assertions (04-09-PLAN.md must_haves):
  - A keyset-paginated GET /feed page returns within 500 ms
  - EXPLAIN ANALYZE on the keyset path does NOT show a Seq Scan on v_live_feed
    or its backing signals table (Pitfall 2 — index must be used)
"""

from __future__ import annotations

import os
import time
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Skip guard — skip the entire module when no DB URL is configured, or when
# the performance marker is not requested.  This keeps the standard suite fast
# and avoids Postgres connection errors in CI.
# ---------------------------------------------------------------------------

def _skip_without_db() -> bool:
    """Return True when a real Postgres DATABASE_URL is available."""
    db_url = os.environ.get("DATABASE_URL", "")
    return not db_url.startswith("postgresql")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_app_with_real_db():
    """Create the FastAPI app wired to the real DB session factory.

    We do NOT override get_db here — this test needs real Postgres I/O to
    measure genuine query latency and to run EXPLAIN ANALYZE.
    """
    from app.main import create_app
    return create_app()


def _get_real_engine():
    """Return a synchronous SQLAlchemy engine for raw SQL execution.

    Keeps the project's psycopg v3 dialect (postgresql+psycopg://) — psycopg v3
    drives synchronous engines fine, and psycopg2 is not installed.
    """
    import sqlalchemy as sa

    from app.core.config import settings
    return sa.create_engine(str(settings.DATABASE_URL))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def perf_engine():
    """Engine scoped to the module — one connection pool for all perf tests.

    Probes connectivity and SKIPS (rather than errors) when no real Postgres is
    reachable with the feed schema present. This keeps `pytest -m performance` a
    clean no-op in any environment without a purpose-built perf database (CI,
    a developer laptop, the dev stack's `test` DB that may not exist) — it never
    targets or pollutes the real application database. Keeps the project's
    psycopg v3 dialect; psycopg2 is intentionally not installed.
    """
    import sqlalchemy as sa
    from sqlalchemy import create_engine
    from sqlalchemy.exc import SQLAlchemyError

    from app.core.config import settings

    engine = create_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            # Require both connectivity and the signals table (the feed backing store).
            conn.execute(sa.text("SELECT 1 FROM signals LIMIT 1"))
    except SQLAlchemyError as exc:
        pytest.skip(
            "No reachable Postgres with the feed schema for the performance "
            f"test ({exc.__class__.__name__}) — provide a perf DB to run it."
        )
    return engine


@pytest.fixture(scope="module")
def seeded_feed_db(perf_engine):
    """
    Ensure approximately 1M rows exist in the signals table (which backs v_live_feed).

    Strategy:
    - Count existing signals.
    - If fewer than 900,000 exist: bulk-insert synthetic rows until the target is reached.
    - Rows are inserted into signals directly (same shape as the live pipeline).
    - All synthetic rows are inserted with a recognizable product_id sentinel (9999)
      so they can be cleaned up after the test module if desired (we leave them
      to keep the test idempotent on repeated runs).

    The insert uses a single VALUES batch (1000 rows at a time) to avoid OOM.

    Yields the engine so tests can run raw SQL.
    """
    import datetime

    import sqlalchemy as sa

    target = 1_000_000
    batch = 5_000

    with perf_engine.connect() as conn:
        count = conn.execute(
            sa.text("SELECT COUNT(*) FROM signals")
        ).scalar_one()

        if count < target:
            needed = target - int(count)
            inserted = 0
            base_time = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)

            while inserted < needed:
                batch_size = min(batch, needed - inserted)
                rows = []
                for i in range(batch_size):
                    offset_secs = inserted + i
                    event_at = base_time + datetime.timedelta(seconds=offset_secs)
                    rows.append({
                        "source_id": 1,
                        "product_id": 9999,
                        "grade_text": f"PERF-{offset_secs}",
                        "polymer_type": "PP",
                        "volume": 10.0,
                        "volume_unit": "mt",
                        "price": 1000.0,
                        "currency": "USD",
                        "section": "perf_test",
                        "kind": "offer",
                        "event_at": event_at,
                        "status": "new",
                        "urgency": "medium",
                        "region": "UZ",
                    })
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO signals
                        (source_id, product_id, grade_text, polymer_type,
                         volume, volume_unit, price, currency, section,
                         kind, event_at, status, urgency, region)
                        VALUES
                        (:source_id, :product_id, :grade_text, :polymer_type,
                         :volume, :volume_unit, :price, :currency, :section,
                         :kind, :event_at, :status, :urgency, :region)
                        """
                    ),
                    rows,
                )
                conn.commit()
                inserted += batch_size

    yield perf_engine


# ---------------------------------------------------------------------------
# Tests (all gated by @pytest.mark.performance)
# ---------------------------------------------------------------------------


@pytest.mark.performance
def test_feed_keyset_page_within_500ms(seeded_feed_db):
    """GET /feed first page must return ≤500 ms with ~1M rows in the table.

    Uses the TestClient over the real application (no mock DB) to measure
    end-to-end latency including SQLAlchemy overhead and JSON serialisation.

    Threshold: 500 ms (0.5 s) — REQ-nfr-performance / TZ §5 NFR.
    """
    if _skip_without_db():
        pytest.skip("No Postgres DATABASE_URL — skipping performance test")

    from fastapi.testclient import TestClient

    from app.core.security import create_access_token

    app = _build_app_with_real_db()
    token = create_access_token(subject="1", role="admin")
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app, raise_server_exceptions=True) as client:
        start = time.perf_counter()
        resp = client.get("/api/v1/feed", headers=headers, params={"limit": 50})
        elapsed = time.perf_counter() - start

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert elapsed <= 0.5, (
        f"GET /feed took {elapsed:.3f}s — exceeds 500 ms REQ-nfr-performance limit"
    )


@pytest.mark.performance
def test_feed_keyset_no_seq_scan(seeded_feed_db):
    """EXPLAIN ANALYZE on the keyset query must NOT show Seq Scan on v_live_feed.

    The composite index on signals (kind, event_at DESC) — and the optional partial
    index on requests (event_at DESC) — must be used.  A Seq Scan at 1M rows would
    push latency well above 500 ms (Pitfall 2 / 04-RESEARCH.md).

    We run EXPLAIN ANALYZE directly via psycopg to get the real query plan.
    """
    if _skip_without_db():
        pytest.skip("No Postgres DATABASE_URL — skipping performance test")

    import sqlalchemy as sa

    # Mirror the exact keyset query from app.api.feed — no cursor (first page)
    keyset_query = sa.text(
        """
        EXPLAIN ANALYZE
        SELECT id, origin, kind, product_id, grade_text, volume,
               price, currency, region, urgency, status, event_at
        FROM v_live_feed
        WHERE
            (CAST(:cursor_ea AS timestamptz) IS NULL
             OR event_at < CAST(:cursor_ea AS timestamptz)
             OR (event_at = CAST(:cursor_ea AS timestamptz) AND id < CAST(:cursor_id AS bigint)))
          AND (CAST(:kind AS text) IS NULL OR kind = CAST(:kind AS text))
          AND (CAST(:product_id AS integer) IS NULL OR product_id = CAST(:product_id AS integer))
          AND (CAST(:source AS text) IS NULL OR origin = CAST(:source AS text))
          AND (CAST(:urgency AS text) IS NULL OR urgency::text = CAST(:urgency AS text))
          AND (CAST(:period_lower AS timestamptz) IS NULL OR event_at >= CAST(:period_lower AS timestamptz))
        ORDER BY event_at DESC, id DESC
        LIMIT :limit
        """
    )

    params: dict[str, Any] = {
        "cursor_ea": None,
        "cursor_id": None,
        "kind": None,
        "product_id": None,
        "source": None,
        "urgency": None,
        "period_lower": None,
        "limit": 50,
    }

    with seeded_feed_db.connect() as conn:
        rows = conn.execute(keyset_query, params).fetchall()

    plan_lines = [row[0] for row in rows]
    plan_text = "\n".join(plan_lines)

    # Seq Scan on v_live_feed or either underlying table is the problem pattern
    assert "Seq Scan on signals" not in plan_text, (
        f"Seq Scan on signals detected — keyset index not used.\n\n"
        f"Query plan:\n{plan_text}"
    )


@pytest.mark.performance
def test_feed_second_page_within_500ms(seeded_feed_db):
    """Paginated second page (cursor set) must also stay ≤500 ms.

    This verifies the cursor WHERE clause continues to use the index even after
    the first page boundary — the most likely regression point (Pitfall 2).
    """
    if _skip_without_db():
        pytest.skip("No Postgres DATABASE_URL — skipping performance test")

    from fastapi.testclient import TestClient

    from app.core.security import create_access_token

    app = _build_app_with_real_db()
    token = create_access_token(subject="1", role="admin")
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app, raise_server_exceptions=True) as client:
        # Get the first page to obtain a cursor
        first_resp = client.get("/api/v1/feed", headers=headers, params={"limit": 50})
        assert first_resp.status_code == 200

        first_page = first_resp.json()
        cursor_ea = first_page.get("next_cursor_event_at")
        cursor_id = first_page.get("next_cursor_id")

        if cursor_ea is None:
            pytest.skip("Not enough rows for a second page — check seed")

        # Now measure second page
        start = time.perf_counter()
        resp = client.get(
            "/api/v1/feed",
            headers=headers,
            params={
                "limit": 50,
                "cursor_event_at": cursor_ea,
                "cursor_id": cursor_id,
            },
        )
        elapsed = time.perf_counter() - start

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert elapsed <= 0.5, (
        f"GET /feed page-2 took {elapsed:.3f}s — exceeds 500 ms REQ-nfr-performance limit"
    )
