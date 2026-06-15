"""
Alembic environment configuration.

Reads DATABASE_URL from app.core.config.settings and connects
target_metadata to Base.metadata (all models imported via app.models).

Schema changes only via alembic migration + DB-doc edit in same PR (dev-spec §8).
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Path setup ───────────────────────────────────────────────────────────────
# Ensure the backend package is importable when alembic is run from the
# backend/ directory (which is the cwd set by alembic.ini).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Import models so Base.metadata knows all tables ──────────────────────────
# This import triggers all model module imports via __init__.py
import app.models  # noqa: F401, E402
from app.core.db import Base  # noqa: E402

# ── Alembic config object ─────────────────────────────────────────────────────
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Target metadata ───────────────────────────────────────────────────────────
# Base.metadata includes all 20 tables imported above.
target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from app settings, falling back to alembic.ini value."""
    # Try to get from app settings first (used when running via entrypoint.py)
    try:
        from app.core.config import settings  # noqa: PLC0415

        return settings.DATABASE_URL
    except Exception:
        # Fall back to alembic.ini when running standalone (e.g., during local dev)
        url = config.get_main_option("sqlalchemy.url")
        if url is None:
            raise RuntimeError(
                "DATABASE_URL not set and alembic.ini has no sqlalchemy.url"
            ) from None
        return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine, though an Engine
    is acceptable here as well. By skipping the Engine creation, we don't even
    need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario, an engine is created and associated with the context.
    """
    # Override sqlalchemy.url from settings (not from alembic.ini)
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
