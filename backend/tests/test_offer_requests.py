"""
Tests for the "Request an offer" admin-gated brokerage flow.

Layers:
  - OfferRequestCreate schema validation (must carry a quantity or a message).
  - offer_request_service.create_offer_request (only against approved offers).
  - offer_request_service.moderate_offer_request approve/reject + audit.
  - telegram handler _apply_offer_request_moderation idempotency.
  - notify tasks: group review post + seller DM (buyer contact WITHHELD).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Schema validation ─────────────────────────────────────────────────────────


def test_offer_request_create_requires_qty_or_message() -> None:
    from pydantic import ValidationError  # noqa: PLC0415

    from app.schemas.marketplace import OfferRequestCreate  # noqa: PLC0415

    with pytest.raises(ValidationError):
        OfferRequestCreate()  # neither quantity nor message

    # A message alone is fine
    assert OfferRequestCreate(message="Интересует, перезвоните").quantity is None
    # A quantity alone is fine
    assert OfferRequestCreate(quantity=50).qty_unit == "MT"


# ── Service ───────────────────────────────────────────────────────────────────


def test_create_offer_request_rejects_non_approved_offer() -> None:
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.schemas.marketplace import OfferRequestCreate  # noqa: PLC0415
    from app.services import offer_request_service  # noqa: PLC0415

    db = MagicMock()
    # pending offer → not public → ValueError
    offer = SimpleNamespace(id=5, status=SellerOfferStatus.pending_moderation)
    db.query.return_value.filter.return_value.first.return_value = offer
    client = SimpleNamespace(id=1)

    with pytest.raises(ValueError, match="Offer not found"):
        offer_request_service.create_offer_request(
            db, client, 5, OfferRequestCreate(quantity=10)
        )


def test_moderate_offer_request_approve_sets_forwarded_and_audits() -> None:
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415
    from app.services import offer_request_service  # noqa: PLC0415

    req = MagicMock()
    db = MagicMock()
    with patch("app.services.offer_request_service.write_audit") as mock_audit:
        offer_request_service.moderate_offer_request(db, req, 3, approve=True, note=None)

    assert req.status == OfferRequestStatus.approved
    assert req.reviewed_at is not None
    assert req.forwarded_at is not None
    assert req.moderated_by == 3
    _, kwargs = mock_audit.call_args
    assert kwargs["action"] == "offer_request.approve"


def test_moderate_offer_request_reject_no_forward() -> None:
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415
    from app.services import offer_request_service  # noqa: PLC0415

    req = MagicMock()
    req.forwarded_at = None
    db = MagicMock()
    with patch("app.services.offer_request_service.write_audit"):
        offer_request_service.moderate_offer_request(db, req, 3, approve=False, note="dup")

    assert req.status == OfferRequestStatus.rejected
    assert req.forwarded_at is None
    assert req.moderation_note == "dup"


# ── Telegram handler idempotency ──────────────────────────────────────────────


def _run_apply(status_value: object) -> dict[str, object]:
    from telegram.handlers import moderation  # noqa: PLC0415

    req = MagicMock()
    req.status = status_value
    with (
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("app.services.offer_request_service.moderate_offer_request_via_telegram") as mock_mod,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = None if status_value is None else req
        out = moderation._apply_offer_request_moderation(7, 555, approve=True)
        out["_mod_called"] = mock_mod.called
    return out


def test_apply_offer_request_pending_applies() -> None:
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415

    out = _run_apply(OfferRequestStatus.pending)
    assert out["ok"] is True
    assert out["_mod_called"] is True


def test_apply_offer_request_already_is_idempotent() -> None:
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415

    out = _run_apply(OfferRequestStatus.approved)
    assert out["ok"] is False
    assert out["reason"] == "already"
    assert out["_mod_called"] is False


def test_apply_offer_request_missing() -> None:
    out = _run_apply(None)
    assert out["ok"] is False
    assert out["reason"] == "not_found"


# ── Notify tasks ──────────────────────────────────────────────────────────────


def _make_offer_request() -> MagicMock:
    req = MagicMock()
    req.id = 7
    req.quantity = 50
    req.qty_unit = "MT"
    req.target_price = 1150
    req.currency = "USD"
    req.message = "Нужно срочно"
    req.offer = SimpleNamespace(
        product_id=None,
        product_text="EVA",
        grade_text="Grade A",
        price=1200,
        currency="USD",
        seller=SimpleNamespace(telegram_user_id=999, company_name="Seller LLC"),
    )
    req.client = SimpleNamespace(
        company_name="Buyer LLC", contact_name="Пётр", phone="+998 90 000 00 00", telegram_user_id=555
    )
    return req


def test_send_offer_request_to_group_skipped_when_unset() -> None:
    from app.core.config import settings  # noqa: PLC0415

    with patch.object(settings, "REQUEST_NOTIFY_CHAT_ID", None):
        from app.tasks.notify import send_offer_request_to_group  # noqa: PLC0415

        assert send_offer_request_to_group(offer_request_id=7)["status"] == "skipped"


def test_send_offer_request_to_group_includes_buyer_and_keyboard() -> None:
    sent: list[dict[str, object]] = []

    async def _capture(chat_id: int, text: str, **kwargs: object) -> None:
        sent.append({"chat_id": chat_id, "text": text, "reply_markup": kwargs.get("reply_markup")})

    from app.core.config import settings  # noqa: PLC0415

    with (
        patch.object(settings, "REQUEST_NOTIFY_CHAT_ID", -100),
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("telegram.bot.bot") as mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = _make_offer_request()
        mock_bot.send_message = _capture

        from app.tasks.notify import send_offer_request_to_group  # noqa: PLC0415

        result = send_offer_request_to_group(offer_request_id=7)

    assert result == {"status": "ok", "error": None}
    text = str(sent[0]["text"])
    assert "EVA" in text
    assert "Buyer LLC" in text  # admin sees buyer contact
    assert "Пётр" in text
    assert sent[0]["reply_markup"] is not None  # approve/reject keyboard


def test_send_offer_request_to_seller_withholds_buyer_contact() -> None:
    sent: list[dict[str, object]] = []

    async def _capture(chat_id: int, text: str, **kwargs: object) -> None:
        sent.append({"chat_id": chat_id, "text": text})

    with (
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("telegram.bot.bot") as mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = _make_offer_request()
        mock_bot.send_message = _capture

        from app.tasks.notify import send_offer_request_to_seller  # noqa: PLC0415

        result = send_offer_request_to_seller(offer_request_id=7)

    assert result == {"status": "ok", "error": None}
    assert sent[0]["chat_id"] == 999  # seller's telegram id
    text = str(sent[0]["text"])
    assert "EVA" in text
    # 3B: buyer contact must NOT leak to the seller
    assert "Buyer LLC" not in text
    assert "Пётр" not in text
    assert "+998 90 000 00 00" not in text


def test_send_offer_request_to_seller_skipped_without_seller_tg() -> None:
    req = _make_offer_request()
    req.offer = SimpleNamespace(
        product_id=None, product_text="EVA", grade_text=None, price=1200, currency="USD",
        seller=SimpleNamespace(telegram_user_id=None, company_name="X"),
    )

    with (
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("telegram.bot.bot") as mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = req
        mock_bot.send_message = AsyncMock()

        from app.tasks.notify import send_offer_request_to_seller  # noqa: PLC0415

        result = send_offer_request_to_seller(offer_request_id=7)

    assert result["status"] == "skipped"
