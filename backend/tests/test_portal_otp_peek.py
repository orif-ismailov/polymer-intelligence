"""OTP peek e2e hook (R1 W7): double-gated (console driver + DEBUG), 404 otherwise."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis

_PEEK = "/api/v1/portal/auth/otp/peek"


def _app_client(fake: FakeRedis) -> TestClient:
    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    app = create_app()

    def _redis():  # noqa: ANN202
        yield fake

    def _db():  # noqa: ANN202
        yield object()

    app.dependency_overrides[get_redis] = _redis
    app.dependency_overrides[get_db] = _db
    with patch("app.api.health._check_redis", return_value="ok"):
        return TestClient(app)


def test_peek_404_when_not_debug() -> None:
    from app.core.config import settings  # noqa: PLC0415

    fake = FakeRedis()
    with patch.object(settings, "DEBUG", False), patch.object(settings, "SMS_PROVIDER", "console"):
        client = _app_client(fake)
        assert client.get(_PEEK, params={"phone": "+998901234567"}).status_code == 404


def test_peek_404_when_eskiz_even_if_debug() -> None:
    from app.core.config import settings  # noqa: PLC0415

    fake = FakeRedis()
    with patch.object(settings, "DEBUG", True), patch.object(settings, "SMS_PROVIDER", "eskiz"):
        client = _app_client(fake)
        assert client.get(_PEEK, params={"phone": "+998901234567"}).status_code == 404


def test_peek_returns_code_when_console_and_debug() -> None:
    from app.core.config import settings  # noqa: PLC0415
    from app.services import otp_service  # noqa: PLC0415

    fake = FakeRedis()
    with (
        patch.object(settings, "DEBUG", True),
        patch.object(settings, "SMS_PROVIDER", "console"),
        patch.object(otp_service, "_generate_code", return_value="654321"),
        patch.object(otp_service, "_enqueue_sms"),
    ):
        otp_service.request_code(object(), fake, "+998901234567", "1.2.3.4")  # type: ignore[arg-type]
        client = _app_client(fake)
        resp = client.get(_PEEK, params={"phone": "901234567"})  # normalizes to +998…
    assert resp.status_code == 200
    assert resp.json()["code"] == "654321"


def test_peek_404_for_unknown_phone() -> None:
    from app.core.config import settings  # noqa: PLC0415

    fake = FakeRedis()
    with patch.object(settings, "DEBUG", True), patch.object(settings, "SMS_PROVIDER", "console"):
        client = _app_client(fake)
        assert client.get(_PEEK, params={"phone": "+998900000000"}).status_code == 404
