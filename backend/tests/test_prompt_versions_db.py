"""
Authored prompt versions against a real Postgres (migration 0046).

What these pin is the one property the whole design exists for: **a version
string means one text, forever.** Everything else here — the sha dedup, the
refusal of an empty body, the loader's resolution order — is a consequence of
it, and each is a way that property could quietly stop holding.

The failure this prevents has no symptom. `load_news_prompt` caches per process
keyed on the version string, so a mutable body would leave some workers on the
old text and some on the new, both journalling the same `prompt_version` into
`parse_runs`. Nothing would error; the classifications would simply stop being
explainable, and no later fix could recover which article got which prompt.

Run with:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \
        uv run pytest tests/test_prompt_versions_db.py -q
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
        "Prompt-version DB tests require a live localhost test PostgreSQL. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)

FAMILY = "news_extract"


@pytest.fixture(scope="module")
def migrated() -> sa.Engine:
    from app.core.config import settings  # noqa: PLC0415

    try:
        settings.DATABASE_URL = _DB_URL
    except Exception:  # noqa: BLE001 — frozen settings: bypass validation
        object.__setattr__(settings, "DATABASE_URL", _DB_URL)

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _DB_URL)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    return sa.create_engine(_DB_URL, pool_pre_ping=True)


@pytest.fixture
def db(migrated: sa.Engine) -> Generator[Session, None, None]:
    from app.services import settings_service  # noqa: PLC0415

    factory = sessionmaker(bind=migrated, expire_on_commit=False)
    with factory() as session:
        session.execute(sa.text("DELETE FROM prompt_versions"))
        session.commit()
        try:
            yield session
        finally:
            session.rollback()
            session.execute(sa.text("DELETE FROM prompt_versions"))
            session.commit()
            settings_service.clear_snapshot()


def _refresh(db: Session) -> None:
    """Load the snapshot on this session, bypassing the generation gate."""
    from app.services import settings_service  # noqa: PLC0415

    settings_service.AUTO_REFRESH = True
    try:
        settings_service.refresh(db, force=True)
    finally:
        settings_service.AUTO_REFRESH = False


@_requires_real_db
class TestTheTableIsAppendOnly:
    def test_migration_0046_created_it(self, migrated: sa.Engine) -> None:
        cols = {c["name"] for c in sa.inspect(migrated).get_columns("prompt_versions")}
        assert cols == {
            "id", "family", "version", "body", "body_sha256", "note", "created_by", "created_at",
        }

    def test_there_is_no_updated_at(self, migrated: sa.Engine) -> None:
        """The structural tell. A column for "when was this last changed" would
        be an invitation to change it, and the answer must always be "never"."""
        cols = {c["name"] for c in sa.inspect(migrated).get_columns("prompt_versions")}
        assert "updated_at" not in cols

    def test_the_service_exposes_no_update_path(self) -> None:
        from app.services import prompt_service  # noqa: PLC0415

        assert not hasattr(prompt_service, "update_version")
        assert not hasattr(prompt_service, "edit_version")

    def test_a_blank_body_is_refused_by_the_schema_too(self, db: Session) -> None:
        """Refused at the service, the API and here. Three times, because an
        empty system prompt produces no error anywhere downstream — the model
        simply runs with no instructions."""
        with pytest.raises(sa.exc.IntegrityError):
            db.execute(
                sa.text(
                    "INSERT INTO prompt_versions (family, version, body, body_sha256) "
                    "VALUES (:f, 'v99', '   ', 'x')"
                ),
                {"f": FAMILY},
            )
        db.rollback()


@_requires_real_db
class TestAuthoring:
    def test_a_version_is_created_and_numbered_past_the_shipped_files(self, db: Session) -> None:
        from app.services import prompt_service  # noqa: PLC0415

        # v1..v3 ship in the image, so the first authored version is v4 — numbering
        # against the table alone would collide with a file on the next release.
        row, created = prompt_service.create_version(db, FAMILY, "AUTHORED PROMPT")
        db.commit()
        assert created is True
        assert row.version == "v4"

    def test_saving_unchanged_text_returns_the_same_version(self, db: Session) -> None:
        """An operator pressing Save twice must not mint v5, v6, v7 that differ
        in nothing — the `raw_items` content-hash bargain."""
        from app.services import prompt_service  # noqa: PLC0415

        first, created_first = prompt_service.create_version(db, FAMILY, "SAME TEXT")
        db.commit()
        second, created_second = prompt_service.create_version(db, FAMILY, "SAME TEXT")
        db.commit()

        assert created_first is True and created_second is False
        assert first.id == second.id
        assert db.execute(sa.text("SELECT count(*) FROM prompt_versions")).scalar_one() == 1

    @pytest.mark.parametrize("body", ["", "   ", "\n\t "])
    def test_an_empty_body_is_refused(self, db: Session, body: str) -> None:
        from app.services import prompt_service  # noqa: PLC0415

        with pytest.raises(prompt_service.InvalidPrompt):
            prompt_service.create_version(db, FAMILY, body)

    def test_an_oversized_body_is_refused(self, db: Session) -> None:
        """The prompt is billed on every article, so its length is a recurring
        cost that is invisible at the moment of pasting."""
        from app.services import prompt_service  # noqa: PLC0415

        with pytest.raises(prompt_service.InvalidPrompt, match="recurring cost"):
            prompt_service.create_version(db, FAMILY, "x" * (prompt_service.MAX_BODY_CHARS + 1))

    def test_the_audit_row_carries_no_prompt_text(self, db: Session) -> None:
        """`audit_log` has a different retention story from this table, and the
        body is already stored immutably one row away."""
        from app.services import prompt_service  # noqa: PLC0415

        secret_ish = "A DISTINCTIVE PHRASE THAT MUST NOT APPEAR IN THE AUDIT ROW"
        prompt_service.create_version(db, FAMILY, secret_ish)
        db.commit()

        row = db.execute(
            sa.text(
                "SELECT action, details FROM audit_log "
                "WHERE entity = 'prompt_versions' ORDER BY id DESC LIMIT 1"
            )
        ).one()
        assert row.action == "prompt.version_created"
        assert secret_ish not in str(row.details)
        assert row.details["bytes"] == len(secret_ish)


@_requires_real_db
class TestTheLoaderResolvesIt:
    def test_an_authored_version_reaches_the_extractor(self, db: Session) -> None:
        """Create → refresh → the loader returns the new text, with no restart
        and without the loader touching the database."""
        from app.services import prompt_service  # noqa: PLC0415
        from parsing.news_extractor import load_news_prompt  # noqa: PLC0415

        row, _ = prompt_service.create_version(db, FAMILY, "AUTHORED PROMPT BODY")
        db.commit()
        _refresh(db)

        assert load_news_prompt(row.version) == "AUTHORED PROMPT BODY"

    def test_the_shipped_versions_still_load(self, db: Session) -> None:
        """Authoring must not shadow the image. v3 is what a Reset goes back to."""
        from app.services import prompt_service  # noqa: PLC0415
        from parsing.news_extractor import load_news_prompt  # noqa: PLC0415

        prompt_service.create_version(db, FAMILY, "AUTHORED")
        db.commit()
        _refresh(db)

        assert load_news_prompt("v3").startswith("You are the News Intelligence")

    def test_an_unknown_version_still_raises(self, db: Session) -> None:
        """Never `""`. An empty prompt is valid and silent, which is what made
        this bug survive so long the first time."""
        from parsing.news_extractor import load_news_prompt  # noqa: PLC0415

        _refresh(db)
        with pytest.raises(FileNotFoundError):
            load_news_prompt("v99")

    def test_the_version_list_is_shipped_union_authored(self, db: Session) -> None:
        from app.services import prompt_service, settings_service  # noqa: PLC0415

        assert settings_service.allowed_values("news_prompt_version") == ("v1", "v2", "v3")
        prompt_service.create_version(db, FAMILY, "AUTHORED")
        db.commit()
        _refresh(db)
        assert settings_service.allowed_values("news_prompt_version") == ("v1", "v2", "v3", "v4")

    def test_an_authored_version_can_be_activated_like_any_setting(self, db: Session) -> None:
        """Activation is an ordinary override, which is what buys it validation,
        an audit row and cross-process propagation for free."""
        from app.services import prompt_service, settings_service  # noqa: PLC0415

        prompt_service.create_version(db, FAMILY, "AUTHORED")
        db.commit()
        _refresh(db)

        settings_service.set_override(db, "news_prompt_version", "v4", None)
        db.commit()
        _refresh(db)
        assert settings_service.get("news_prompt_version") == "v4"

    def test_activating_a_version_that_exists_nowhere_is_refused(self, db: Session) -> None:
        from app.services import settings_service  # noqa: PLC0415

        _refresh(db)
        with pytest.raises(settings_service.InvalidSetting):
            settings_service.set_override(db, "news_prompt_version", "v99", None)


class TestTheLoaderTouchesNoDatabase:
    def test_load_news_prompt_opens_no_connection(self) -> None:
        """The reason bodies ride in the settings snapshot at all.

        `extract_news` runs inside `parse_news_item`'s open transaction, so a
        checkout here is the nested-connection pool deadlock — not a slow path.
        The same assertion `test_settings_env_source.py` makes for `get()`.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from app.services import settings_service  # noqa: PLC0415
        from parsing.news_extractor import load_news_prompt  # noqa: PLC0415

        settings_service.seed_prompts({("news_extract", "v4"): "AUTHORED"})
        with patch("app.core.db.SessionLocal") as session_local:
            assert load_news_prompt("v4") == "AUTHORED"
            load_news_prompt("v3")  # the shipped path too
        session_local.assert_not_called()
