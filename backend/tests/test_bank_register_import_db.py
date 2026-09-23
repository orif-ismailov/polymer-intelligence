"""Loading the bank register into Postgres (migration 0051).

The parser is proved by `test_bank_register.py` without a database. What needs a
real one is the part that can corrupt the live register: an upload replaces the
WHOLE table, so the properties worth pinning are about what happens when a load
goes wrong.

  * **A bad file must leave the working register untouched.** The parse happens
    before a single DELETE, mirroring the rule `verification/api_admin.py` already
    states for registry evidence: refuse before anything is recorded. Applied the
    other way round, a truncated download would empty the table and every MFO
    would stop resolving.
  * **Re-loading the same bytes is a no-op**, keyed on sha256 — which is what lets
    the seeder run on every deploy without rewriting 324 rows or inventing a new
    provenance row each time.
  * **A replace leaves no orphans.** `bank_branches.import_id` cascades, so the
    old rows go with the old import rather than lingering with a dangling key.

Run with:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \
        uv run pytest tests/test_bank_register_import_db.py -q
"""

from __future__ import annotations

import io
import os
import zipfile
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session, sessionmaker

from alembic import command

BACKEND_DIR = Path(__file__).parent.parent
_REGISTER = BACKEND_DIR / "app" / "seed" / "data" / "bank_branches.xlsx"

_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "Bank-register import tests require a live localhost test PostgreSQL. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    return sa.create_engine(_DB_URL, pool_pre_ping=True)


@pytest.fixture(scope="module")
def migrated(engine: sa.Engine) -> sa.Engine:
    from app.core.config import settings  # noqa: PLC0415

    try:
        settings.DATABASE_URL = _DB_URL
    except Exception:  # noqa: BLE001 — frozen settings: bypass validation
        object.__setattr__(settings, "DATABASE_URL", _DB_URL)

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _DB_URL)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    return engine


@pytest.fixture
def db(migrated: sa.Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=migrated, expire_on_commit=False)
    with factory() as session:
        session.execute(sa.text("DELETE FROM bank_register_imports"))
        session.commit()
        try:
            yield session
        finally:
            session.rollback()
            session.execute(sa.text("DELETE FROM bank_register_imports"))
            session.commit()


def _content() -> bytes:
    return _REGISTER.read_bytes()


def _junk_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "not a workbook")
    return buf.getvalue()


@_requires_real_db
class TestLoadingTheRegister:
    def test_it_imports_every_row_and_records_where_they_came_from(self, db: Session) -> None:
        from app.domains.reference import bank_service  # noqa: PLC0415

        outcome = bank_service.import_register(db, _content(), "bank_branches.xlsx")
        db.commit()

        assert outcome.row_count == 324
        assert outcome.file_created_at is not None
        assert outcome.file_created_at.isoformat() == "2024-11-18"

        rows = db.execute(sa.text("SELECT count(*) FROM bank_branches")).scalar_one()
        assert rows == 324
        name = db.execute(
            sa.text("SELECT bank_name FROM bank_branches WHERE mfo = '00401'")
        ).scalar_one()
        assert name == "ALOQABANK"

    def test_lookup_by_mfo(self, db: Session) -> None:
        from app.domains.reference import bank_service  # noqa: PLC0415

        bank_service.import_register(db, _content(), "bank_branches.xlsx")
        db.commit()

        found = bank_service.bank_by_mfo(db, "00401")
        assert found is not None
        assert found.bank_name == "ALOQABANK"
        assert bank_service.bank_by_mfo(db, "99999") is None

    def test_reloading_the_same_bytes_changes_nothing(self, db: Session) -> None:
        """Keyed on sha256 so the seeder can run on every deploy without
        rewriting 324 rows or adding a provenance row that records no change."""
        from app.domains.reference import bank_service  # noqa: PLC0415

        first = bank_service.import_register(db, _content(), "bank_branches.xlsx")
        db.commit()
        again = bank_service.import_register(db, _content(), "bank_branches.xlsx")
        db.commit()

        assert first.imported is True
        assert again.imported is False, "same file — nothing to do"
        imports = db.execute(sa.text("SELECT count(*) FROM bank_register_imports")).scalar_one()
        assert imports == 1
        rows = db.execute(sa.text("SELECT count(*) FROM bank_branches")).scalar_one()
        assert rows == 324


@_requires_real_db
class TestABadFileCannotDamageTheLiveRegister:
    def test_a_junk_upload_leaves_the_previous_register_intact(self, db: Session) -> None:
        """The whole reason the parse runs before the DELETE."""
        from app.domains.reference import bank_service  # noqa: PLC0415
        from app.domains.reference.bank_register import BankRegisterInvalid  # noqa: PLC0415

        bank_service.import_register(db, _content(), "bank_branches.xlsx")
        db.commit()

        with pytest.raises(BankRegisterInvalid):
            bank_service.import_register(db, _junk_zip(), "junk.xlsx")
        db.rollback()

        rows = db.execute(sa.text("SELECT count(*) FROM bank_branches")).scalar_one()
        assert rows == 324, "a rejected upload must not empty the table"
        name = db.execute(
            sa.text("SELECT bank_name FROM bank_branches WHERE mfo = '00401'")
        ).scalar_one()
        assert name == "ALOQABANK"

    def test_a_replace_leaves_no_orphan_branches(self, db: Session) -> None:
        """One import owns its rows; replacing drops the old ones with it."""
        from app.domains.reference import bank_service  # noqa: PLC0415

        bank_service.import_register(db, _content(), "first.xlsx")
        db.commit()
        # `force` is the deliberate re-load: same bytes, but apply them anyway.
        # It is what makes this a REPLACE rather than the sha256 no-op above.
        bank_service.import_register(db, _content(), "second.xlsx", force=True)
        db.commit()

        orphans = db.execute(
            sa.text(
                "SELECT count(*) FROM bank_branches b "
                "LEFT JOIN bank_register_imports i ON i.id = b.import_id "
                "WHERE i.id IS NULL"
            )
        ).scalar_one()
        assert orphans == 0
        rows = db.execute(sa.text("SELECT count(*) FROM bank_branches")).scalar_one()
        assert rows == 324, "replace, not append"
