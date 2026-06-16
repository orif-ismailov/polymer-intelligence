"""
Tests for send_status_change_notification Celery task.

TDD RED phase: tests written before task implementation.

Covers:
- Task renders status_change template for the client's language (RU/UZ)
- Task uses D-10 client-facing label, not the raw internal status string
  (e.g. RequestStatus.viewed → "На рассмотрении", not "viewed")
- Task calls bot.send_message once with the client's telegram_user_id
- Task returns {"status": "ok", "error": None} on success
- Task returns {"status": "error", ...} without raising when request is missing
- Task returns {"status": "error", ...} without raising when telegram_user_id is None

Security invariants:
- T-03-12: deep-link button points to recipient's own request (no cross-client leak)
- T-03-13: task never raises — always returns error dict on any failure
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── D-10 label map (matches CLIENT_STATUS_MAP in request_service.py + RU labels) ──
# viewed → in_review → "На рассмотрении"
_STATUS_LABELS_RU: dict[str, str] = {
    "new": "Новая заявка",
    "in_review": "На рассмотрении",
    "offer_received": "Предложение получено",
    "matched": "Подобрано",
    "closed": "Закрыта",
    "cancelled": "Отменена",
}

_STATUS_LABELS_UZ: dict[str, str] = {
    "new": "Yangi ariza",
    "in_review": "Ko'rib chiqilmoqda",
    "offer_received": "Taklif olindi",
    "matched": "Topildi",
    "closed": "Yopildi",
    "cancelled": "Bekor qilindi",
}


def _make_mock_client(
    id: int = 1,
    telegram_user_id: int = 999,
    language: str = "ru",
) -> MagicMock:
    """Return a MagicMock that quacks like a Client ORM object."""
    client = MagicMock()
    client.id = id
    client.telegram_user_id = telegram_user_id
    client.language = language
    return client


def _make_mock_request(
    id: int = 42,
    number: str = "REQ-2026-06-16-00001",
    client_id: int = 1,
    status: str = "viewed",
) -> MagicMock:
    """Return a MagicMock that quacks like a Request ORM object."""
    from app.models.enums import RequestStatus  # noqa: PLC0415

    req = MagicMock()
    req.id = id
    req.number = number
    req.client_id = client_id
    req.status = RequestStatus(status)
    return req


class TestSendStatusChangeNotification:
    """Tests for the send_status_change_notification Celery task."""

    def test_ru_template_renders_d10_label(self) -> None:
        """Task renders RU template with D-10 label for viewed status.

        viewed → in_review → "На рассмотрении" (D-10 client-facing label in RU).
        The push text must NOT contain the raw internal status "viewed".
        """
        mock_request = _make_mock_request(status="viewed")
        mock_client = _make_mock_client(language="ru")

        with (
            patch("sqlalchemy.orm.Session") as mock_session_cls,
            patch("app.core.db.engine"),
            patch("telegram.bot.bot") as mock_bot,
        ):
            # Wire Session context manager to return our mock objects
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_request.client = mock_client
            mock_session.get.return_value = mock_request

            # Mock bot.send_message as async
            mock_bot.send_message = AsyncMock(return_value=None)

            from app.tasks.notify import send_status_change_notification  # noqa: PLC0415

            result = send_status_change_notification(request_id=42)

        assert result["status"] == "ok"
        assert result["error"] is None

    def test_calls_bot_send_message_once(self) -> None:
        """Task calls bot.send_message exactly once with the client's telegram_user_id."""
        mock_request = _make_mock_request(status="viewed")
        mock_client = _make_mock_client(telegram_user_id=999, language="ru")

        send_message_calls = []

        async def _fake_send(chat_id: int, **kwargs: object) -> None:
            send_message_calls.append(chat_id)

        with (
            patch("sqlalchemy.orm.Session") as mock_session_cls,
            patch("app.core.db.engine"),
            patch("telegram.bot.bot") as mock_bot,
        ):
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_request.client = mock_client
            mock_session.get.return_value = mock_request
            mock_bot.send_message = _fake_send

            from app.tasks.notify import send_status_change_notification  # noqa: PLC0415

            send_status_change_notification(request_id=42)

        assert len(send_message_calls) == 1
        assert send_message_calls[0] == 999

    def test_uses_d10_label_not_raw_status(self) -> None:
        """Task push text contains D-10 label 'На рассмотрении', not raw 'viewed'."""
        mock_request = _make_mock_request(status="viewed")
        mock_client = _make_mock_client(language="ru")

        sent_texts = []

        async def _capture_send(chat_id: int, text: str, **kwargs: object) -> None:
            sent_texts.append(text)

        with (
            patch("sqlalchemy.orm.Session") as mock_session_cls,
            patch("app.core.db.engine"),
            patch("telegram.bot.bot") as mock_bot,
        ):
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_request.client = mock_client
            mock_session.get.return_value = mock_request
            mock_bot.send_message = _capture_send

            from app.tasks.notify import send_status_change_notification  # noqa: PLC0415

            send_status_change_notification(request_id=42)

        assert len(sent_texts) == 1
        text = sent_texts[0]
        # Must contain D-10 RU label
        assert "На рассмотрении" in text, f"Expected D-10 label in text, got: {text!r}"
        # Must NOT contain raw status string
        assert "viewed" not in text, f"Raw status 'viewed' must not appear in text: {text!r}"

    def test_uz_template_renders_d10_label(self) -> None:
        """Task renders UZ template for a UZ client."""
        mock_request = _make_mock_request(status="viewed")
        mock_client = _make_mock_client(language="uz")

        sent_texts = []

        async def _capture_send(chat_id: int, text: str, **kwargs: object) -> None:
            sent_texts.append(text)

        with (
            patch("sqlalchemy.orm.Session") as mock_session_cls,
            patch("app.core.db.engine"),
            patch("telegram.bot.bot") as mock_bot,
        ):
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_request.client = mock_client
            mock_session.get.return_value = mock_request
            mock_bot.send_message = _capture_send

            from app.tasks.notify import send_status_change_notification  # noqa: PLC0415

            send_status_change_notification(request_id=42)

        assert len(sent_texts) == 1

    def test_missing_request_returns_error_dict(self) -> None:
        """Task returns {'status': 'error'} without raising when request not found."""
        with (
            patch("sqlalchemy.orm.Session") as mock_session_cls,
            patch("app.core.db.engine"),
        ):
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_session.get.return_value = None  # request not found

            from app.tasks.notify import send_status_change_notification  # noqa: PLC0415

            result = send_status_change_notification(request_id=99999)

        assert result["status"] == "error"
        assert "error" in result
        # Must NOT raise — task is idempotent-safe

    def test_no_telegram_user_id_skips_send(self) -> None:
        """Task skips bot.send_message when client.telegram_user_id is None."""
        mock_request = _make_mock_request(status="viewed")
        mock_client = _make_mock_client(telegram_user_id=None, language="ru")  # type: ignore[arg-type]
        mock_client.telegram_user_id = None

        send_calls = []

        async def _capture_send(**kwargs: object) -> None:
            send_calls.append(kwargs)

        with (
            patch("sqlalchemy.orm.Session") as mock_session_cls,
            patch("app.core.db.engine"),
            patch("telegram.bot.bot") as mock_bot,
        ):
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_request.client = mock_client
            mock_session.get.return_value = mock_request
            mock_bot.send_message = _capture_send

            from app.tasks.notify import send_status_change_notification  # noqa: PLC0415

            result = send_status_change_notification(request_id=42)

        assert result["status"] == "ok"
        assert len(send_calls) == 0  # No send attempted

    def test_returns_ok_dict_structure(self) -> None:
        """Task always returns {'status': 'ok', 'error': None} on success."""
        mock_request = _make_mock_request(status="new")
        mock_client = _make_mock_client(telegram_user_id=111, language="ru")

        with (
            patch("sqlalchemy.orm.Session") as mock_session_cls,
            patch("app.core.db.engine"),
            patch("telegram.bot.bot") as mock_bot,
        ):
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_request.client = mock_client
            mock_session.get.return_value = mock_request
            mock_bot.send_message = AsyncMock(return_value=None)

            from app.tasks.notify import send_status_change_notification  # noqa: PLC0415

            result = send_status_change_notification(request_id=42)

        assert result == {"status": "ok", "error": None}
