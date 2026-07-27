"""
Offline tests for migration 0021: contracts (R3 Stage B T1.1).

1. Revision chain 0021 → 0020 and 0021 is the single alembic head.
2. upgrade()/downgrade() callable.
3. Base.metadata carries contract_templates, contracts, contract_signatures with
   key columns/constraints (parties-distinct CHECK, unique signature).
4. ContractStatus enum values.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0021_contracts.py"

_NEW_TABLES = {"contract_templates", "contracts", "contract_signatures"}


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0021", _MIGRATION)
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
        assert module.revision == "0021"
        assert module.down_revision == "0020"

    def test_upgrade_downgrade_callable(self) -> None:
        module = _load_migration()
        assert callable(module.upgrade)
        assert callable(module.downgrade)

    def test_0021_is_single_head(self) -> None:
        script = _script_dir()
        assert script.get_heads() == ["0026"], (
            f"expected a single head 0026, got {script.get_heads()}"
        )


class TestMetadata:
    def test_new_tables_registered(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        assert _NEW_TABLES.issubset(set(Base.metadata.tables))

    def test_parties_distinct_check(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        names = {c.name for c in Base.metadata.tables["contracts"].constraints}
        assert "ck_contract_parties_distinct" in names

    def test_unique_signature(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        names = {c.name for c in Base.metadata.tables["contract_signatures"].constraints}
        assert "uq_contract_signature" in names

    def test_contract_status_enum(self) -> None:
        from app.models.enums import ContractStatus

        assert ContractStatus.pending_signatures.value == "pending_signatures"
        assert ContractStatus.active.value == "active"
