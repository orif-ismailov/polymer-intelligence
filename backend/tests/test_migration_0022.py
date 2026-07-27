"""
Offline tests for migration 0022: company logo (P1 W1 — T1.1).

1. Revision chain 0022 → 0021 and 0022 is the single alembic head.
2. upgrade()/downgrade() callable.
3. `Company.logo_storage_path` is registered on Base.metadata as a nullable TEXT.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0022_company_logo.py"


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0022", _MIGRATION)
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
        assert module.revision == "0022"
        assert module.down_revision == "0021"

    def test_upgrade_downgrade_callable(self) -> None:
        module = _load_migration()
        assert callable(module.upgrade)
        assert callable(module.downgrade)

    def test_0022_is_single_head(self) -> None:
        script = _script_dir()
        assert script.get_heads() == ["0026"], (
            f"expected a single head 0026, got {script.get_heads()}"
        )


class TestMetadata:
    def test_logo_column_registered(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        companies = Base.metadata.tables["companies"]
        assert "logo_storage_path" in companies.c, (
            "Company.logo_storage_path must be on the model, or alembic autogenerate "
            "and every serializer will miss it"
        )
        column = companies.c.logo_storage_path
        # Nullable: a company without a logo is the normal case, not an error state.
        assert column.nullable is True
        assert "TEXT" in str(column.type).upper()
