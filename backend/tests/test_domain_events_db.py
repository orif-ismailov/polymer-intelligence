"""Real-Postgres tests for the transactional outbox (R1 W2 — acceptance).

Guarded exactly like test_news_filter_sql_db / test_catalog_search: they run only
against a developer-provisioned localhost DB named ``test_polymer`` and SKIP in CI
and in the default suite (whose conftest patch_env points DATABASE_URL at a
placeholder). Run against the dev stack's Postgres::

    PGPASS=$(docker exec deploy-postgres-1 printenv POSTGRES_PASSWORD)
    DATABASE_URL="postgresql+psycopg://pi_user:${PGPASS}@localhost:5432/test_polymer" \
        uv run pytest tests/test_domain_events_db.py -q

Covers the W2 acceptance list that pure-Python tests can't reach:
  * emit() inside a rolled-back transaction leaves no row;
  * two dispatchers running concurrently publish each event exactly once
    (FOR UPDATE SKIP LOCKED — a held lock is skipped, not double-dispatched);
  * an unknown event_type is skipped with a warning (not a crash) and still
    marked published so it can't wedge the poll loop.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa

if TYPE_CHECKING:
    from collections.abc import Iterator

BACKEND_DIR = Path(__file__).parent.parent

_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "Outbox DB tests require a live localhost test PostgreSQL. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


@pytest.fixture(scope="module")
def outbox_engine() -> sa.Engine:
    return sa.create_engine(_DB_URL, pool_pre_ping=True)


@pytest.fixture
def outbox_db(outbox_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[sa.Engine]:
    """Migrate to head, clean domain_events, and bind SessionLocal to this engine.

    conftest.patch_env forces DATABASE_URL to a placeholder for the whole session,
    and alembic's env.py reads settings.DATABASE_URL — point both at the real test
    DB. The dispatcher task imports app.core.db.SessionLocal lazily, so patching
    that attribute makes it run against test_polymer.
    """
    from alembic.config import Config  # noqa: PLC0415
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from alembic import command as alembic_command  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415

    original_url = settings.DATABASE_URL
    object.__setattr__(settings, "DATABASE_URL", _DB_URL)  # frozen settings: bypass validation

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _DB_URL)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    alembic_command.upgrade(cfg, "head")  # idempotent — builds the schema once

    with outbox_engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM domain_events"))

    session_factory = sessionmaker(bind=outbox_engine, expire_on_commit=False)
    monkeypatch.setattr("app.core.db.SessionLocal", session_factory)

    yield outbox_engine

    with outbox_engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM domain_events"))
    object.__setattr__(settings, "DATABASE_URL", original_url)


def _session_factory(engine: sa.Engine):  # noqa: ANN202
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    return sessionmaker(bind=engine, expire_on_commit=False)


@_requires_real_db
def test_emit_rolled_back_transaction_leaves_no_row(outbox_db: sa.Engine) -> None:
    from app.services import event_service, event_types  # noqa: PLC0415

    session = _session_factory(outbox_db)
    with session() as s:
        event_service.emit(s, event_types.COMPANY_REGISTERED, "company", 1, {"k": "v"})
        # flushed (event.id assigned) but NOT committed
        s.rollback()

    with session() as s:
        count = s.execute(sa.text("SELECT count(*) FROM domain_events")).scalar_one()
    assert count == 0


@_requires_real_db
def test_emit_committed_row_is_persisted_and_unpublished(outbox_db: sa.Engine) -> None:
    from app.services import event_service, event_types  # noqa: PLC0415

    session = _session_factory(outbox_db)
    with session() as s:
        event_service.emit(s, event_types.COMPANY_VERIFIED, "company", 99, {"n": 1})
        s.commit()

    with session() as s:
        row = s.execute(
            sa.text("SELECT event_type, aggregate_id, published_at FROM domain_events")
        ).one()
    assert row.event_type == event_types.COMPANY_VERIFIED
    assert row.aggregate_id == "99"
    assert row.published_at is None  # dispatcher hasn't run yet


@_requires_real_db
def test_dispatch_publishes_all_events_and_is_idempotent(outbox_db: sa.Engine) -> None:
    from app.services import event_service, event_types  # noqa: PLC0415
    from app.tasks.events import dispatch_domain_events  # noqa: PLC0415

    session = _session_factory(outbox_db)
    with session() as s:
        for i in range(3):
            event_service.emit(s, event_types.COMPANY_REGISTERED, "company", i, {"n": i})
        s.commit()

    assert dispatch_domain_events() == {"selected": 3, "published": 3}

    with session() as s:
        unpublished = s.execute(
            sa.text("SELECT count(*) FROM domain_events WHERE published_at IS NULL")
        ).scalar_one()
    assert unpublished == 0

    # Second run: nothing left to publish (published rows are filtered out).
    assert dispatch_domain_events() == {"selected": 0, "published": 0}


@_requires_real_db
def test_dispatch_skips_locked_rows_and_publishes_each_exactly_once(outbox_db: sa.Engine) -> None:
    """A concurrent dispatcher's locked rows are skipped, then published on the next run.

    Simulates two dispatchers: one holds FOR UPDATE SKIP LOCKED on the first two
    rows (open transaction), the other must publish only the remaining three.
    Releasing the lock, a second dispatch publishes exactly the held two — every
    event published once, none twice.
    """
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.services import event_service, event_types  # noqa: PLC0415
    from app.tasks.events import dispatch_domain_events  # noqa: PLC0415

    session = _session_factory(outbox_db)
    with session() as s:
        for i in range(5):
            event_service.emit(s, event_types.COMPANY_VERIFIED, "company", i, {"n": i})
        s.commit()

    locker = session()
    try:
        locked = (
            locker.execute(
                sa.select(DomainEvent)
                .where(DomainEvent.published_at.is_(None))
                .order_by(DomainEvent.id)
                .limit(2)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        assert len(locked) == 2  # this "dispatcher" holds two rows

        # The other dispatcher must skip the two locked rows → publish the other three.
        first = dispatch_domain_events()
        assert first["published"] == 3
    finally:
        locker.rollback()
        locker.close()

    # Lock released → the remaining two publish exactly once.
    second = dispatch_domain_events()
    assert second["published"] == 2

    with session() as s:
        total = s.execute(sa.text("SELECT count(*) FROM domain_events")).scalar_one()
        published = s.execute(
            sa.text("SELECT count(*) FROM domain_events WHERE published_at IS NOT NULL")
        ).scalar_one()
    assert total == 5
    assert published == 5  # every event published, each exactly once


@_requires_real_db
def test_dispatch_unknown_event_type_is_skipped_with_warning(
    outbox_db: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import MagicMock  # noqa: PLC0415

    import app.tasks.events as events  # noqa: PLC0415
    from app.models.events import DomainEvent  # noqa: PLC0415

    session = _session_factory(outbox_db)
    with session() as s:
        s.add(
            DomainEvent(
                event_type="totally.unknown",
                aggregate_type="x",
                aggregate_id="1",
                payload={},
            )
        )
        s.commit()

    # NB: the outbox_db fixture ran alembic, whose env.py fileConfig() reinstalls
    # root logging handlers — so caplog can't see the warning here. Patch the
    # module logger directly instead (the warning path is caplog-verified DB-free
    # in test_domain_events_dispatch.py).
    mock_logger = MagicMock()
    monkeypatch.setattr(events, "logger", mock_logger)

    result = events.dispatch_domain_events()

    # Skipped (no crash) but still marked published so it can't wedge the loop.
    assert result == {"selected": 1, "published": 1}
    warning_events = [call.args[0] for call in mock_logger.warning.call_args_list]
    assert "domain_event.unroutable" in warning_events
    with session() as s:
        unpublished = s.execute(
            sa.text("SELECT count(*) FROM domain_events WHERE published_at IS NULL")
        ).scalar_one()
    assert unpublished == 0
