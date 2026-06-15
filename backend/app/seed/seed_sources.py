"""
Sources seed script.

Populates the sources table with the UZEX + CBU adapter rows (adapter + config
with selectors/urls).  Idempotent: uses INSERT ... ON CONFLICT (adapter, name)
DO NOTHING so re-running creates no duplicates.

INVARIANT (DEC-test-before-enable, T-02-24):
  All seeded rows have ``is_enabled = false`` and ``last_test_ok_at = NULL``.
  A source can only be enabled after it passes an admin-triggered Test
  (enforced via service-layer validation).

Seed scope:
- uzex_offers   — UZEX open auction offers pages (Sum + Currency + Import)
- uzex_contracts — UZEX quotation/contract listing pages (Sum + Currency)
- uzex_deals    — UZEX concluded-deal registry (/Trade/List)
- cbu_rates     — CBU official FX rate API endpoint

Usage:
    python -m app.seed.seed_sources

Idempotency contract:
    Running this function twice on the same migrated database:
    - Inserts the expected rows on first run
    - Inserts 0 additional rows on second run
    - Never raises an error on second run
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Path to seed data file
_DATA_DIR = Path(__file__).parent / "data"
_SOURCES_FILE = _DATA_DIR / "sources_seed.json"


def _load_json(path: Path) -> Any:
    """Load and return JSON from a file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def seed_sources(session: Session) -> int:
    """Upsert UZEX + CBU source rows idempotently.

    Uses INSERT ... ON CONFLICT (adapter, name) DO NOTHING so re-runs are safe.

    All inserted rows have:
        is_enabled = false
        last_test_ok_at = NULL
    This enforces the source-enable invariant: a source can only be enabled
    after a passing admin Test (DEC-test-before-enable, T-02-24).

    Args:
        session: Active SQLAlchemy session.  Caller must commit.

    Returns:
        Number of rows inserted (0 on idempotent re-run).
    """
    sources = _load_json(_SOURCES_FILE)
    inserted = 0

    for src in sources:
        # Serialize config dict to JSON string for JSONB binding
        config_json = json.dumps(src.get("config") or {})

        # Idempotent insert: skip if a row with the same (adapter, name) exists.
        # The sources table has no unique constraint on (adapter, name) in the
        # locked DDL; we use INSERT ... WHERE NOT EXISTS to enforce idempotency
        # without requiring a schema change (ON CONFLICT needs a unique index).
        cursor_result = session.execute(
            text(
                """
                INSERT INTO sources (
                    kind, adapter, name, url, config, country,
                    is_enabled, last_test_ok_at
                )
                SELECT
                    :kind, :adapter, :name, :url,
                    CAST(:config AS JSONB),
                    :country,
                    false,
                    NULL
                WHERE NOT EXISTS (
                    SELECT 1 FROM sources
                    WHERE adapter = :adapter AND name = :name
                )
                """
            ),
            {
                "kind": src["kind"],
                "adapter": src["adapter"],
                "name": src["name"],
                "url": src.get("url"),
                "config": config_json,
                "country": src.get("country"),
            },
        )
        # Cast to CursorResult to access .rowcount (SQLAlchemy ORM text() returns
        # Result[Any] which doesn't expose rowcount in stubs; CursorResult does).
        inserted += int(cast(CursorResult[Any], cursor_result).rowcount)

    session.flush()
    logger.info(
        "seed.sources_seeded",
        extra={"inserted": inserted, "total": len(sources)},
    )
    return inserted


def seed_all_sources(session: Session) -> dict[str, int]:
    """Run the sources seed and commit.

    Returns counts of rows inserted per entity type.
    """
    sources_inserted = seed_sources(session)
    session.commit()
    return {"sources": sources_inserted}


if __name__ == "__main__":
    import logging as _logging
    import os
    import sys

    _logging.basicConfig(level=_logging.INFO)

    from sqlalchemy import create_engine  # noqa: PLC0415

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        try:
            from app.core.config import settings  # noqa: PLC0415

            db_url = settings.DATABASE_URL
        except Exception:
            print("ERROR: DATABASE_URL not set", file=sys.stderr)
            sys.exit(1)

    engine = create_engine(db_url)
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        counts = seed_all_sources(session)

    print(f"Seed complete: {counts}")
    sys.exit(0)
