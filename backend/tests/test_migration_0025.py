"""
Offline tests for migration 0025: offer sale fields + favorites (P4 W1 — T1.1).

Two unrelated things ride in one migration because both are small and both belong
to the offer surface:

1. `seller_offers` gains how the seller actually trades — a production lead time,
   a sale mode, and three "ready to deal" flags that become badges on the market
   card. Every one is nullable or defaulted: `seller_offers` is a live table with
   rows from two origins (TG sellers and portal companies), and a NOT NULL column
   without a default would fail the migration outright.
2. `offer_favorites` — a person's shortlist, keyed to the ACCOUNT rather than the
   company: a bookmark is personal, and a user switching company hats should keep
   their own list.

(`app.*` is imported inside the tests: the conftest env patch is a session
fixture and does not exist at collection time.)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0025_offer_sale_fields.py"


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0025", _MIGRATION)
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


class TestRevisionChain:
    def test_revision_and_down_revision(self) -> None:
        module = _load_migration()
        assert module.revision == "0025"
        assert module.down_revision == "0024"

    def test_upgrade_downgrade_callable(self) -> None:
        module = _load_migration()
        assert callable(module.upgrade)
        assert callable(module.downgrade)


class TestSaleModeEnum:
    def test_values(self) -> None:
        from app.models.enums import OfferSaleMode  # noqa: PLC0415

        assert [m.value for m in OfferSaleMode] == [
            "from_stock",
            "made_to_order",
            "recurring_contract",
        ]


class TestOfferSaleFields:
    def test_columns_registered(self) -> None:
        offers = _metadata().tables["seller_offers"]
        for column in (
            "lead_time_days",
            "sale_mode",
            "accepts_rfq",
            "accepts_contract",
            "accepts_escrow",
        ):
            assert column in offers.c, (
                f"seller_offers.{column} must be on the model, or every offer "
                f"serializer silently drops it"
            )

    def test_every_new_column_is_safe_on_a_live_table(self) -> None:
        """`seller_offers` already holds rows from two origins. A NOT NULL column
        without a server default would fail the migration on any real database."""
        offers = _metadata().tables["seller_offers"]
        for column in (
            "lead_time_days",
            "sale_mode",
            "accepts_rfq",
            "accepts_contract",
            "accepts_escrow",
        ):
            spec = offers.c[column]
            assert spec.nullable or spec.server_default is not None, (
                f"{column} is NOT NULL with no server default"
            )

    def test_rfq_is_the_only_readiness_flag_on_by_default(self) -> None:
        """Answering an RFQ costs a seller nothing, so it is opt-out. Signing a
        contract and holding money in escrow are commitments — opt-in."""
        offers = _metadata().tables["seller_offers"]
        assert "true" in str(offers.c.accepts_rfq.server_default.arg).lower()
        for column in ("accepts_contract", "accepts_escrow"):
            assert "false" in str(offers.c[column].server_default.arg).lower(), column

    def test_lead_time_is_optional_at_the_db_level(self) -> None:
        """It is required only for made-to-order offers, and that is a schema rule
        (which knows the availability) rather than a column constraint."""
        assert _metadata().tables["seller_offers"].c.lead_time_days.nullable is True


class TestOfferFavorites:
    def test_registered(self) -> None:
        assert "offer_favorites" in _metadata().tables

    def test_a_bookmark_belongs_to_a_person_not_a_company(self) -> None:
        favorites = _metadata().tables["offer_favorites"]
        assert "user_account_id" in favorites.c
        assert "company_id" not in favorites.c, (
            "a shortlist is personal — switching company hats must not change it"
        )

    def test_one_row_per_account_and_offer(self) -> None:
        favorites = _metadata().tables["offer_favorites"]
        uniques = {
            tuple(c.name for c in con.columns)
            for con in favorites.constraints
            if type(con).__name__ == "UniqueConstraint"
        }
        unique_indexes = {
            tuple(c.name for c in ix.columns) for ix in favorites.indexes if ix.unique
        }
        assert ("user_account_id", "offer_id") in uniques | unique_indexes, (
            "double-starring an offer must collide, not create a second row"
        )

    def test_a_deleted_offer_takes_its_bookmarks_with_it(self) -> None:
        favorites = _metadata().tables["offer_favorites"]
        fks = [fk for fk in favorites.foreign_keys if fk.column.table.name == "seller_offers"]
        assert fks and fks[0].ondelete == "CASCADE", (
            "a bookmark to a deleted offer is a dangling row nothing can render"
        )


class TestSingleHead:
    def test_0025_is_the_head(self) -> None:
        script = _script_dir()
        assert script.get_heads() == ["0026"], (
            f"expected a single head 0026, got {script.get_heads()}"
        )
