"""
Offline tests for migration 0020: E-IMZO verification rails (R3 Stage A T1.3).

Validates (no live DB — the real upgrade/downgrade drill runs against an ephemeral
Postgres in CI/dev, see test_migration.py):
1. Revision chain 0020 → 0019 and 0020 is the single alembic head.
2. upgrade()/downgrade() are callable.
3. Base.metadata carries signature_evidence, company_person_data,
   integration_call_log with their key columns + indexes.
4. companies gains a non-null identity_locked column.
5. VerificationCheckType has the new eimzo_signature member.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0020_eimzo.py"

_NEW_TABLES = {"signature_evidence", "company_person_data", "integration_call_log"}


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0020", _MIGRATION)
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
        assert module.revision == "0020"
        assert module.down_revision == "0019"

    def test_upgrade_downgrade_callable(self) -> None:
        module = _load_migration()
        assert callable(module.upgrade)
        assert callable(module.downgrade)

    def test_0020_is_single_head(self) -> None:
        script = _script_dir()
        assert script.get_heads() == ["0025"], (
            f"expected a single head 0025, got {script.get_heads()}"
        )
        assert script.get_revision("0020").down_revision == "0019"


class TestMetadataTables:
    def test_new_tables_registered(self) -> None:
        import app.models  # noqa: F401 — populate Base.metadata
        from app.core.db import Base

        assert _NEW_TABLES.issubset(set(Base.metadata.tables))

    def test_signature_evidence_columns(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        cols = Base.metadata.tables["signature_evidence"].c
        for name in (
            "company_id",
            "user_account_id",
            "purpose",
            "challenge",
            "pkcs7_storage_path",
            "pkcs7_sha256",
            "cert_subject",
            "signed_at",
        ):
            assert name in cols, name

    def test_company_person_data_columns(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        cols = Base.metadata.tables["company_person_data"].c
        for name in ("company_id", "full_name_enc", "pinfl_enc", "pinfl_last4", "position", "source"):
            assert name in cols, name

    def test_integration_call_log_indexes(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        idx = {ix.name for ix in Base.metadata.tables["integration_call_log"].indexes}
        assert "ix_integration_call_log_created" in idx
        assert "ix_integration_call_log_provider" in idx

    def test_companies_identity_locked_not_null(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        col = Base.metadata.tables["companies"].c["identity_locked"]
        assert col.nullable is False


class TestEnum:
    def test_eimzo_signature_member(self) -> None:
        from app.models.enums import VerificationCheckType

        assert VerificationCheckType.eimzo_signature.value == "eimzo_signature"
