"""
Runtime setting overrides against a real Postgres (migration 0045).

Everything here needs a database, which is why it is separate from
`test_settings_env_source.py`: what the unit suite can prove is that `.env` wins
when there is no row, and these prove the other half — that a row wins, that it
survives the trip through JSONB with its type intact, that a credential is
ciphertext at rest, and that a second SESSION sees a write the first made.

That last one is the point of the whole feature. A panel that only changed the
process it was clicked in would be worse than no panel: the operator would watch
the dashboard agree with them while the workers went on doing the old thing.

Run with:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \
        uv run pytest tests/test_settings_overrides_db.py -q
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session, sessionmaker

from alembic import command

BACKEND_DIR = Path(__file__).parent.parent

_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

_requires_real_db = pytest.mark.skipif(
    not _IS_REAL_DB,
    reason=(
        "Settings-override DB tests require a live localhost test PostgreSQL. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    return sa.create_engine(_DB_URL, pool_pre_ping=True)


@pytest.fixture(scope="module")
def migrated(engine: sa.Engine) -> sa.Engine:
    """A schema at head. `conftest.patch_env` pins DATABASE_URL to a placeholder
    for the session and alembic's env.py reads `settings.DATABASE_URL`, so both
    have to be pointed at the real database first."""
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
    """A clean override table per test, and a clean snapshot after it.

    The snapshot is module state, so an override left behind is an
    order-dependent failure in whatever runs next — the expensive kind.
    """
    from app.services import settings_service  # noqa: PLC0415

    factory = sessionmaker(bind=migrated, expire_on_commit=False)
    with factory() as session:
        session.execute(sa.text("DELETE FROM app_settings"))
        session.commit()
        try:
            yield session
        finally:
            session.rollback()
            session.execute(sa.text("DELETE FROM app_settings"))
            session.commit()
            settings_service.clear_snapshot()


def _refresh(db: Session) -> None:
    """Reload the snapshot regardless of the generation counter.

    `force` because these tests have no Redis to bump: without it the reload is
    gated on a generation read that cannot happen, and the assertion under test
    would be about the gate rather than about the table.
    """
    from app.services import settings_service  # noqa: PLC0415

    settings_service.AUTO_REFRESH = True
    try:
        settings_service.refresh(db, force=True)
    finally:
        settings_service.AUTO_REFRESH = False


@_requires_real_db
class TestTheTableExists:
    def test_migration_0045_created_it(self, migrated: sa.Engine) -> None:
        cols = {c["name"] for c in sa.inspect(migrated).get_columns("app_settings")}
        assert cols == {"key", "value", "is_secret", "updated_at", "updated_by"}


@_requires_real_db
class TestRoundTrip:
    def test_an_override_wins_over_env_after_a_refresh(self, db: Session) -> None:
        from app.services import settings_service  # noqa: PLC0415

        assert settings_service.get("gov_registry_mode") == "stub"
        # The rail needs its credential; that guard has its own test below. Here
        # it is just a precondition for reaching the thing under test.
        settings_service.set_override(db, "didox_partner_token", "a-real-token", None)
        db.commit()
        _refresh(db)

        settings_service.set_override(db, "gov_registry_mode", "didox", None)
        db.commit()
        _refresh(db)
        assert settings_service.get("gov_registry_mode") == "didox"
        # …and `.env` still says what it said. Both halves are what the panel shows.
        assert settings_service.env_value("gov_registry_mode") == "stub"

    def test_reset_returns_the_env_value(self, db: Session) -> None:
        from app.services import settings_service  # noqa: PLC0415

        settings_service.set_override(db, "news_refresh_interval_minutes", 15, None)
        db.commit()
        _refresh(db)
        assert settings_service.get("news_refresh_interval_minutes") == 15

        settings_service.clear_override(db, "news_refresh_interval_minutes")
        db.commit()
        _refresh(db)
        assert settings_service.get("news_refresh_interval_minutes") == 60
        assert db.execute(sa.text("SELECT count(*) FROM app_settings")).scalar_one() == 0

    @pytest.mark.parametrize(
        ("key", "written", "expected"),
        [
            ("news_ai_enabled", "false", False),
            ("news_refresh_interval_minutes", "45", 45),
            ("ingest_per_host_delay_seconds", "1.5", 1.5),
            ("news_prompt_version", "v2", "v2"),
            ("request_notify_chat_id", "", None),
        ],
    )
    def test_types_survive_the_round_trip(
        self, db: Session, key: str, written: object, expected: object
    ) -> None:
        """JSONB plus a pydantic coercion is two chances to lose a type. A bool
        that comes back as 1, or an int as "45", would read as working right up
        until something compared it."""
        from app.services import settings_service  # noqa: PLC0415

        settings_service.set_override(db, key, written, None)
        db.commit()
        _refresh(db)
        value = settings_service.get(key)
        assert value == expected
        assert type(value) is type(expected)

    def test_a_second_session_sees_the_write(self, db: Session, migrated: sa.Engine) -> None:
        """The whole feature, in one assertion: an api process writes, a worker
        process reads. Two sessions is the closest a test gets to two processes,
        and it is the boundary the override has to cross."""
        from app.services import settings_service  # noqa: PLC0415

        settings_service.set_override(db, "escrow_mode", "stub", None)
        settings_service.set_override(db, "dangerous_check_enforced", True, None)
        db.commit()

        factory = sessionmaker(bind=migrated, expire_on_commit=False)
        with factory() as other:
            settings_service.clear_snapshot()  # a cold process, no snapshot yet
            _refresh(other)
        assert settings_service.get("dangerous_check_enforced") is True


@_requires_real_db
class TestSecrets:
    def test_a_credential_is_ciphertext_at_rest(self, db: Session) -> None:
        """Encryption is what makes this table safe to hold a partner token. The
        assertion is on the STORED bytes, because that is the thing a backup, a
        replica, or a `SELECT *` would expose."""
        from app.services import settings_service  # noqa: PLC0415

        secret = "partner-token-abcdef123456"
        settings_service.set_override(db, "didox_partner_token", secret, None)
        db.commit()

        stored = db.execute(sa.text("SELECT value, is_secret FROM app_settings")).one()
        assert stored.is_secret is True
        assert secret not in str(stored.value)

        _refresh(db)
        assert settings_service.get("didox_partner_token") == secret

    def test_the_listing_never_returns_it(self, db: Session) -> None:
        from app.services import settings_service  # noqa: PLC0415

        secret = "partner-token-abcdef123456"
        settings_service.set_override(db, "didox_partner_token", secret, None)
        db.commit()

        rows = {r["key"]: r for r in settings_service.get_all(db)}
        row = rows["didox_partner_token"]
        assert secret not in str(row)
        assert row["value"] == "••••3456"
        assert row["overridden"] is True


@_requires_real_db
class TestValidationAtTheWrite:
    def test_a_bad_value_never_reaches_the_table(self, db: Session) -> None:
        from app.services import settings_service  # noqa: PLC0415

        with pytest.raises(settings_service.InvalidSetting):
            settings_service.set_override(db, "news_refresh_interval_minutes", 1, None)
        db.rollback()
        assert db.execute(sa.text("SELECT count(*) FROM app_settings")).scalar_one() == 0

    def test_a_rail_is_validated_against_the_other_overrides(self, db: Session) -> None:
        """Two writes that are only valid together must be able to be made one at
        a time. The candidate model layers the live overrides on top of `.env`,
        so setting the token first makes the mode acceptable second — without
        that, the sequence an operator would actually perform is impossible.
        """
        from app.services import settings_service  # noqa: PLC0415

        settings_service.set_override(db, "didox_partner_token", "", None)
        db.commit()
        _refresh(db)
        with pytest.raises(settings_service.InvalidSetting, match="DIDOX_PARTNER_TOKEN"):
            settings_service.set_override(db, "gov_registry_mode", "didox", None)
        db.rollback()

        settings_service.set_override(db, "didox_partner_token", "a-real-token", None)
        db.commit()
        _refresh(db)
        settings_service.set_override(db, "gov_registry_mode", "didox", None)
        db.commit()
        _refresh(db)
        assert settings_service.get("gov_registry_mode") == "didox"


@_requires_real_db
class TestWithdrawnOptIn:
    def test_a_row_for_a_no_longer_overridable_key_stops_applying(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Taking `overridable` off a spec has to disarm existing rows, not leave
        them quietly in force — otherwise revoking the opt-in would be a change
        that looks made and is not."""
        from app.services import settings_service  # noqa: PLC0415

        settings_service.set_override(db, "news_refresh_interval_minutes", 15, None)
        db.commit()
        _refresh(db)
        assert settings_service.get("news_refresh_interval_minutes") == 15

        spec = settings_service.SPECS["news_refresh_interval_minutes"]
        monkeypatch.setitem(
            settings_service.SPECS,
            spec.key,
            settings_service.SettingSpec(
                spec.key, spec.env_var, spec.label, spec.group, overridable=False
            ),
        )
        _refresh(db)
        assert settings_service.get("news_refresh_interval_minutes") == 60
        # The row is still there — disarming it is a read-side decision, so
        # restoring the opt-in restores the operator's value rather than losing it.
        assert db.execute(sa.text("SELECT count(*) FROM app_settings")).scalar_one() == 1
