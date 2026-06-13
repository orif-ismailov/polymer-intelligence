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

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    # Pool settings tuned for a single-VPS FastAPI deployment (DEC-deploy-single-vps).
    pool_pre_ping=True,   # detect stale connections before using them
    pool_size=10,
    max_overflow=20,
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
