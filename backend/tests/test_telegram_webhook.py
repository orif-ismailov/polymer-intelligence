"""
Tests for POST /api/v1/telegram/webhook/{secret}.

TDD RED phase: tests written before router implementation.

Covers:
- Correct path secret + correct X-Telegram-Bot-Api-Secret-Token header → 200 OK
- Wrong path secret (correct header) → 403
- Correct path secret + wrong X-Telegram-Bot-Api-Secret-Token header → 403
- Missing X-Telegram-Bot-Api-Secret-Token header → 403

Security invariants:
- T-03-11: Spoofing — BOTH path secret AND header must match WEBHOOK_SECRET via
  hmac.compare_digest; single mismatch → 403.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Must match conftest._TEST_ENV
_WEBHOOK_SECRET = "test_webhook_secret_at_least_32_chars_long"
_WRONG_SECRET = "wrong_secret_totally_different_value_xxxx"


# ── Minimal aiogram Update payload ────────────────────────────────────────────
_MINIMAL_UPDATE = {
    "update_id": 100,
    "message": {
        "message_id": 1,
        "date": 1700000000,
        "chat": {"id": 999, "type": "private"},
        "from": {
            "id": 999,
            "is_bot": False,
            "first_name": "Test",
            "language_code": "ru",
        },
        "text": "/start",
    },
}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def webhook_client() -> Generator[TestClient, None, None]:
    """TestClient with:
    - get_db mocked (no live Postgres)
    - dp.feed_update patched to a no-op AsyncMock (no bot dispatch)
    """
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    application = create_app()

    mock_session = MagicMock()
    mock_session.execute.return_value = MagicMock()

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_session

    application.dependency_overrides[get_db] = _override_get_db

    with (
        patch("app.api.health._check_redis", return_value="ok"),
        patch("telegram.bot.dp") as mock_dp,
    ):
        mock_dp.feed_update = AsyncMock(return_value=None)
        with TestClient(application) as test_client:
            yield test_client


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestWebhookSecretValidation:
    """Secret validation: both path secret and header must match."""

    def test_correct_secret_and_header_returns_200(
        self, webhook_client: TestClient
    ) -> None:
        """POST with correct path secret + correct header → 200 {"ok": True}."""
        response = webhook_client.post(
            f"/api/v1/telegram/webhook/{_WEBHOOK_SECRET}",
            json=_MINIMAL_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": _WEBHOOK_SECRET},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_wrong_path_secret_returns_403(
        self, webhook_client: TestClient
    ) -> None:
        """POST with wrong path secret → 403, even if header is correct."""
        response = webhook_client.post(
            f"/api/v1/telegram/webhook/{_WRONG_SECRET}",
            json=_MINIMAL_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": _WEBHOOK_SECRET},
        )
        assert response.status_code == 403

    def test_wrong_header_secret_returns_403(
        self, webhook_client: TestClient
    ) -> None:
        """POST with wrong X-Telegram-Bot-Api-Secret-Token → 403, even if path is correct."""
        response = webhook_client.post(
            f"/api/v1/telegram/webhook/{_WEBHOOK_SECRET}",
            json=_MINIMAL_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": _WRONG_SECRET},
        )
        assert response.status_code == 403

    def test_missing_header_returns_403(
        self, webhook_client: TestClient
    ) -> None:
        """POST with no X-Telegram-Bot-Api-Secret-Token header → 403."""
        response = webhook_client.post(
            f"/api/v1/telegram/webhook/{_WEBHOOK_SECRET}",
            json=_MINIMAL_UPDATE,
            # No X-Telegram-Bot-Api-Secret-Token header
        )
        assert response.status_code == 403

    def test_both_wrong_returns_403(
        self, webhook_client: TestClient
    ) -> None:
        """POST with wrong path secret + wrong header → 403."""
        response = webhook_client.post(
            f"/api/v1/telegram/webhook/{_WRONG_SECRET}",
            json=_MINIMAL_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": _WRONG_SECRET},
        )
        assert response.status_code == 403
