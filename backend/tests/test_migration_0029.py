"""Offline tests for migration 0029: gov-registry snapshots (R6 / P7.c — T4.1).

One small migration for one idea: **what a registry told us about a company is
evidence, and evidence is immutable**.

`registry_snapshots` therefore has no `updated_at` and no update path anywhere in
the codebase. A fresh check is a new row; the history of a company's registry
checks IS the sequence of its rows. That matters more here than elsewhere,
because two very different things write these rows —

  * `source='registry'` — an API answered (ПЦД, once that access exists);
  * `source='manual'` — an operator read an open service (my.soliq.uz for VAT,
    license.gov.uz for licences) and transcribed the result, attaching a
    screenshot. INTEGRATIONS.md §3 sanctions this as the pre-ПЦД bridge, and it
    is the half of P7.c that works today.

Overwriting a row would erase which of the two said what, and when.

The two new `verification_check_type` values are added with
`ALTER TYPE … ADD VALUE`, which cannot run inside a transaction block.

(`app.*` is imported inside the tests: the conftest env patch is a session
fixture and does not exist at collection time.)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0029_gov_registry.py"


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0029", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


def _metadata():  # noqa: ANN202
    import app.models  # noqa: F401, PLC0415
    from app.core.db import Base  # noqa: PLC0415

    return Base.metadata


def _check_names(table_name: str) -> set[str]:
    from sqlalchemy import CheckConstraint  # noqa: PLC0415

    table = _metadata().tables[table_name]
    return {
        c.name
        for c in table.constraints
        if isinstance(c, CheckConstraint) and c.name is not None
    }


class TestRevision:
    def test_revision_and_down_revision(self) -> None:
        module = _load_migration()
        assert module.revision == "0029"  # type: ignore[attr-defined]
        assert module.down_revision == "0028"  # type: ignore[attr-defined]

    def test_upgrade_downgrade_callable(self) -> None:
        module = _load_migration()
        assert callable(module.upgrade)  # type: ignore[attr-defined]
        assert callable(module.downgrade)  # type: ignore[attr-defined]

    def test_0029_is_the_head(self) -> None:
        assert _script_dir().get_heads() == ["0029"], (
            "a second head means two migrations claim the same parent"
        )


class TestCheckTypes:
    def test_the_two_registry_checks_exist(self) -> None:
        from app.models.enums import VerificationCheckType  # noqa: PLC0415

        assert VerificationCheckType.gov_registry.value == "gov_registry"
        assert VerificationCheckType.vat_status.value == "vat_status"

    def test_the_r1_check_types_are_untouched(self) -> None:
        """Appending to a PG enum is safe; reordering or renaming is not."""
        from app.models.enums import VerificationCheckType  # noqa: PLC0415

        assert [c.value for c in VerificationCheckType][:5] == [
            "tax_id_format",
            "bank_requisites",
            "documents_complete",
            "manual_kyb",
            "eimzo_signature",
        ]

    def test_the_values_are_added_outside_a_transaction(self) -> None:
        source = _MIGRATION.read_text(encoding="utf-8")
        assert "autocommit_block" in source
        assert source.count("ADD VALUE IF NOT EXISTS") >= 2


class TestRegistrySnapshots:
    def test_registered(self) -> None:
        assert "registry_snapshots" in _metadata().tables

    def test_the_row_is_immutable(self) -> None:
        """No `updated_at`: a new check is a new row, never an edit of an old one.

        This is the whole point of the table — an operator's transcription and a
        registry's answer must stay distinguishable, with their own timestamps.
        """
        columns = set(_metadata().tables["registry_snapshots"].columns.keys())
        assert "updated_at" not in columns
        assert {"fetched_at", "created_at"} <= columns

    def test_kind_and_source_are_closed_sets(self) -> None:
        names = _check_names("registry_snapshots")
        assert "ck_registry_snapshot_kind" in names
        assert "ck_registry_snapshot_source" in names

    def test_the_three_kinds_are_the_three_lookups(self) -> None:
        """One kind per `GovRegistryClient` method — company, licences, VAT."""
        from app.models.registry import SNAPSHOT_KINDS  # noqa: PLC0415

        assert set(SNAPSHOT_KINDS) == {"company", "licenses", "vat"}

    def test_a_manual_snapshot_can_carry_its_screenshot(self) -> None:
        """The operator's evidence gets the same treatment as a PKCS#7: a storage
        key plus the sha256 of the bytes, so tampering is detectable."""
        columns = _metadata().tables["registry_snapshots"].columns
        assert columns["evidence_path"].nullable is True
        assert columns["evidence_sha256"].nullable is True

    def test_an_automatic_snapshot_has_no_author(self) -> None:
        """`created_by` is NULL when an API answered — nobody asserted anything."""
        assert _metadata().tables["registry_snapshots"].columns["created_by"].nullable is True

    def test_the_payload_is_required(self) -> None:
        """A snapshot with no content is not evidence of anything."""
        assert _metadata().tables["registry_snapshots"].columns["payload"].nullable is False

    def test_the_hot_query_is_indexed(self) -> None:
        """'The latest snapshot of kind X for company Y' is the only read path."""
        table = _metadata().tables["registry_snapshots"]
        indexes = {tuple(c.name for c in idx.columns) for idx in table.indexes}
        assert ("company_id", "kind", "id") in indexes

    def test_snapshots_follow_a_deleted_company(self) -> None:
        table = _metadata().tables["registry_snapshots"]
        fks = {fk.column.table.name: fk.ondelete for fk in table.foreign_keys}
        assert fks["companies"] == "CASCADE"


class TestMigrationMatchesTheModel:
    def test_the_migration_creates_the_table_the_model_declares(self) -> None:
        source = _MIGRATION.read_text(encoding="utf-8")
        assert 'create_table(\n        "registry_snapshots"' in source
        for column in _metadata().tables["registry_snapshots"].columns:
            assert f'"{column.name}"' in source, f"{column.name} missing from the migration"

    def test_the_model_is_registered_for_alembic(self) -> None:
        """`app/models/__init__.py` must import it or autogenerate cannot see it."""
        import app.models as models  # noqa: PLC0415

        assert hasattr(models, "RegistrySnapshot")
