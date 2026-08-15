"""
SQLAlchemy 2 database setup.

Provides:
- engine: the SQLAlchemy Engine built from DATABASE_URL
- SessionLocal: a sessionmaker factory
- Base: declarative base class that all ORM models inherit from
- get_db(): FastAPI dependency that yields a session and closes it on exit

Usage in a router:
    from app.core.db import get_db
    from sqlalchemy.orm import Session

    @router.get("/example")
    def example(db: Session = Depends(get_db)):
        ...

Schema changes only via Alembic migration + DB-doc edit in the same PR
(dev-spec §8, DEC-postgres-16).
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
# The pool is PER PROCESS, and there are many processes: uvicorn forks
# API_WORKERS of them, and each Celery worker process builds its own too. So the
# ceiling that matters is (processes x (pool_size + max_overflow)) against
# Postgres `max_connections`, not the numbers here read on their own.
#
# With the compose defaults — 2 API workers, 2 Celery workers, 5 + 10 each —
# that is 4 x 15 = 60, plus beat and the userbot, against the
# `max_connections=200` the compose postgres is started with. The previous
# values (10 + 20, hardcoded) came from a single-process deployment, where four
# uvicorn workers of those would alone have reached 120 against a default
# ceiling of 100, and the failure mode is `FATAL: sorry, too many clients` under
# load rather than anything gradual. Raising worker count without lowering the
# per-process pool is the mistake this comment exists to prevent.
#
# The counts default to 2 because CONNECTIONS ARE NOT THE BINDING CONSTRAINT —
# memory is. Each uvicorn worker and each Celery prefork child loads the whole
# app (20 domains of ORM models, anthropic, instructor, telethon, weasyprint), so
# process count multiplies resident memory almost linearly: measured at ~250 MB
# per api worker and ~180 MB per Celery child. A default of 4/4 was briefly
# shipped and exhausted a 2 vCPU / 4 GB host — 11 OOM kills, swap full, load 29.
# The default must be safe on the SMALLEST target, and 2 vCPU is that target.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # detect stale connections before using them
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    echo=False,           # set echo=True for SQL debug output during development
)


# ── Session factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ── Declarative base ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """All ORM models inherit from this base.

    Phase-1 models (signals, raw_items, requests, etc.) defined in app/models/
    will subclass Base.  The full DDL is in docs/polymer-intelligence-db-architecture.md.
    """


# ── FastAPI session dependency ────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a DB session and close it after the request.

    Example::

        @router.get("/health")
        def health(db: Session = Depends(get_db)):
            db.execute(text("SELECT 1"))
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
