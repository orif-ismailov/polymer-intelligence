"""
Tests for forum-topic routing of team-group notifications.

- _deliver_to_group: threads message_thread_id when set, omits it when None, and
  falls back to General (no thread) on a TelegramBadRequest (invalid/closed topic).
- Mapping: buyer requests + offer inquiries → NOTIFY_TOPIC_BUYERS; seller offers →
  NOTIFY_TOPIC_SELLERS.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

# ── _deliver_to_group unit behavior ───────────────────────────────────────────


class _RecordingBot:
    def __init__(self, fail_with_thread: bool = False) -> None:
        self.threads: list[int | None] = []
        self.fail_with_thread = fail_with_thread

    async def send_message(self, chat_id: int, text: str, reply_markup: object = None, **kwargs: object) -> None:
        thread = kwargs.get("message_thread_id")
        self.threads.append(thread)  # type: ignore[arg-type]
        if self.fail_with_thread and thread is not None:
            from aiogram.exceptions import TelegramBadRequest  # noqa: PLC0415

            raise TelegramBadRequest(method=MagicMock(), message="message thread not found")


def test_deliver_threads_topic_when_set() -> None:
    from app.tasks import notify  # noqa: PLC0415

    bot = _RecordingBot()
    asyncio.run(notify._deliver_to_group(bot, -100, 34, text="x"))
    assert bot.threads == [34]


def test_deliver_omits_thread_when_none() -> None:
    from app.tasks import notify  # noqa: PLC0415

    bot = _RecordingBot()
    asyncio.run(notify._deliver_to_group(bot, -100, None, text="x"))
    assert bot.threads == [None]


def test_deliver_falls_back_to_general_on_bad_topic() -> None:
    from app.tasks import notify  # noqa: PLC0415

    bot = _RecordingBot(fail_with_thread=True)
    asyncio.run(notify._deliver_to_group(bot, -100, 999, text="x"))
    # First tried the topic (999), then retried on General (None).
    assert bot.threads == [999, None]


# ── Mapping: which task routes to which topic ─────────────────────────────────


def _run_task_capture_thread(task_call, settings_patch: dict[str, int], get_return: object):
    """Run a notify task with a captured send_message and return the thread id used."""
    captured: dict[str, object] = {}

    async def _cap(chat_id: int, text: str, reply_markup: object = None, **kwargs: object) -> None:
        captured["thread"] = kwargs.get("message_thread_id")

    from app.core.config import settings  # noqa: PLC0415

    patches = [patch.object(settings, k, v) for k, v in settings_patch.items()]
    with (
        patches[0],
        patches[1],
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("telegram.bot.bot") as mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = get_return
        mock_bot.send_message = _cap
        mock_bot.send_photo = AsyncMock()
        task_call()
    return captured.get("thread")


def _fake_request() -> MagicMock:
    r = MagicMock()
    r.product_id = None
    r.product_text = "EVA"
    r.urgency = SimpleNamespace(value="high")
    return r


def _fake_offer() -> MagicMock:
    o = MagicMock()
    o.product_id = None
    o.product_text = "EVA"
    o.files = []
    o.incoterms = SimpleNamespace(value="FCA")
    o.seller = SimpleNamespace(
        company_name="S", contact_name=None, phone=None, telegram_username=None, telegram_user_id=1
    )
    return o


def _fake_offer_request() -> MagicMock:
    r = MagicMock()
    r.offer = _fake_offer()
    r.client = SimpleNamespace(
        company_name="B", contact_name=None, phone=None, telegram_user_id=2
    )
    r.message = None
    return r


def test_request_routes_to_buyers_topic() -> None:
    from app.tasks.notify import send_request_to_group  # noqa: PLC0415

    thread = _run_task_capture_thread(
        lambda: send_request_to_group(request_id=1),
        {"REQUEST_NOTIFY_CHAT_ID": -100, "NOTIFY_TOPIC_BUYERS": 32},
        _fake_request(),
    )
    assert thread == 32


def test_offer_routes_to_sellers_topic() -> None:
    from app.tasks.notify import send_offer_to_group  # noqa: PLC0415

    thread = _run_task_capture_thread(
        lambda: send_offer_to_group(offer_id=1),
        {"REQUEST_NOTIFY_CHAT_ID": -100, "NOTIFY_TOPIC_SELLERS": 34},
        _fake_offer(),
    )
    assert thread == 34


def test_offer_request_routes_to_buyers_topic() -> None:
    from app.tasks.notify import send_offer_request_to_group  # noqa: PLC0415

    thread = _run_task_capture_thread(
        lambda: send_offer_request_to_group(offer_request_id=1),
        {"REQUEST_NOTIFY_CHAT_ID": -100, "NOTIFY_TOPIC_BUYERS": 32},
        _fake_offer_request(),
    )
    assert thread == 32
