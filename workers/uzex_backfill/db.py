"""PostgreSQL access for the backfill worker (raw psycopg 3, no ORM).

Owns three standalone tables (see ``schema.sql``) with no foreign keys to any
application table. All writes are idempotent:

* offers upsert on ``(source, external_id, content_hash)`` with
  ``ON CONFLICT DO NOTHING`` — the first fetched copy is kept, a genuine content
  change lands as a new revision row, and re-running a range inserts zero
  duplicates.
* discovered labels and the progress checkpoint upsert in place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Json

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def normalize_dsn(url: str) -> str:
    """Strip a SQLAlchemy driver suffix so psycopg accepts the DSN.

    ``postgresql+psycopg://...`` / ``postgresql+asyncpg://...`` → ``postgresql://...``
    """
    for prefix in ("postgresql+", "postgres+"):
        if url.startswith(prefix):
            scheme, _, rest = url.partition("://")
            base = scheme.split("+", 1)[0]
            return f"{base}://{rest}"
    return url


def connect(database_url: str) -> psycopg.Connection:
    """Open a connection with explicit (non-autocommit) transactions."""
    return psycopg.connect(normalize_dsn(database_url), autocommit=False)


def apply_schema(conn: psycopg.Connection) -> None:
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


# -- progress / concurrent-run guard --------------------------------------
def get_checkpoint(conn: psycopg.Connection, worker_name: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_id FROM uzex_backfill_progress WHERE worker_name = %s",
            (worker_name,),
        )
        row = cur.fetchone()
    return int(row[0]) if row else None


def seconds_since_checkpoint(conn: psycopg.Connection, worker_name: str) -> float | None:
    """Age of the checkpoint in seconds, or None if no checkpoint exists."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXTRACT(EPOCH FROM (now() - updated_at)) "
            "FROM uzex_backfill_progress WHERE worker_name = %s",
            (worker_name,),
        )
        row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def write_checkpoint(conn: psycopg.Connection, worker_name: str, last_id: int) -> None:
    """Advance the checkpoint high-water mark and refresh the heartbeat.

    ``last_id`` is kept monotonic via GREATEST so a small explicit-range or
    retry run cannot regress the main resume point; ``updated_at`` always
    refreshes so it doubles as the concurrent-run heartbeat. To truly reset the
    resume point, delete the progress row.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO uzex_backfill_progress (worker_name, last_id, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (worker_name)
            DO UPDATE SET
                last_id = GREATEST(uzex_backfill_progress.last_id, EXCLUDED.last_id),
                updated_at = now()
            """,
            (worker_name, last_id),
        )
    conn.commit()


# -- offers ----------------------------------------------------------------
def upsert_offer(
    conn: psycopg.Connection,
    *,
    source: str,
    external_id: int,
    http_status: int | None,
    final_url: str | None,
    status: str,
    fields: dict[str, Any] | None,
    raw_html: bytes | None,
    content_hash: str,
) -> bool:
    """Insert one offer row; returns True if a new row was written.

    ``ON CONFLICT (source, external_id, content_hash) DO NOTHING`` means an
    identical re-fetch is a no-op, while changed content (new hash) is a new
    revision. The first copy is never mutated.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO uzex_raw_offers
                (source, external_id, http_status, final_url, status,
                 fields, raw_html, content_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source, external_id, content_hash) DO NOTHING
            """,
            (
                source,
                external_id,
                http_status,
                final_url,
                status,
                Json(fields) if fields is not None else None,
                raw_html,
                content_hash,
            ),
        )
        inserted = cur.rowcount == 1
    conn.commit()
    return inserted


# -- discovered labels -----------------------------------------------------
def load_known_labels(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT label FROM uzex_discovered_labels")
        return {row[0] for row in cur.fetchall()}


def insert_labels(conn: psycopg.Connection, labels: dict[str, int]) -> None:
    """Record first-seen ids for previously-unseen labels (idempotent)."""
    if not labels:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO uzex_discovered_labels (label, first_seen_id)
            VALUES (%s, %s)
            ON CONFLICT (label) DO NOTHING
            """,
            list(labels.items()),
        )
    conn.commit()


# -- retry-failed ----------------------------------------------------------
def failed_external_ids(
    conn: psycopg.Connection, source: str, limit: int | None = None
) -> list[int]:
    """Ids whose latest state is fetch_failed and which have no ok revision yet."""
    sql = """
        SELECT DISTINCT f.external_id
        FROM uzex_raw_offers f
        WHERE f.source = %s
          AND f.status = 'fetch_failed'
          AND NOT EXISTS (
              SELECT 1 FROM uzex_raw_offers o
              WHERE o.source = f.source
                AND o.external_id = f.external_id
                AND o.status = 'ok'
          )
        ORDER BY f.external_id
    """
    params: tuple[Any, ...] = (source,)
    if limit is not None:
        sql += " LIMIT %s"
        params = (source, limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [int(row[0]) for row in cur.fetchall()]


# -- status ----------------------------------------------------------------
def status_counts(conn: psycopg.Connection, source: str) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, count(*) FROM uzex_raw_offers WHERE source = %s GROUP BY status",
            (source,),
        )
        return {row[0]: int(row[1]) for row in cur.fetchall()}


def offer_id_bounds(conn: psycopg.Connection, source: str) -> tuple[int | None, int | None]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT min(external_id), max(external_id) FROM uzex_raw_offers WHERE source = %s",
            (source,),
        )
        row = cur.fetchone()
    if not row:
        return (None, None)
    lo = int(row[0]) if row[0] is not None else None
    hi = int(row[1]) if row[1] is not None else None
    return (lo, hi)


def label_count(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM uzex_discovered_labels")
        row = cur.fetchone()
    return int(row[0]) if row else 0
