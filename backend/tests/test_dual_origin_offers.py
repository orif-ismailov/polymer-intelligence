"""Dual-origin offer serialization (R1 W5 — T5.3).

DB-free. The SellerOffer origin/display_name/company_verified properties, and that
adding them keeps a SELLER-origin catalog/moderation payload's pre-R1 fields intact
(the seller block still present) while a COMPANY-origin offer has seller=None + the
company display fields.
"""

from __future__ import annotations

import decimal


def _seller(company_name: str = "Chem Trade LLC", is_verified: bool = True):  # noqa: ANN202
    from app.models.marketplace import Seller  # noqa: PLC0415

    seller = Seller(company_name=company_name, is_verified=is_verified)
    seller.id = 5
    return seller


def _company(short_name=None, legal_name="OOO Long Name", status="verified"):  # noqa: ANN001, ANN202
    from app.models.companies import Company  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    company = Company(
        jurisdiction="UZ", tax_id="123456789",
        short_name=short_name, legal_name=legal_name, status=CompanyStatus(status),
    )
    company.id = 9
    return company


def _offer(**kw):  # noqa: ANN003, ANN202
    from app.models.enums import OfferAvailability, PriceBasis, SellerOfferStatus  # noqa: PLC0415
    from app.models.marketplace import SellerOffer  # noqa: PLC0415

    offer = SellerOffer(
        product_id=2, grade_text="HDPE 5502", availability=OfferAvailability.in_stock,
        qty_available=decimal.Decimal("100"), qty_unit="MT", price=decimal.Decimal("1200"),
        currency="USD", incoterms=PriceBasis.unknown, status=SellerOfferStatus.approved,
    )
    offer.id = 11
    for key, value in kw.items():
        setattr(offer, key, value)
    return offer


# ── properties ────────────────────────────────────────────────────────────────


def test_seller_origin_properties() -> None:
    offer = _offer(seller_id=5, seller=_seller(), company_id=None, company=None)
    assert offer.origin == "seller"
    assert offer.display_name == "Chem Trade LLC"
    assert offer.company_verified is False


def test_company_origin_prefers_short_name_then_legal() -> None:
    offer = _offer(company_id=9, company=_company(short_name="ShortCo"), seller_id=None, seller=None)
    assert offer.origin == "company"
    assert offer.display_name == "ShortCo"
    assert offer.company_verified is True

    offer2 = _offer(company_id=9, company=_company(short_name=None, legal_name="OOO Long Name"))
    assert offer2.display_name == "OOO Long Name"


def test_company_origin_unverified_badge_is_false() -> None:
    offer = _offer(company_id=9, company=_company(status="suspended"), seller_id=None, seller=None)
    assert offer.company_verified is False


# ── serialization ─────────────────────────────────────────────────────────────


def test_catalog_seller_origin_keeps_seller_block_and_adds_fields() -> None:
    from app.schemas.marketplace import CatalogOfferOut  # noqa: PLC0415

    offer = _offer(seller_id=5, seller=_seller(), company_id=None, company=None)
    out = CatalogOfferOut.model_validate(offer).model_dump()

    # pre-R1 fields intact
    assert out["id"] == 11
    assert out["grade_text"] == "HDPE 5502"
    assert out["seller"] == {"company_name": "Chem Trade LLC", "is_verified": True}
    # new dual-origin fields, seller-origin values
    assert out["origin"] == "seller"
    assert out["display_name"] == "Chem Trade LLC"
    assert out["company_verified"] is False


def test_catalog_company_origin_has_no_seller_block() -> None:
    from app.schemas.marketplace import CatalogOfferOut  # noqa: PLC0415

    offer = _offer(company_id=9, company=_company(short_name="ShortCo"), seller_id=None, seller=None)
    out = CatalogOfferOut.model_validate(offer).model_dump()

    assert out["seller"] is None
    assert out["origin"] == "company"
    assert out["display_name"] == "ShortCo"
    assert out["company_verified"] is True


def test_moderation_serialization_dual_origin() -> None:
    from app.schemas.marketplace import ModerationOfferOut  # noqa: PLC0415

    seller_offer = _offer(seller_id=5, seller=_seller(), company_id=None, company=None)
    seller_offer.created_at = __import__("datetime").datetime(2026, 1, 1)
    sm = ModerationOfferOut.model_validate(seller_offer).model_dump()
    assert sm["seller"]["company_name"] == "Chem Trade LLC"
    assert sm["origin"] == "seller"

    company_offer = _offer(company_id=9, company=_company(short_name="ShortCo"), seller_id=None, seller=None)
    company_offer.created_at = __import__("datetime").datetime(2026, 1, 1)
    cm = ModerationOfferOut.model_validate(company_offer).model_dump()
    assert cm["seller"] is None
    assert cm["display_name"] == "ShortCo"
    assert cm["company_verified"] is True
