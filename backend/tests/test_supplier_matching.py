"""
Supplier matching for RFQ push (P4 W3 — T3.1 + T3.2).

The scoring table is written BEFORE the service, and deliberately as plain
numbers rather than by importing the weights: a test that computes the expected
score from the same constants the code uses proves only that arithmetic works.

What the ranking has to get right is the ordering, not the absolute numbers — a
manufacturer with a weaker product match should still be able to outrank a
trader with a perfect one, because that is the judgement the multiplier encodes.

No LLM is involved. `request_analysis_service` turned out to have no structural
matcher (it only aggregates signals as context for its prompt), so per the plan
the candidate set is built in SQL here.

(`app.*` is imported inside the tests: the conftest env patch is a session
fixture and does not exist at collection time.)
"""

from __future__ import annotations

import decimal
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_request,
    make_seller,
    make_seller_offer,
    migrate_head,
    requires_real_db,
    session_factory,
)

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0026_rfq_push_log.py"


# ── migration (T3.1) ──────────────────────────────────────────────────────────


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0026", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _metadata():  # noqa: ANN202
    import app.models  # noqa: F401, PLC0415
    from app.core.db import Base  # noqa: PLC0415

    return Base.metadata


class TestMigration:
    def test_revision_chain(self) -> None:
        module = _load_migration()
        assert module.revision == "0026"
        assert module.down_revision == "0025"

    def test_is_in_a_single_head_chain(self) -> None:
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        heads = ScriptDirectory.from_config(cfg).get_heads()
        assert len(heads) == 1, (
            f"a second head means two migrations claim the same parent: {heads}"
        )

    def test_one_push_per_company_per_rfq(self) -> None:
        """FR-A2. This unique index IS the dedup: re-running the task inserts
        nothing rather than re-notifying a supplier who already heard."""
        table = _metadata().tables["rfq_push_log"]
        uniques = {
            tuple(c.name for c in con.columns)
            for con in table.constraints
            if type(con).__name__ == "UniqueConstraint"
        }
        unique_indexes = {
            tuple(c.name for c in ix.columns) for ix in table.indexes if ix.unique
        }
        assert ("request_id", "company_id") in uniques | unique_indexes

    def test_it_records_why_this_supplier_was_picked(self) -> None:
        """Staff read this to answer "why did we push this to them?" — without the
        score and rank the log is just a list of names."""
        table = _metadata().tables["rfq_push_log"]
        for column in ("score", "rank", "notified_at"):
            assert column in table.c, column
        assert "NUMERIC" in str(table.c.score.type).upper()


# ── scoring (T3.2), pure and table-driven ─────────────────────────────────────

#: (match_kind, verified, fresh_offer, roles) → expected score, spelled out.
#: base = product match + 0.2 verified + 0.1 fresh, then x the best role multiplier.
_CASES = [
    # A perfect product match from a verified manufacturer with a fresh offer:
    # (1.0 + 0.2 + 0.1) * 1.3
    ("product", True, True, ("manufacturer",), "1.69"),
    # Same, but a trader: no multiplier.
    ("product", True, True, ("trader",), "1.30"),
    # Distributor 1.2, importer 1.1.
    ("product", True, True, ("distributor",), "1.56"),
    ("product", True, True, ("importer",), "1.43"),
    # Polymer-type match only.
    ("type", True, True, ("manufacturer",), "1.17"),
    # Free-text match only, unverified, stale offer: the weakest candidate.
    ("text", False, False, (), "0.40"),
    # Roles that say nothing about supply do not lift the score.
    ("product", True, True, ("laboratory", "logistics_provider"), "1.30"),
    # The BEST role wins when a company holds several.
    ("product", True, True, ("trader", "manufacturer"), "1.69"),
    # No role at all behaves like a trader.
    ("product", True, True, (), "1.30"),
]


@pytest.mark.parametrize(("kind", "verified", "fresh", "roles", "expected"), _CASES)
def test_score_table(kind, verified, fresh, roles, expected) -> None:  # noqa: ANN001
    from app.services.supplier_matching_service import score_candidate  # noqa: PLC0415

    got = score_candidate(
        match_kind=kind, verified=verified, fresh_offer=fresh, roles=roles
    )
    assert got == decimal.Decimal(expected), f"{kind}/{roles}: got {got}"


def test_a_manufacturer_can_outrank_a_trader_with_a_better_match() -> None:
    """The whole point of the role multiplier: who you are can beat what you
    listed. A manufacturer matching on polymer type outranks a trader matching
    the exact product — a buyer would rather hear from the plant."""
    from app.services.supplier_matching_service import score_candidate  # noqa: PLC0415

    plant = score_candidate(
        match_kind="type", verified=True, fresh_offer=True, roles=("manufacturer",)
    )
    reseller = score_candidate(
        match_kind="text", verified=True, fresh_offer=True, roles=("trader",)
    )
    assert plant > reseller


def test_the_lab_passport_term_is_wired_but_inert_until_p6() -> None:
    """P6 adds lab passports. The weight exists so the ranking does not need
    re-deriving then, but it must contribute NOTHING today — otherwise every
    score silently shifts when P6 lands."""
    from app.services import supplier_matching_service as matching  # noqa: PLC0415

    assert matching.W_LAB_PASSPORT > 0
    with_flag = matching.score_candidate(
        match_kind="product", verified=True, fresh_offer=True, roles=(),
        has_lab_passport=True,
    )
    without = matching.score_candidate(
        match_kind="product", verified=True, fresh_offer=True, roles=()
    )
    assert with_flag > without, "the term must work when P6 starts setting it"
    assert without == decimal.Decimal("1.30"), "and default to off today"


# ── candidate selection (real DB) ─────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


def _supplier(db, tax, phone, *, roles=(), verified=True, **offer_kw):  # noqa: ANN001, ANN003, ANN202
    from app.core.time import utcnow  # noqa: PLC0415
    from app.models.companies import CompanyBusinessRole  # noqa: PLC0415
    from app.models.enums import (  # noqa: PLC0415
        BusinessRoleStatus,
        CompanyStatus,
        SellerOfferStatus,
    )

    account = make_account(db, phone)
    company = make_company(db, account, tax_id=tax)
    company.status = CompanyStatus.verified if verified else CompanyStatus.draft
    company.legal_name = f"OOO {tax}"
    db.flush()
    for role in roles:
        db.add(
            CompanyBusinessRole(
                company_id=company.id, role=role, status=BusinessRoleStatus.confirmed
            )
        )
    offer = make_seller_offer(
        db, company=company, status=SellerOfferStatus.approved, **offer_kw
    )
    offer.published_at = offer_kw.pop("published_at", None) or utcnow()
    db.flush()
    return company, offer


@requires_real_db
def test_matches_by_product_text_and_ranks_by_role(sf) -> None:  # noqa: ANN001
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415
    from app.services import supplier_matching_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc = make_account(db, "+998900000001")
        buyer = make_company(db, buyer_acc, tax_id="301111111")
        request = make_request(
            db, company=buyer, account=buyer_acc, product_text="HDPE film"
        )
        _supplier(db, "302222222", "+998900000002", roles=(Role.trader,))
        _supplier(db, "303333333", "+998900000003", roles=(Role.manufacturer,))
        db.commit()

        matches = supplier_matching_service.match_suppliers(db, request)

        assert [m.rank for m in matches] == [1, 2]
        assert matches[0].score > matches[1].score
        top = db.get(type(buyer), matches[0].company_id)
        assert top is not None and top.tax_id == "303333333", (
            "the manufacturer must come first"
        )


@requires_real_db
def test_the_rfq_author_is_never_matched(sf) -> None:  # noqa: ANN001
    """A company must not be pushed its own RFQ."""
    from app.services import supplier_matching_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc = make_account(db, "+998900000001")
        buyer = make_company(db, buyer_acc, tax_id="301111111")
        from app.models.enums import CompanyStatus, SellerOfferStatus  # noqa: PLC0415

        buyer.status = CompanyStatus.verified
        db.flush()
        make_seller_offer(db, company=buyer, status=SellerOfferStatus.approved)
        request = make_request(db, company=buyer, account=buyer_acc, product_text="HDPE film")
        db.commit()

        assert supplier_matching_service.match_suppliers(db, request) == []


@requires_real_db
def test_unverified_companies_and_tg_sellers_are_not_candidates(sf) -> None:  # noqa: ANN001
    """The push says "a buyer wants what you sell" — it must only go to companies
    the platform has actually verified, and a Telegram seller has no portal
    account to notify at all."""
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.services import supplier_matching_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc = make_account(db, "+998900000001")
        buyer = make_company(db, buyer_acc, tax_id="301111111")
        request = make_request(db, company=buyer, account=buyer_acc, product_text="HDPE film")
        _supplier(db, "302222222", "+998900000002", verified=False)
        seller = make_seller(db, telegram_user_id=999001)
        make_seller_offer(db, seller=seller, status=SellerOfferStatus.approved)
        db.commit()

        assert supplier_matching_service.match_suppliers(db, request) == []


@requires_real_db
def test_a_stale_offer_drops_out_of_the_candidate_set(sf) -> None:  # noqa: ANN001
    """A listing from two years ago is not evidence that anyone still sells it."""
    import datetime  # noqa: PLC0415

    from app.core.time import utcnow  # noqa: PLC0415
    from app.services import supplier_matching_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc = make_account(db, "+998900000001")
        buyer = make_company(db, buyer_acc, tax_id="301111111")
        request = make_request(db, company=buyer, account=buyer_acc, product_text="HDPE film")
        _company, offer = _supplier(db, "302222222", "+998900000002")
        offer.published_at = utcnow() - datetime.timedelta(days=400)
        db.commit()

        assert supplier_matching_service.match_suppliers(db, request) == []


@requires_real_db
def test_one_row_per_company_even_with_several_matching_offers(sf) -> None:  # noqa: ANN001
    """A supplier with five matching listings is still one supplier to notify."""
    from app.core.time import utcnow  # noqa: PLC0415
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.services import supplier_matching_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc = make_account(db, "+998900000001")
        buyer = make_company(db, buyer_acc, tax_id="301111111")
        request = make_request(db, company=buyer, account=buyer_acc, product_text="HDPE film")
        company, _offer = _supplier(db, "302222222", "+998900000002")
        for _ in range(4):
            extra = make_seller_offer(
                db, company=company, status=SellerOfferStatus.approved
            )
            extra.published_at = utcnow()
        db.commit()

        matches = supplier_matching_service.match_suppliers(db, request)
        assert [m.company_id for m in matches] == [company.id]


@requires_real_db
def test_a_request_with_nothing_to_match_on_returns_nothing(sf) -> None:  # noqa: ANN001
    """No product id, no polymer type, no text — matching everyone would be worse
    than matching no one."""
    from app.services import supplier_matching_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc = make_account(db, "+998900000001")
        buyer = make_company(db, buyer_acc, tax_id="301111111")
        request = make_request(db, company=buyer, account=buyer_acc, product_text=None)
        _supplier(db, "302222222", "+998900000002")
        db.commit()

        assert supplier_matching_service.match_suppliers(db, request) == []
