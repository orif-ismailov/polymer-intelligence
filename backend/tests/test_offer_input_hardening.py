"""Offer input hardening — audit findings IMEX-06 (stored markup) and IMEX-12 (negatives).

Both portal (`CompanyOfferIn`, create AND PATCH) and webapp (`SellerOfferCreate` /
`SellerOfferUpdate`) bodies are covered, because the audit's PoC went through the
portal while the webapp schema had its own gap (`min_order_qty`).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.text import reject_markup
from app.domains.companies.schemas import CompanyOfferIn
from app.domains.marketplace.schemas import SellerOfferCreate, SellerOfferUpdate
from tests._verification_db import make_engine, migrate_head, requires_real_db

_PAYLOADS = [
    "<script>alert(document.domain)</script>",
    '"><img src=x onerror=alert(1)>',
    "</b>",
    "<!-- x -->",
    "<svg/onload=alert(1)>",
    "<!DOCTYPE html>",
]

_PLAIN = ["MFI <2", "a < b > c", "PP H030 <-> PP H031", "<- see TDS", "Плотность < 0,95 г/см³"]


@pytest.mark.parametrize("value", _PAYLOADS)
def test_markup_is_refused(value: str) -> None:
    with pytest.raises(ValueError, match="HTML markup"):
        reject_markup(value)


@pytest.mark.parametrize("value", _PLAIN)
def test_comparisons_are_not_markup(value: str) -> None:
    """A polymer spec is full of `<`; refusing those would break real offers."""
    assert reject_markup(value) == value


def _webapp(**overrides: object) -> dict[str, object]:
    return {"product_text": "PP", "qty_available": "10", "price": "1000", **overrides}


@pytest.mark.parametrize("field", ["description", "grade_text", "product_text"])
@pytest.mark.parametrize("value", _PAYLOADS[:2])
def test_portal_offer_text_refuses_markup(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        CompanyOfferIn(**{field: value})


@pytest.mark.parametrize("field", ["description", "grade_text", "product_text", "company_name"])
@pytest.mark.parametrize("schema", [SellerOfferCreate, SellerOfferUpdate])
def test_webapp_offer_text_refuses_markup(field: str, schema: type[SellerOfferCreate]) -> None:
    with pytest.raises(ValidationError):
        schema(**_webapp(**{field: _PAYLOADS[1]}))


def test_portal_offer_chips_refuse_markup() -> None:
    with pytest.raises(ValidationError):
        CompanyOfferIn(key_properties=["UV-stable", "<b>bold</b>"])


def test_plain_offer_text_still_saves() -> None:
    offer = CompanyOfferIn(description="MFI <2, плотность 0,946", grade_text="PE100")
    assert offer.description == "MFI <2, плотность 0,946"


@pytest.mark.parametrize("field", ["price", "qty_available", "min_order_qty"])
@pytest.mark.parametrize("value", ["-500", "-10", "0"])
def test_portal_offer_numbers_must_be_positive(field: str, value: str) -> None:
    """The audit's PATCH {"price": -500, "qty_available": -10} was stored."""
    with pytest.raises(ValidationError):
        CompanyOfferIn(**{field: value})


def test_portal_offer_numbers_stay_below_the_column_ceiling() -> None:
    """Numeric(14, 2): a larger price is a DB error (500), so it is a 422 here."""
    with pytest.raises(ValidationError):
        CompanyOfferIn(price="1000000000000")


def test_portal_offer_currency_fits_its_column() -> None:
    with pytest.raises(ValidationError):
        CompanyOfferIn(currency="USDT")


@pytest.mark.parametrize("value", ["-1", "0"])
def test_webapp_min_order_qty_must_be_positive(value: str) -> None:
    with pytest.raises(ValidationError):
        SellerOfferCreate(**_webapp(min_order_qty=value))


def test_valid_numbers_still_pass() -> None:
    offer = CompanyOfferIn(price="1250.50", qty_available="20", min_order_qty="1")
    assert offer.price is not None and offer.price > 0


# ── The database refuses them too (migration 0057) ────────────────────────────


@requires_real_db
def test_offer_number_checks_exist_after_migration() -> None:
    import sqlalchemy as sa  # noqa: PLC0415

    migrate_head()
    engine = make_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'seller_offers'::regclass AND contype = 'c'"
            )
        ).scalars()
        names = set(rows)
    assert {
        "ck_offer_price_positive",
        "ck_offer_qty_positive",
        "ck_offer_min_order_positive",
        "ck_offer_sample_price_nonneg",
    } <= names
