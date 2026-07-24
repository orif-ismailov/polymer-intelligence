"""Shared helpers for the W4 verification real-Postgres tests.

Guarded like the other real-DB suites: only run against a localhost `test_polymer`
DB (skip in CI / default suite). Not a pytest module (leading underscore).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).parent.parent

_DB_URL = os.environ.get("DATABASE_URL", "")
IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

requires_real_db = pytest.mark.skipif(
    not IS_REAL_DB,
    reason=(
        "Verification DB tests require a live localhost test PostgreSQL. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)

# Delete order: children before parents (FK-safe).
_TABLES = [
    "domain_events",
    "audit_log",
    "verification_checks",
    "company_bank_accounts",
    "verification_documents",
    "verification_cases",
    "company_business_roles",
    "company_members",
    "companies",
    "sms_send_log",
    "user_accounts",
]


def make_engine() -> sa.Engine:
    return sa.create_engine(_DB_URL, pool_pre_ping=True)


def migrate_head() -> None:
    """Point settings + alembic at test_polymer and upgrade to head (idempotent)."""
    from alembic.config import Config

    from alembic import command as alembic_command
    from app.core.config import settings

    object.__setattr__(settings, "DATABASE_URL", _DB_URL)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _DB_URL)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    alembic_command.upgrade(cfg, "head")


def clean(engine: sa.Engine) -> None:
    with engine.begin() as conn:
        for table in _TABLES:
            conn.execute(sa.text(f"DELETE FROM {table}"))  # noqa: S608 — fixed table list


def session_factory(engine: sa.Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def make_account(db: Session, phone: str):  # noqa: ANN202
    from app.models.accounts import UserAccount  # noqa: PLC0415

    account = UserAccount(phone=phone)
    db.add(account)
    db.flush()
    return account
