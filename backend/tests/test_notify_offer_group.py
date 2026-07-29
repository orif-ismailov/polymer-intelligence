"""
Tests for send_offer_to_group — posts a new seller offer to the team group.

Covers: skipped when REQUEST_NOTIFY_CHAT_ID unset; sends a text message (with the
Confirm keyboard) when the offer has no image; sends a photo with caption when an
image is attached; missing offer → error dict (never raises).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def _make_offer(with_image: bool = False) -> MagicMock:
    offer = MagicMock()
    offer.id = 11
    offer.product_id = None  # → uses product_text, single session.get
    offer.product_text = "EVA"
    offer.grade_text = "Grade A"
    offer.polymer_type = "homopolymer"
    offer.qty_available = 100
    offer.qty_unit = "MT"
    offer.price = 1200
    offer.currency = "USD"
    offer.incoterms = SimpleNamespace(value="FCA")
    offer.min_order_qty = 20
    offer.warehouse_city = "Ташкент"
    offer.description = "Свежая партия"
    offer.company_id = None  # seller-origin (R1 W5 dual-origin branch)
    offer.seller = SimpleNamespace(
        company_name="Acme LLC",
        contact_name="Ivan",
        phone="+998 90 123 45 67",
        telegram_username="ivan_seller",
        telegram_user_id=555,
    )
    if with_image:
        from app.models.enums import OfferFileKind  # noqa: PLC0415

        img = SimpleNamespace(
            kind=OfferFileKind.image, storage_path="offers/11/abc-photo.jpg", file_name="photo.jpg"
        )
        offer.files = [img]
    else:
        offer.files = []
    return offer


def test_skipped_when_chat_id_unset() -> None:
    from app.core.config import settings  # noqa: PLC0415

    with patch.object(settings, "REQUEST_NOTIFY_CHAT_ID", None):
        from app.tasks.notify import send_offer_to_group  # noqa: PLC0415

        result = send_offer_to_group(offer_id=11)
    assert result["status"] == "skipped"


def test_sends_text_with_keyboard_when_no_image() -> None:
    sent: list[dict[str, object]] = []

    async def _capture(chat_id: int, text: str, **kwargs: object) -> None:
        sent.append({"chat_id": chat_id, "text": text, "reply_markup": kwargs.get("reply_markup")})

    from app.core.config import settings  # noqa: PLC0415

    with (
        patch.object(settings, "REQUEST_NOTIFY_CHAT_ID", -1001234567890),
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("telegram.bot.bot") as mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = _make_offer(with_image=False)
        mock_bot.send_message = _capture
        mock_bot.send_photo = AsyncMock()

        from app.tasks.notify import send_offer_to_group  # noqa: PLC0415

        result = send_offer_to_group(offer_id=11)

    assert result == {"status": "ok", "error": None}
    assert len(sent) == 1
    assert sent[0]["chat_id"] == -1001234567890
    text = sent[0]["text"]
    assert "EVA" in text
    assert "Acme LLC" in text
    assert "@ivan_seller" in text
    assert "1200 USD (FCA)" in text
    assert sent[0]["reply_markup"] is not None  # Confirm/Reject keyboard attached


def test_sends_photo_when_image_present() -> None:
    photos: list[dict[str, object]] = []

    async def _capture_photo(chat_id: int, photo: object, **kwargs: object) -> None:
        photos.append({"chat_id": chat_id, "caption": kwargs.get("caption")})

    from app.core.config import settings  # noqa: PLC0415

    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"\xff\xd8\xffdata"))}

    with (
        patch.object(settings, "REQUEST_NOTIFY_CHAT_ID", -100),
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("app.core.storage.s3_client", mock_s3),
        patch("telegram.bot.bot") as mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = _make_offer(with_image=True)
        mock_bot.send_photo = _capture_photo
        mock_bot.send_message = AsyncMock()

        from app.tasks.notify import send_offer_to_group  # noqa: PLC0415

        result = send_offer_to_group(offer_id=11)

    assert result == {"status": "ok", "error": None}
    assert len(photos) == 1
    assert photos[0]["chat_id"] == -100
    assert "EVA" in str(photos[0]["caption"])
    mock_s3.get_object.assert_called_once()


def test_edited_offer_uses_update_header() -> None:
    """A re-review after a seller edit (edited=True) frames the post as an update."""
    sent: list[str] = []

    async def _capture(chat_id: int, text: str, **kwargs: object) -> None:
        sent.append(text)

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
        mock_session.get.return_value = _make_offer(with_image=False)
        mock_bot.send_message = _capture
        mock_bot.send_photo = AsyncMock()

        from app.tasks.notify import send_offer_to_group  # noqa: PLC0415

        result = send_offer_to_group(offer_id=11, edited=True)

    assert result == {"status": "ok", "error": None}
    assert "Обновлённое предложение на модерацию" in sent[0]
    assert "EVA" in sent[0]  # still carries the full offer detail for re-review


def test_missing_offer_returns_error() -> None:
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
        mock_session.get.return_value = None
        mock_bot.send_message = AsyncMock()
        mock_bot.send_photo = AsyncMock()

        from app.tasks.notify import send_offer_to_group  # noqa: PLC0415

        result = send_offer_to_group(offer_id=99999)

    assert result["status"] == "error"
