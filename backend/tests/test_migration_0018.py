"""
Offline tests for migration 0018: portal parity (R2 W1 T1.1).

Validates (no live DB — the real upgrade/downgrade drill runs against an ephemeral
Postgres in CI/dev, see test_migration_0018_db.py):
1. Revision chain 0018 → 0017 and 0018 is the alembic head.
2. upgrade()/downgrade() are callable.
3. Base.metadata carries the new `portal_notifications` table with its columns +
   the (user_account_id, read_at, id DESC) unread index.
4. Dual-origin relaxation on `requests`: client_id is nullable, company_id /
   created_by_user_account_id columns exist, ck_request_origin CHECK is present.
5. Dual-origin relaxation on `offer_requests`: same trio + ck_inquiry_origin CHECK.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0018_portal_parity.py"


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0018", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


class TestRevisionChain:
    def test_revision_and_down_revision(self) -> None:
        module = _load_migration()
        assert module.revision == "0018"
        assert module.down_revision == "0017"

    def test_upgrade_downgrade_callable(self) -> None:
        module = _load_migration()
        assert callable(module.upgrade)
        assert callable(module.downgrade)

    def test_0018_is_head(self) -> None:
        heads = _script_dir().get_heads()
        assert heads == ["0018"], f"expected 0018 to be the sole head, got {heads}"


class TestPortalNotificationsTable:
    def test_table_registered_with_columns(self) -> None:
        import app.models  # noqa: F401 — populate Base.metadata
        from app.core.db import Base

        assert "portal_notifications" in Base.metadata.tables
        cols = Base.metadata.tables["portal_notifications"].c
        for name in (
            "id",
            "user_account_id",
            "kind",
            "title_key",
            "body_key",
            "params",
            "entity",
            "entity_id",
            "read_at",
            "created_at",
        ):
            assert name in cols, f"portal_notifications missing column {name!r}"

    def test_user_account_id_not_null(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        assert (
            Base.metadata.tables["portal_notifications"].c.user_account_id.nullable
            is False
        )

    def test_unread_index_present(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        index_cols = {
            tuple(c.name for c in ix.columns)
            for ix in Base.metadata.tables["portal_notifications"].indexes
        }
        assert (
            "user_account_id",
            "read_at",
            "id",
        ) in index_cols, f"expected unread composite index, got {index_cols}"


class TestRequestDualOrigin:
    def test_client_id_is_nullable(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        assert Base.metadata.tables["requests"].c.client_id.nullable is True

    def test_origin_columns_exist(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        cols = Base.metadata.tables["requests"].c
        assert "company_id" in cols
        assert "created_by_user_account_id" in cols

    def test_request_origin_check_present(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        names = {c.name for c in Base.metadata.tables["requests"].constraints}
        assert "ck_request_origin" in names


class TestInquiryDualOrigin:
    def test_client_id_is_nullable(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        assert Base.metadata.tables["offer_requests"].c.client_id.nullable is True

    def test_origin_columns_exist(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        cols = Base.metadata.tables["offer_requests"].c
        assert "company_id" in cols
        assert "created_by_user_account_id" in cols

    def test_inquiry_origin_check_present(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        names = {c.name for c in Base.metadata.tables["offer_requests"].constraints}
        assert "ck_inquiry_origin" in names
