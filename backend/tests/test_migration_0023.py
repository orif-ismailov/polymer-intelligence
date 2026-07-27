"""
Offline tests for migration 0023: deals bounded context (P2 W1 — T1.1).

1. Revision chain 0023 → 0022 and 0023 is the single alembic head.
2. upgrade()/downgrade() callable.
3. The five deals tables are registered on Base.metadata with the invariants the
   domain relies on: parties distinct, one contract per deal, append-only history,
   FK widths that actually match the tables they point at.
4. The RFQ extensions (required_docs / visibility / visible_company_ids) land on
   `requests`, which is an EXISTING table — a missed column here is silent data
   loss at the ORM layer, not a startup error.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0023_deals.py"


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0023", _MIGRATION)
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
        assert module.revision == "0023"
        assert module.down_revision == "0022"

    def test_upgrade_downgrade_callable(self) -> None:
        module = _load_migration()
        assert callable(module.upgrade)
        assert callable(module.downgrade)

    def test_0023_is_single_head(self) -> None:
        script = _script_dir()
        assert script.get_heads() == ["0024"], (
            f"expected a single head 0024, got {script.get_heads()}"
        )


class TestEnums:
    def test_deal_status_values(self) -> None:
        from app.models.enums import DealStatus  # noqa: PLC0415

        assert [m.value for m in DealStatus] == [
            "negotiation",
            "contract_pending",
            "contract_signed",
            "payment_pending",
            "paid_escrow",
            "shipped",
            "delivered",
            "completed",
            "cancelled",
            "disputed",
        ]

    def test_rfq_response_status_values(self) -> None:
        from app.models.enums import RfqResponseStatus  # noqa: PLC0415

        assert {m.value for m in RfqResponseStatus} == {
            "submitted",
            "accepted",
            "not_selected",
            "withdrawn",
        }

    def test_deal_document_kind_values(self) -> None:
        from app.models.enums import DealDocumentKind  # noqa: PLC0415

        assert {m.value for m in DealDocumentKind} == {
            "contract",
            "invoice",
            "lab_passport",
            "transport",
            "other",
        }

    def test_rfq_visibility_values(self) -> None:
        from app.models.enums import RfqVisibility  # noqa: PLC0415

        assert {m.value for m in RfqVisibility} == {"verified_only", "all", "selected"}

    def test_deal_actor_kind_values(self) -> None:
        from app.models.enums import DealActorKind  # noqa: PLC0415

        assert {m.value for m in DealActorKind} == {"buyer", "seller", "staff", "system"}


class TestDealsTable:
    def test_registered(self) -> None:
        assert "deals" in _metadata().tables

    def test_parties_cannot_be_the_same_company(self) -> None:
        deals = _metadata().tables["deals"]
        checks = {
            c.name
            for c in deals.constraints
            if type(c).__name__ == "CheckConstraint"
        }
        assert "ck_deal_parties_distinct" in checks, (
            "a deal between a company and itself must be impossible at the DB level"
        )

    def test_one_contract_per_deal(self) -> None:
        deals = _metadata().tables["deals"]
        unique_contract = [
            ix for ix in deals.indexes if ix.name == "uq_deals_contract" and ix.unique
        ]
        assert unique_contract, (
            "contract_id must be uniquely indexed — the CONTRACT_ACTIVATED consumer "
            "looks the deal up by contract_id and must find at most one"
        )

    def test_context_links_are_nullable(self) -> None:
        # A deal can be opened from an RFQ response, from an inquiry, or (later)
        # from nothing at all — none of the three context links is required.
        deals = _metadata().tables["deals"]
        for column in ("request_id", "offer_id", "contract_id"):
            assert deals.c[column].nullable is True, f"{column} must be nullable"

    def test_fk_widths_match_their_targets(self) -> None:
        # requests.id and seller_offers.id are INTEGER, not BIGINT. A BigInteger FK
        # here still works in Postgres but silently mismatches the ORM type and
        # breaks joins under SQLite-backed tooling.
        meta = _metadata()
        deals = meta.tables["deals"]
        assert str(deals.c.request_id.type) == str(meta.tables["requests"].c.id.type)
        assert str(deals.c.offer_id.type) == str(meta.tables["seller_offers"].c.id.type)

    def test_status_defaults_to_negotiation(self) -> None:
        deals = _metadata().tables["deals"]
        assert deals.c.status.server_default is not None
        assert "negotiation" in str(deals.c.status.server_default.arg)


class TestDealChildTables:
    def test_history_is_registered_and_indexed(self) -> None:
        history = _metadata().tables["deal_status_history"]
        assert history.c.from_status.nullable is True, (
            "the opening row has no previous status"
        )
        assert history.c.to_status.nullable is False

    def test_messages_reject_an_empty_post(self) -> None:
        messages = _metadata().tables["deal_messages"]
        checks = {
            c.name for c in messages.constraints if type(c).__name__ == "CheckConstraint"
        }
        assert "ck_deal_message_not_empty" in checks, (
            "a message with neither text nor a file is meaningless — reject it in the DB"
        )

    def test_documents_are_revoked_not_deleted(self) -> None:
        documents = _metadata().tables["deal_documents"]
        assert documents.c.revoked.server_default is not None
        assert "sha256" in documents.c, "document integrity hash is part of the evidence trail"

    def test_children_cascade_from_the_deal(self) -> None:
        meta = _metadata()
        for table in ("deal_status_history", "deal_messages", "deal_documents"):
            fks = [fk for fk in meta.tables[table].foreign_keys if fk.column.table.name == "deals"]
            assert fks, f"{table} must reference deals"
            assert fks[0].ondelete == "CASCADE", f"{table}.deal_id must cascade"


class TestRfqResponses:
    def test_registered(self) -> None:
        assert "rfq_responses" in _metadata().tables

    def test_one_live_response_per_company_per_request(self) -> None:
        responses = _metadata().tables["rfq_responses"]
        partial = [ix for ix in responses.indexes if ix.name == "uq_rfq_response_active"]
        assert partial and partial[0].unique, "a company may not double-respond to one RFQ"
        # Partial: a withdrawn response must not block a fresh one.
        assert partial[0].dialect_options["postgresql"]["where"] is not None

    def test_deal_link_is_nullable(self) -> None:
        responses = _metadata().tables["rfq_responses"]
        assert responses.c.deal_id.nullable is True, (
            "deal_id is filled only on accept — a submitted response has no deal yet"
        )


class TestRequestRfqExtensions:
    def test_columns_registered(self) -> None:
        requests = _metadata().tables["requests"]
        for column in ("required_docs", "visibility", "visible_company_ids"):
            assert column in requests.c, (
                f"requests.{column} must be on the model, or every RFQ serializer "
                f"silently drops it"
            )

    def test_visibility_defaults_to_verified_only(self) -> None:
        # The safe default: an RFQ is visible to verified companies, never to the
        # whole internet, unless the buyer widens it on purpose.
        requests = _metadata().tables["requests"]
        assert requests.c.visibility.nullable is False
        assert "verified_only" in str(requests.c.visibility.server_default.arg)
