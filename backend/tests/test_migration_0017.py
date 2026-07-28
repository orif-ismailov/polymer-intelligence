"""
Offline tests for migration 0017: company verification & portal (R1).

Validates (no live DB — the real upgrade/downgrade drill runs against an ephemeral
Postgres in CI/dev):
1. Revision chain 0017 → 0016 and 0017 is the alembic head.
2. upgrade()/downgrade() are callable and the 14 R1 ENUM types are declared.
3. Base.metadata carries the 10 new tables (models registered in __init__).
4. The dual-origin marketplace bridge is reflected in the ORM: seller_offers.seller_id
   is nullable, company_id / created_by_user_account_id exist, ck_offer_origin CHECK
   is present (nullable seller_id regression guard, W1 acceptance).
5. The partial indexes ux_open_case + ix_outbox_unpublished are in the metadata.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0017_company_verification.py"

_NEW_TABLES = {
    "user_accounts",
    "sms_send_log",
    "companies",
    "company_members",
    "company_business_roles",
    "company_bank_accounts",
    "verification_cases",
    "verification_checks",
    "verification_documents",
    "domain_events",
}

_EXPECTED_ENUMS = {
    "account_status",
    "company_status",
    "company_member_role",
    "company_member_status",
    "company_business_role",
    "business_role_status",
    "bank_account_status",
    "bank_verification_method",
    "verification_case_type",
    "verification_case_status",
    "verification_check_type",
    "verification_check_status",
    "verification_document_kind",
    "document_review_status",
}


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0017", _MIGRATION)
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
        assert module.revision == "0017"
        assert module.down_revision == "0016"

    def test_upgrade_downgrade_callable(self) -> None:
        module = _load_migration()
        assert callable(module.upgrade)
        assert callable(module.downgrade)

    def test_0017_in_single_head_chain(self) -> None:
        # 0017 was the head at R1; later migrations (0018 dual-origin, 0019 market
        # index, 0020 e-imzo) supersede it. Assert a single linear head with 0017
        # an ancestor.
        script = _script_dir()
        assert script.get_heads() == ["0027"], (
            f"expected a single head 0027, got {script.get_heads()}"
        )
        assert script.get_revision("0018").down_revision == "0017"

    def test_declares_all_fourteen_enums(self) -> None:
        module = _load_migration()
        declared = {name for name, _ in module._ENUMS}
        assert declared == _EXPECTED_ENUMS
        assert len(module._ENUMS) == 14


class TestMetadataTables:
    def test_new_tables_registered(self) -> None:
        import app.models  # noqa: F401 — populate Base.metadata
        from app.core.db import Base

        assert _NEW_TABLES.issubset(set(Base.metadata.tables))

    def test_open_case_and_outbox_partial_indexes(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        case_indexes = {ix.name for ix in Base.metadata.tables["verification_cases"].indexes}
        assert "ux_open_case" in case_indexes
        event_indexes = {ix.name for ix in Base.metadata.tables["domain_events"].indexes}
        assert "ix_outbox_unpublished" in event_indexes

    def test_company_unique_jurisdiction_tax_id(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        constraint_names = {
            c.name for c in Base.metadata.tables["companies"].constraints
        }
        assert "uq_company_jurisdiction_tax_id" in constraint_names


class TestDualOriginBridge:
    """Nullable seller_id regression + dual-origin columns/constraint (W1 acceptance)."""

    def test_seller_id_is_nullable(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        assert Base.metadata.tables["seller_offers"].c.seller_id.nullable is True

    def test_company_and_author_columns_exist(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        cols = Base.metadata.tables["seller_offers"].c
        assert "company_id" in cols
        assert "created_by_user_account_id" in cols

    def test_offer_origin_check_constraint_present(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        constraint_names = {
            c.name for c in Base.metadata.tables["seller_offers"].constraints
        }
        assert "ck_offer_origin" in constraint_names

    def test_dormant_company_bridge_on_sellers_and_clients(self) -> None:
        import app.models  # noqa: F401
        from app.core.db import Base

        assert "company_id" in Base.metadata.tables["sellers"].c
        assert "company_id" in Base.metadata.tables["clients"].c
