"""
pytest configuration and fixtures for the backend test suite.

Provides:
- A FastAPI TestClient with db and redis health checks mocked out so that
  unit tests do not require live infrastructure.
- Environment patches that satisfy Settings validation.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Minimum required env vars ─────────────────────────────────────────────────
# These satisfy the Settings required-fields validation during test collection.
_TEST_ENV: dict[str, str] = {
    "DATABASE_URL": "postgresql+psycopg://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "ANTHROPIC_API_KEY": "sk-ant-test-key",
    "BOT_TOKEN": "123456789:AABBccDDeeFF",
    "WEBHOOK_SECRET": "test_webhook_secret_at_least_32_chars_long",
    "TG_API_ID": "12345678",
    "TG_API_HASH": "abcdef1234567890abcdef1234567890",
    "JWT_SECRET": "test_jwt_secret_must_be_at_least_64_chars_long_for_security_xx",
    "S3_ACCESS_KEY": "minio_test_access",
    "S3_SECRET_KEY": "minio_test_secret",
}


@pytest.fixture(scope="session", autouse=True)
def patch_env() -> Generator[None, None, None]:
    """Patch environment variables for the entire test session.

    This runs before any module that imports app.core.config so that
    Settings() gets valid env values rather than raising ValidationError.
    """
    with patch.dict(os.environ, _TEST_ENV, clear=False):
        yield


def _mock_db_session() -> MagicMock:
    """Return a mock Session that silently accepts db.execute(...)."""
    session = MagicMock()
    session.execute.return_value = MagicMock()
    return session


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient with db and redis probes mocked to return 'ok'."""
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    application = create_app()

    # Override get_db so tests don't need a live Postgres connection
    mock_session = _mock_db_session()

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_session

    application.dependency_overrides[get_db] = _override_get_db

    # Patch _check_redis to avoid needing a live Redis connection
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def client_db_error() -> Generator[TestClient, None, None]:
    """TestClient where the db check returns an error (session.execute raises)."""
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    application = create_app()

    def _error_db() -> Generator[Any, None, None]:
        session = MagicMock()
        session.execute.side_effect = Exception("connection refused")
        yield session

    application.dependency_overrides[get_db] = _error_db

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def client_redis_error() -> Generator[TestClient, None, None]:
    """TestClient where the redis check returns an error."""
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    application = create_app()

    mock_session = _mock_db_session()

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_session

    application.dependency_overrides[get_db] = _override_get_db

    with patch("app.api.health._check_redis", return_value="error"), TestClient(application) as test_client:
        yield test_client
