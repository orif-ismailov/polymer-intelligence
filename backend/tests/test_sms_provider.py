"""SMS port + send_sms task tests (R1 W3 — T3.1).

DB-free. Covers the provider factory, the console driver (dev/CI), the Eskiz
provider's auth + 401-refresh flow via httpx.MockTransport, and the send_sms
Celery task (provider + sms_send_log write mocked). App imports are lazy so
`settings` is only built after conftest's patch_env fixture runs.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx


def test_sms_send_result_defaults() -> None:
    from app.integrations.sms.base import SmsSendResult  # noqa: PLC0415

    ok = SmsSendResult(ok=True)
    assert ok.ok is True
    assert ok.provider_msg_id is None
    assert ok.error is None


def test_factory_returns_console_by_default(monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import settings  # noqa: PLC0415
    from app.integrations.sms import get_sms_provider  # noqa: PLC0415
    from app.integrations.sms.console import ConsoleSmsProvider  # noqa: PLC0415

    monkeypatch.setattr(settings, "SMS_PROVIDER", "console")
    provider = get_sms_provider()
    assert isinstance(provider, ConsoleSmsProvider)
    assert provider.provider_name == "console"


def test_factory_returns_eskiz_when_configured(monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import settings  # noqa: PLC0415
    from app.integrations.sms import get_sms_provider  # noqa: PLC0415
    from app.integrations.sms.eskiz import EskizSmsProvider  # noqa: PLC0415

    monkeypatch.setattr(settings, "SMS_PROVIDER", "eskiz")
    provider = get_sms_provider()
    assert isinstance(provider, EskizSmsProvider)
    assert provider.provider_name == "eskiz"


def test_console_provider_send_logs_and_succeeds() -> None:
    from app.integrations.sms.console import ConsoleSmsProvider  # noqa: PLC0415

    result = asyncio.run(ConsoleSmsProvider().send("+998901234567", "code: 123456"))
    assert result.ok is True


# ── Eskiz provider (httpx MockTransport) ──────────────────────────────────────


def _eskiz_with_transport(handler):  # noqa: ANN001, ANN202
    from app.integrations.sms.eskiz import EskizSmsProvider  # noqa: PLC0415

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return EskizSmsProvider(client_factory=factory)


def test_eskiz_logs_in_then_sends() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"data": {"token": "tok-1"}})
        assert request.headers["Authorization"] == "Bearer tok-1"
        return httpx.Response(200, json={"id": "msg-42", "status": "waiting"})

    result = asyncio.run(_eskiz_with_transport(handler).send("+998 90 123 45 67", "hi"))
    assert result.ok is True
    assert result.provider_msg_id == "msg-42"
    assert any("auth/login" in c for c in calls)
    assert any("sms/send" in c for c in calls)


def test_eskiz_refreshes_token_on_401_then_retries() -> None:
    state = {"token": 0, "send_attempts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/login":
            state["token"] += 1
            return httpx.Response(200, json={"data": {"token": f"tok-{state['token']}"}})
        state["send_attempts"] += 1
        if state["send_attempts"] == 1:
            return httpx.Response(401, json={"message": "token expired"})
        return httpx.Response(200, json={"id": "msg-ok"})

    result = asyncio.run(_eskiz_with_transport(handler).send("+998901234567", "hi"))
    assert result.ok is True
    assert result.provider_msg_id == "msg-ok"
    assert state["token"] == 2  # logged in twice (initial + refresh)


def test_eskiz_degrades_to_error_on_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    result = asyncio.run(_eskiz_with_transport(handler).send("+998901234567", "hi"))
    assert result.ok is False
    assert result.error is not None


# ── send_sms task ─────────────────────────────────────────────────────────────


def test_send_sms_task_succeeds_and_never_logs_the_code(caplog) -> None:  # noqa: ANN001
    from app.integrations.sms.base import SmsSendResult  # noqa: PLC0415
    from app.tasks import notify  # noqa: PLC0415

    fake_provider = MagicMock()
    fake_provider.provider_name = "console"

    async def _send(phone: str, text: str) -> SmsSendResult:
        return SmsSendResult(ok=True, provider_msg_id="pm-1")

    fake_provider.send = _send

    with (
        patch("app.integrations.sms.get_sms_provider", return_value=fake_provider),
        patch.object(notify, "_write_sms_log") as write_log,
        caplog.at_level("DEBUG"),
    ):
        result = notify.send_sms("+998901234567", "your code is 654321", purpose="otp")

    assert result["status"] == "ok"
    assert result["provider_msg_id"] == "pm-1"
    write_log.assert_called_once()
    # The code must never appear in the task's own logs (only the console driver prints it).
    assert "654321" not in caplog.text


def test_send_sms_task_records_error_and_does_not_raise() -> None:
    from app.tasks import notify  # noqa: PLC0415

    fake_provider = MagicMock()
    fake_provider.provider_name = "eskiz"

    async def _boom(phone: str, text: str):  # noqa: ANN202
        raise RuntimeError("provider down")

    fake_provider.send = _boom

    with (
        patch("app.integrations.sms.get_sms_provider", return_value=fake_provider),
        patch.object(notify, "_write_sms_log") as write_log,
    ):
        result = notify.send_sms("+998901234567", "code 111111")

    assert result["status"] == "error"
    write_log.assert_called_once()
    # status arg recorded as "error"
    assert write_log.call_args.args[-1] == "error"
