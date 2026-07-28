"""
Laboratory badges, market filters and the P4 scoring hook (P6 W4 — T4.1/T4.2).

Two badges, deliberately different questions:

  * **"lab passport"** — a PDF is attached. Anyone can earn it by uploading one.
  * **"Laboratory Verified"** — a platform lab order finished. Only
    `lab_service.complete_with_result` sets it.

FR-L5 asks for both as SEPARATE filters, so a buyer who only trusts an
independent analysis can say so. The passport filter is an EXISTS over the files
rather than a cached column: the catalog query already loads them, and a second
source of truth would be one a file deletion had to remember to update.

The scoring hook is the other half: P4 shipped `W_LAB_PASSPORT` wired but inert
(`has_lab_passport` defaulted False) so that P6 landing would not silently
re-rank everyone. This is where it starts counting.

Run with a localhost test_polymer DB; skipped otherwise (see _verification_db).
"""

from __future__ import annotations

import datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_request,
    make_seller_offer,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

pytestmark = requires_real_db


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def db(engine: sa.Engine) -> Session:
    clean(engine)
    session = session_factory(engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _passport(db: Session, offer) -> None:  # noqa: ANN001
    from app.models.enums import OfferFileKind  # noqa: PLC0415
    from app.models.marketplace import SellerOfferFile  # noqa: PLC0415

    db.add(
        SellerOfferFile(
            offer_id=offer.id, kind=OfferFileKind.lab_passport, file_name="p.pdf"
        )
    )
    db.flush()


def _three_offers(db: Session):  # noqa: ANN202
    """One plain offer, one with a self-uploaded passport, one verified by us."""
    owner = make_account(db, "+998900000601")
    company = make_company(db, owner, tax_id="300000601")
    plain = make_seller_offer(db, company=company, product_text="PP plain")
    with_passport = make_seller_offer(db, company=company, product_text="PP passport")
    verified = make_seller_offer(db, company=company, product_text="PP verified")

    _passport(db, with_passport)
    _passport(db, verified)
    verified.lab_verified = True
    db.flush()
    return plain, with_passport, verified


class TestFilters:
    def test_unfiltered_returns_everything(self, db: Session) -> None:
        from app.services import offer_service  # noqa: PLC0415

        _three_offers(db)
        assert len(offer_service.list_catalog(db)) == 3

    def test_the_passport_filter_finds_both_kinds(self, db: Session) -> None:
        """Independently verified material has a passport too — the narrower
        filter must not hide it from the broader one."""
        from app.services import offer_service  # noqa: PLC0415

        _plain, with_passport, verified = _three_offers(db)
        found = offer_service.list_catalog(db, has_lab_passport=True)
        assert {o.id for o in found} == {with_passport.id, verified.id}

    def test_the_verified_filter_is_narrower(self, db: Session) -> None:
        from app.services import offer_service  # noqa: PLC0415

        _plain, _with_passport, verified = _three_offers(db)
        found = offer_service.list_catalog(db, lab_verified=True)
        assert {o.id for o in found} == {verified.id}

    def test_false_is_not_a_filter(self, db: Session) -> None:
        """`False` from an unchecked checkbox must mean "don't filter", not
        "show me offers WITHOUT a passport" — otherwise unticking the box empties
        the market."""
        from app.services import offer_service  # noqa: PLC0415

        _three_offers(db)
        assert len(offer_service.list_catalog(db, has_lab_passport=False)) == 3
        assert len(offer_service.list_catalog(db, lab_verified=False)) == 3

    def test_the_filters_compose_with_the_others(self, db: Session) -> None:
        from app.services import offer_service  # noqa: PLC0415

        _plain, with_passport, _verified = _three_offers(db)
        found = offer_service.list_catalog(db, q="passport", has_lab_passport=True)
        assert [o.id for o in found] == [with_passport.id]

    def test_a_deleted_passport_leaves_the_filter(self, db: Session) -> None:
        """The reason there is no cached column: this is the update a cache would
        have to remember to make."""
        from app.models.marketplace import SellerOfferFile  # noqa: PLC0415
        from app.services import offer_service  # noqa: PLC0415

        _plain, with_passport, _verified = _three_offers(db)
        file_row = (
            db.query(SellerOfferFile)
            .filter(SellerOfferFile.offer_id == with_passport.id)
            .one()
        )
        db.delete(file_row)
        db.flush()

        found = offer_service.list_catalog(db, has_lab_passport=True)
        assert with_passport.id not in {o.id for o in found}


class TestCardFields:
    def test_the_card_carries_both_flags(self, db: Session) -> None:
        from app.schemas.portal_market import PortalMarketOfferOut  # noqa: PLC0415

        plain, with_passport, verified = _three_offers(db)
        cards = {
            o.id: PortalMarketOfferOut.model_validate(o)
            for o in (plain, with_passport, verified)
        }
        assert (cards[plain.id].has_lab_passport, cards[plain.id].lab_verified) == (
            False,
            False,
        )
        assert (
            cards[with_passport.id].has_lab_passport,
            cards[with_passport.id].lab_verified,
        ) == (True, False)
        assert (cards[verified.id].has_lab_passport, cards[verified.id].lab_verified) == (
            True,
            True,
        )

    def test_the_sample_terms_are_on_the_card(self, db: Session) -> None:
        import decimal  # noqa: PLC0415

        from app.schemas.portal_market import PortalMarketOfferOut  # noqa: PLC0415

        owner = make_account(db, "+998900000602")
        company = make_company(db, owner, tax_id="300000602")
        offer = make_seller_offer(
            db,
            company=company,
            samples_available=True,
            sample_price=decimal.Decimal("15.00"),
            sample_dispatch_days=3,
        )
        card = PortalMarketOfferOut.model_validate(offer)
        assert card.samples_available is True
        assert card.sample_dispatch_days == 3

    def test_the_mini_app_card_is_untouched(self, db: Session) -> None:
        """`webapp/` is frozen: the shared `CatalogOfferOut` must not grow P6
        fields, exactly as P4 decided for its badges."""
        from app.schemas.marketplace import CatalogOfferOut  # noqa: PLC0415

        for field in (
            "has_lab_passport",
            "lab_verified",
            "samples_available",
            "sample_price",
        ):
            assert field not in CatalogOfferOut.model_fields


class TestSupplierScoringHook:
    """P4 shipped the weight inert so that P6 landing would not silently re-rank
    everyone. It counts from here — by PASSPORT, not by `lab_verified`: that is
    what the weight is called, and a buyer cares that an analysis exists, not who
    paid for it."""

    def _supplier(self, db: Session, phone: str, tax: str, *, passport: bool):  # noqa: ANN202
        from app.models.enums import CompanyStatus  # noqa: PLC0415

        owner = make_account(db, phone)
        company = make_company(db, owner, tax_id=tax)
        company.status = CompanyStatus.verified
        offer = make_seller_offer(
            db, company=company, product_text="HDPE film", polymer_type="HDPE"
        )
        offer.published_at = datetime.datetime.now(datetime.UTC)
        if passport:
            _passport(db, offer)
        db.flush()
        return company

    def test_a_supplier_with_a_passport_outranks_an_identical_one_without(
        self, db: Session
    ) -> None:
        from app.services import supplier_matching_service  # noqa: PLC0415

        buyer_owner = make_account(db, "+998900000610")
        buyer = make_company(db, buyer_owner, tax_id="300000610")
        without = self._supplier(db, "+998900000611", "300000611", passport=False)
        with_passport = self._supplier(db, "+998900000612", "300000612", passport=True)
        rfq = make_request(db, company=buyer, account=buyer_owner, product_text="HDPE film")
        db.flush()

        ranked = supplier_matching_service.match_suppliers(db, rfq)
        by_company = {c.company_id: c for c in ranked}
        assert by_company[with_passport.id].score > by_company[without.id].score
        assert by_company[with_passport.id].rank < by_company[without.id].rank

    def test_the_bonus_is_the_declared_weight(self, db: Session) -> None:
        from app.services import supplier_matching_service  # noqa: PLC0415

        buyer_owner = make_account(db, "+998900000620")
        buyer = make_company(db, buyer_owner, tax_id="300000620")
        without = self._supplier(db, "+998900000621", "300000621", passport=False)
        with_passport = self._supplier(db, "+998900000622", "300000622", passport=True)
        rfq = make_request(db, company=buyer, account=buyer_owner, product_text="HDPE film")
        db.flush()

        by_company = {
            c.company_id: c for c in supplier_matching_service.match_suppliers(db, rfq)
        }
        delta = by_company[with_passport.id].score - by_company[without.id].score
        assert delta == supplier_matching_service.W_LAB_PASSPORT

    def test_lab_verified_alone_does_not_score(self, db: Session) -> None:
        """A `lab_verified` offer always has a passport, so there is nothing to
        add on top — the weight is counted once, for the analysis."""
        from app.services import supplier_matching_service  # noqa: PLC0415

        buyer_owner = make_account(db, "+998900000630")
        buyer = make_company(db, buyer_owner, tax_id="300000630")
        plain = self._supplier(db, "+998900000631", "300000631", passport=True)
        verified = self._supplier(db, "+998900000632", "300000632", passport=True)
        from app.models.marketplace import SellerOffer  # noqa: PLC0415

        db.query(SellerOffer).filter(SellerOffer.company_id == verified.id).update(
            {"lab_verified": True}
        )
        rfq = make_request(db, company=buyer, account=buyer_owner, product_text="HDPE film")
        db.flush()

        by_company = {
            c.company_id: c for c in supplier_matching_service.match_suppliers(db, rfq)
        }
        assert by_company[plain.id].score == by_company[verified.id].score
