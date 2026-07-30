"""Offline tests for migration 0030: offer product facts.

Three columns for the three things the redesigned add-product flow
(`docs/new-design/product_creation.jpeg`) asks for and the offer row could not
hold: who made the goods, and the two chip rows on the product sheet.

`seller_offers` is live and carries rows from two origins (TG sellers and portal
companies), so all three are nullable — a bare NOT NULL would fail the migration
on any real database, and there is nothing to backfill them from.

(`app.*` is imported inside the tests: the conftest env patch is a session
fixture and does not exist at collection time.)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0030_offer_product_facts.py"

_COLUMNS = ("manufacturer", "key_properties", "applications")


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0030", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


def _offers_table():  # noqa: ANN202
    import app.models  # noqa: F401, PLC0415
    from app.core.db import Base  # noqa: PLC0415

    return Base.metadata.tables["seller_offers"]


class TestRevision:
    def test_migration_file_exists_and_is_wired(self) -> None:
        module = _load_migration()
        assert module.revision == "0030"  # type: ignore[attr-defined]
        assert module.down_revision == "0029"  # type: ignore[attr-defined]
        assert callable(module.upgrade)  # type: ignore[attr-defined]
        assert callable(module.downgrade)  # type: ignore[attr-defined]

    def test_0030_is_in_a_single_head_chain(self) -> None:
        # The invariant is "one head", not "0030 is the head" — pinning the revision
        # made every later migration fail a test about 0030. Same shape as the
        # sibling guards in test_migration_0029 and up.
        script = _script_dir()
        assert len(script.get_heads()) == 1, (
            f"a second head means two migrations claim the same parent: {script.get_heads()}"
        )
        assert script.get_revision("0030").down_revision == "0029"


class TestColumns:
    def test_the_three_columns_are_on_the_model(self) -> None:
        columns = _offers_table().c
        for name in _COLUMNS:
            assert name in columns, f"seller_offers.{name} is missing from the model"

    def test_every_added_column_is_nullable(self) -> None:
        """The table is live and carries rows of two origins; a NOT NULL here
        would fail the migration on any database with data in it."""
        columns = _offers_table().c
        for name in _COLUMNS:
            assert columns[name].nullable, f"seller_offers.{name} must be nullable"

    def test_the_chip_rows_are_jsonb(self) -> None:
        """Free text nobody queries by value — a join table would buy two more
        joins per card render and nothing else."""
        from sqlalchemy.dialects.postgresql import JSONB  # noqa: PLC0415

        columns = _offers_table().c
        assert isinstance(columns["key_properties"].type, JSONB)
        assert isinstance(columns["applications"].type, JSONB)

    def test_manufacturer_is_text_not_a_company_link(self) -> None:
        """The maker of the goods is usually not a party on this platform."""
        column = _offers_table().c["manufacturer"]
        assert column.foreign_keys == set()
