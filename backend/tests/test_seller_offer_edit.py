"""
Tests for seller offer self-management (product editing):
  - offer_service.update_offer: full-replacement of fields; editing a public (approved)
    or rejected offer re-enters moderation (re-review policy), draft/pending stay in place.
  - offer_service.seller_id_for: cheap owner lookup, None without a Telegram id.

The API layer (GET/PATCH /webapp/seller/offers/{id}) and the catalog own-exclusion /
is_own flag are covered in test_marketplace_api.py.
"""

from __future__ import annotations

import decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _update_body(**overrides: object) -> object:
    from app.schemas.marketplace import SellerOfferUpdate  # noqa: PLC0415

    base: dict[str, object] = {
        "product_id": 2,
        "qty_available": decimal.Decimal("150"),
        "price": decimal.Decimal("1300"),
    }
    base.update(overrides)
    return SellerOfferUpdate(**base)  # type: ignore[arg-type]


def _offer(status: object) -> SimpleNamespace:
    from app.models.enums import OfferAvailability, PriceBasis  # noqa: PLC0415

    return SimpleNamespace(
        id=11,
        seller_id=7,
        status=status,
        product_id=1,
        product_text=None,
        grade_text="old grade",
        polymer_type=None,
        availability=OfferAvailability.in_stock,
        qty_available=decimal.Decimal("100"),
        qty_unit="MT",
        price=decimal.Decimal("1200"),
        currency="USD",
        incoterms=PriceBasis.FCA,
        warehouse_city="Tashkent",
        country="UZ",
        min_order_qty=None,
        description=None,
        published_at="set",
        moderated_by=3,
        moderation_note="prev note",
    )


def test_update_offer_approved_reenters_moderation() -> None:
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.services import offer_service as svc  # noqa: PLC0415

    offer = _offer(SellerOfferStatus.approved)
    db = MagicMock()
    with patch("app.services.offer_service.write_audit") as audit:
        result, requeued = svc.update_offer(db, offer, _update_body(grade_text="new grade"))

    assert result is offer
    assert requeued is True
    assert offer.status == SellerOfferStatus.pending_moderation
    assert offer.published_at is None  # no longer public
    assert offer.moderated_by is None
    assert offer.moderation_note is None
    # full-replacement applied
    assert offer.grade_text == "new grade"
    assert offer.price == decimal.Decimal("1300")
    assert offer.product_id == 2
    audit.assert_called_once()
    _, kwargs = audit.call_args
    assert kwargs["action"] == "offer.edit"
    assert kwargs["details"]["via"] == "seller"
    assert kwargs["details"]["requeued"] is True


def test_update_offer_draft_stays_in_place() -> None:
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.services import offer_service as svc  # noqa: PLC0415

    offer = _offer(SellerOfferStatus.draft)
    with patch("app.services.offer_service.write_audit"):
        _, requeued = svc.update_offer(MagicMock(), offer, _update_body())

    assert requeued is False
    assert offer.status == SellerOfferStatus.draft
    assert offer.published_at == "set"  # untouched
    assert offer.moderation_note == "prev note"


def test_update_offer_pending_stays_pending() -> None:
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.services import offer_service as svc  # noqa: PLC0415

    offer = _offer(SellerOfferStatus.pending_moderation)
    with patch("app.services.offer_service.write_audit"):
        _, requeued = svc.update_offer(MagicMock(), offer, _update_body())

    assert requeued is False
    assert offer.status == SellerOfferStatus.pending_moderation


def test_update_offer_rejected_reenters_moderation() -> None:
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.services import offer_service as svc  # noqa: PLC0415

    offer = _offer(SellerOfferStatus.rejected)
    with patch("app.services.offer_service.write_audit"):
        _, requeued = svc.update_offer(MagicMock(), offer, _update_body())

    assert requeued is True
    assert offer.status == SellerOfferStatus.pending_moderation
    assert offer.moderation_note is None  # the old rejection note is cleared


def test_seller_id_for_none_without_telegram_id() -> None:
    from app.services import offer_service as svc  # noqa: PLC0415

    assert svc.seller_id_for(MagicMock(), None) is None
