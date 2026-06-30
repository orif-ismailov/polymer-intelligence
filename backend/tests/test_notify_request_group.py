"""
Tests for send_request_to_group — posts a new buyer request to the team group.

Covers: skipped when REQUEST_NOTIFY_CHAT_ID unset; sends a formatted message to the
chat id when set; missing request → error dict (never raises).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


def _make_request() -> MagicMock:
    req = MagicMock()
    req.id = 42
    req.number = "REQ-2026-06-29-00007"
    req.product_id = None  # → uses product_text, single session.get
    req.product_text = "EVA"
    req.grade_text = "Grade A"
    req.volume = 100
    req.volume_unit = "MT"
    req.target_price = 1200
    req.currency = "USD"
    req.port_or_city = "Ташкент"
    req.urgency = MagicMock(value="high")
    req.company_name = "Acme LLC"
    req.contact_name = "Ivan"
    req.phone = "+998 90 123 45 67"
    req.comment = "ASAP"
    return req


def test_skipped_when_chat_id_unset():
    from app.core.config import settings  # noqa: PLC0415

    with patch.object(settings, "REQUEST_NOTIFY_CHAT_ID", None):
        from app.tasks.notify import send_request_to_group  # noqa: PLC0415

        result = send_request_to_group(request_id=42)
    assert result["status"] == "skipped"


def test_sends_formatted_message_to_chat():
    sent: list[dict[str, object]] = []

    async def _capture(chat_id: int, text: str, **kwargs: object) -> None:
        sent.append({"chat_id": chat_id, "text": text})

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
        mock_session.get.return_value = _make_request()
        mock_bot.send_message = _capture

        from app.tasks.notify import send_request_to_group  # noqa: PLC0415

        result = send_request_to_group(request_id=42)

    assert result == {"status": "ok", "error": None}
    assert len(sent) == 1
    assert sent[0]["chat_id"] == -1001234567890
    text = sent[0]["text"]
    assert "REQ-2026-06-29-00007" in text
    assert "EVA" in text
    assert "Срочно" in text  # urgency label
    assert "Acme LLC" in text


def test_missing_request_returns_error():
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
        mock_bot.send_message = AsyncMock(return_value=None)

        from app.tasks.notify import send_request_to_group  # noqa: PLC0415

        result = send_request_to_group(request_id=99999)

    assert result["status"] == "error"
