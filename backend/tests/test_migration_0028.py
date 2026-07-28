"""
Offline tests for migration 0028: labs and samples (P6 W1 — T1.1).

One migration for one bounded context. It brings in:

1. `lab_partners` — the directory of partner laboratories. The analysis itself
   is a MANUAL process (TZ §5): the platform orchestrates the request and stores
   the result, it does not run the lab.
2. `lab_orders` — a company's request for an analysis, about an offer OR about a
   deal (CHECK: at least one). Staff drive the statuses. `done` is the only
   status that produces something, so it is the only one the schema constrains:
   a done order must point at the passport it produced.
3. `sample_requests` — a buyer asking a seller for a physical sample. The seller
   company is COPIED onto the row rather than read through the offer, so the
   seller's inbox does not change shape when an offer is edited. One live
   request per (offer, buyer) is a partial unique index, not an app-level if.
4. `seller_offers` gains the sample terms (available / price / dispatch days)
   and `lab_verified` — the flag only `lab_service.complete_with_result` sets,
   which is what separates "the seller uploaded a passport" from "we had it
   analysed".

(`app.*` is imported inside the tests: the conftest env patch is a session
fixture and does not exist at collection time.)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0028_lab.py"


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0028", _MIGRATION)
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


class TestRevisionChain:
    def test_revision_and_down_revision(self) -> None:
        module = _load_migration()
        assert module.revision == "0028"
        assert module.down_revision == "0027"

    def test_upgrade_downgrade_callable(self) -> None:
        module = _load_migration()
        assert callable(module.upgrade)
        assert callable(module.downgrade)


class TestEnums:
    def test_lab_order_statuses(self) -> None:
        from app.models.enums import LabOrderStatus  # noqa: PLC0415

        assert [m.value for m in LabOrderStatus] == [
            "submitted",
            "accepted",
            "sample_awaited",
            "in_analysis",
            "done",
            "rejected",
        ]

    def test_sample_request_statuses(self) -> None:
        from app.models.enums import SampleRequestStatus  # noqa: PLC0415

        assert [m.value for m in SampleRequestStatus] == [
            "requested",
            "accepted",
            "declined",
            "sent",
            "received",
            "rejected_by_buyer",
        ]

    def test_offer_file_kind_gains_the_lab_passport(self) -> None:
        from app.models.enums import OfferFileKind  # noqa: PLC0415

        assert "lab_passport" in {m.value for m in OfferFileKind}

    def test_deal_document_kind_already_had_one(self) -> None:
        """P2 shipped `lab_passport` on the deal side; P6 must not duplicate it."""
        from app.models.enums import DealDocumentKind  # noqa: PLC0415

        assert "lab_passport" in {m.value for m in DealDocumentKind}

    def test_migration_adds_the_enum_value_outside_a_transaction(self) -> None:
        """ALTER TYPE … ADD VALUE cannot run inside a transaction block."""
        source = _MIGRATION.read_text(encoding="utf-8")
        assert "autocommit_block" in source
        assert "ADD VALUE IF NOT EXISTS 'lab_passport'" in source


class TestLabPartners:
    def test_registered(self) -> None:
        assert "lab_partners" in _metadata().tables

    def test_a_partner_may_but_need_not_be_a_registered_company(self) -> None:
        """A lab we phone is a directory entry; a lab that signed up is also a
        company with the `laboratory` business role. Both are partners."""
        partners = _metadata().tables["lab_partners"]
        assert partners.c.company_id.nullable is True

    def test_retired_rather_than_deleted(self) -> None:
        """A finished order points at the lab that ran it — the row must survive."""
        partners = _metadata().tables["lab_partners"]
        assert "is_active" in partners.c


class TestLabOrders:
    def test_registered(self) -> None:
        assert "lab_orders" in _metadata().tables

    def test_number_is_unique(self) -> None:
        """The operator quotes it on the phone; two orders must not share one."""
        orders = _metadata().tables["lab_orders"]
        assert orders.c.number.unique

    def test_an_order_is_always_about_an_offer_or_a_deal(self) -> None:
        orders = _metadata().tables["lab_orders"]
        assert orders.c.offer_id.nullable is True
        assert orders.c.deal_id.nullable is True
        assert "ck_lab_order_target" in _check_names("lab_orders"), (
            "an order attached to neither an offer nor a deal has nowhere to put "
            "its result"
        )

    def test_done_requires_the_passport_it_produced(self) -> None:
        """The whole point of the status. Enforced in the schema so no future
        caller can mark an order done and leave the seller with a badge and no
        document behind it."""
        assert "ck_lab_order_done_has_result" in _check_names("lab_orders")

    def test_the_result_is_a_pointer_not_a_second_copy_of_the_path(self) -> None:
        """The S3 key already lives on the file row; a duplicate would drift."""
        orders = _metadata().tables["lab_orders"]
        assert "result_document_path" not in orders.c
        for column, target in (
            ("result_offer_file_id", "seller_offer_files"),
            ("result_deal_document_id", "deal_documents"),
        ):
            fks = [fk for fk in orders.c[column].foreign_keys]
            assert fks and fks[0].column.table.name == target
            assert fks[0].ondelete == "SET NULL"


class TestSampleRequests:
    def test_registered(self) -> None:
        assert "sample_requests" in _metadata().tables

    def test_the_seller_is_stored_not_followed_through_the_offer(self) -> None:
        """The seller's inbox is queried by seller_company_id; reading it through
        the offer would make the inbox depend on the offer never being edited."""
        samples = _metadata().tables["sample_requests"]
        assert samples.c.seller_company_id.nullable is False

    def test_parties_are_distinct(self) -> None:
        assert "ck_sample_parties_distinct" in _check_names("sample_requests")

    def test_the_courier_and_the_address_are_recorded(self) -> None:
        samples = _metadata().tables["sample_requests"]
        for column in ("qty", "courier", "tracking_ref", "delivery_address"):
            assert column in samples.c
        assert samples.c.delivery_address.nullable is False, (
            "a sample with nowhere to go is not a request"
        )

    def test_one_live_request_per_offer_and_buyer(self) -> None:
        """Partial, like uq_rfq_response_active: a declined request must not lock
        the buyer out forever."""
        samples = _metadata().tables["sample_requests"]
        index = next(
            (i for i in samples.indexes if i.name == "uq_sample_request_active"), None
        )
        assert index is not None and index.unique
        where = str(index.dialect_options["postgresql"]["where"])
        for live in ("requested", "accepted", "sent"):
            assert live in where
        for terminal in ("declined", "received", "rejected_by_buyer"):
            assert terminal not in where

    def test_the_timeline_is_stamped(self) -> None:
        samples = _metadata().tables["sample_requests"]
        for column in ("accepted_at", "sent_at", "received_at"):
            assert column in samples.c


class TestSellerOfferLabColumns:
    def test_columns_registered(self) -> None:
        offers = _metadata().tables["seller_offers"]
        for column in (
            "samples_available",
            "sample_price",
            "sample_dispatch_days",
            "lab_verified",
        ):
            assert column in offers.c, f"seller_offers.{column} missing"

    def test_every_new_column_is_safe_on_a_live_table(self) -> None:
        offers = _metadata().tables["seller_offers"]
        for column in (
            "samples_available",
            "sample_price",
            "sample_dispatch_days",
            "lab_verified",
        ):
            spec = offers.c[column]
            assert spec.nullable or spec.server_default is not None, (
                f"{column} is NOT NULL with no server default"
            )

    def test_lab_verified_defaults_to_false(self) -> None:
        """Only the platform sets it (an order reaching `done`); every existing
        offer starts without the independent confirmation."""
        offers = _metadata().tables["seller_offers"]
        assert "false" in str(offers.c.lab_verified.server_default.arg).lower()


class TestOfferModelHelpers:
    def test_has_lab_passport_reads_the_files(self) -> None:
        """Not a cached column: the catalog query already selectinloads files,
        and a second source of truth for "is there a PDF attached" would drift."""
        from app.models.enums import OfferFileKind  # noqa: PLC0415
        from app.models.marketplace import SellerOffer, SellerOfferFile  # noqa: PLC0415

        offer = SellerOffer()
        offer.files = []
        assert offer.has_lab_passport is False
        assert offer.lab_passport_file_id is None

        passport = SellerOfferFile(kind=OfferFileKind.lab_passport, file_name="p.pdf")
        passport.id = 7
        offer.files = [SellerOfferFile(kind=OfferFileKind.image, file_name="a.jpg"), passport]
        assert offer.has_lab_passport is True
        assert offer.lab_passport_file_id == 7


class TestSingleHead:
    def test_0028_is_the_head(self) -> None:
        script = _script_dir()
        assert script.get_heads() == ["0028"], (
            f"expected a single head 0028, got {script.get_heads()}"
        )
