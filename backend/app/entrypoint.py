"""
API container startup entrypoint — advisory-locked migration runner.

This module implements the dev-spec §7 contract: when the API container starts,
it acquires a PostgreSQL session-level advisory lock before running
`alembic upgrade head`, ensuring that two concurrent API containers cannot
race on DDL migration.

The advisory lock key is a stable large integer — any fixed value works; we use
a hash of the project name to avoid collisions with other apps on the same DB.

Advisory lock protocol (T-02-01 mitigation):
    1. Open a raw connection (not a pool connection)
    2. Call pg_advisory_lock(<key>) — blocks until acquired
    3. Run alembic upgrade head
    4. Call pg_advisory_unlock(<key>) — release the lock
    5. Close the connection

Usage:
    - Called from the api container entrypoint/startup (e.g., from main.py lifespan)
    - Can also be invoked as a CLI: python -m app.entrypoint
    - Tests can call run_migrations() directly

Acceptance: grep -v '^#' backend/app/entrypoint.py | grep -c advisory_lock >= 1
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy import text

from alembic import command as alembic_command

logger = logging.getLogger(__name__)

# Stable advisory lock key — chosen to avoid collision with other pg clients.
# Derived from hash of project name, reduced to postgres BIGINT range.
_ADVISORY_LOCK_KEY: int = 0x506F6C796D65720A  # "Polymer\n" as hex, fits int64

# Path to alembic directory (relative to this file's location)
_ALEMBIC_DIR = Path(__file__).parent.parent / "alembic"
_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def _get_alembic_cfg(database_url: str) -> Config:
    """Build an Alembic Config pointing at the live database."""
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    return cfg


def run_migrations() -> str:
    """Run alembic upgrade head under a PostgreSQL session-level advisory lock.

    Returns the current revision string after successful migration.

    Implements T-02-01 mitigation: concurrent API containers block here
    instead of racing on DDL.
    """
    from sqlalchemy import create_engine  # noqa: PLC0415 — avoid circular at module level

    try:
        from app.core.config import settings  # noqa: PLC0415

        database_url = settings.DATABASE_URL
    except Exception:
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            raise RuntimeError("DATABASE_URL is not set — cannot run migrations") from None

    logger.info("entrypoint.migration_start", extra={"url": database_url.split("@")[-1]})

    # Use a dedicated engine with NullPool so we control the connection lifecycle
    from sqlalchemy.pool import NullPool  # noqa: PLC0415

    engine = create_engine(database_url, poolclass=NullPool)

    with engine.connect() as conn:
        # ── Acquire advisory lock ─────────────────────────────────────────────
        # pg_advisory_lock blocks until the lock is acquired.
        # advisory_lock is a session-level lock (auto-released when session ends).
        conn.execute(text(f"SELECT pg_advisory_lock({_ADVISORY_LOCK_KEY})"))
        logger.info("entrypoint.advisory_lock_acquired", extra={"key": _ADVISORY_LOCK_KEY})

        try:
            # ── Run migrations ────────────────────────────────────────────────
            cfg = _get_alembic_cfg(database_url)
            alembic_command.upgrade(cfg, "head")
            logger.info("entrypoint.migration_complete")

            # ── Read current revision ─────────────────────────────────────────
            result = conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            row = result.fetchone()
            revision = row[0] if row else "none"

        finally:
            # ── Release advisory lock ────────────────────────────────────────
            # Always release even if migration failed (connection close also releases
            # session-level locks, but explicit release is cleaner).
            conn.execute(text(f"SELECT pg_advisory_unlock({_ADVISORY_LOCK_KEY})"))
            logger.info("entrypoint.advisory_lock_released", extra={"key": _ADVISORY_LOCK_KEY})

    engine.dispose()
    return revision


def get_schema_version(database_url: str | None = None) -> str | None:
    """Query the current alembic_version from the database.

    Returns the revision string, or None if the alembic_version table does not
    exist yet (unmigrated database).

    Used by /health endpoint to report schema readiness (REQ-nfr-observability).
    """
    from sqlalchemy import create_engine, inspect  # noqa: PLC0415
    from sqlalchemy.pool import NullPool  # noqa: PLC0415

    if database_url is None:
        try:
            from app.core.config import settings  # noqa: PLC0415

            database_url = settings.DATABASE_URL
        except Exception:
            database_url = os.environ.get("DATABASE_URL", "")

    if not database_url:
        return None

    try:
        engine = create_engine(database_url, poolclass=NullPool)
        with engine.connect() as conn:
            # Check table exists before querying
            inspector = inspect(engine)
            if "alembic_version" not in inspector.get_table_names():
                return None
            result = conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            row = result.fetchone()
            return row[0] if row else None
    except Exception as exc:
        logger.warning("entrypoint.get_schema_version_failed", exc_info=exc)
        return None
    finally:
        import contextlib  # noqa: PLC0415
        with contextlib.suppress(Exception):
            engine.dispose()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    revision = run_migrations()
    print(f"Migrations applied. Current revision: {revision}")
    sys.exit(0)
