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
    "VERIFICATION_ENC_KEY": "cG9seW1lcl92ZXJpZmljYXRpb25fdGVzdF9rZXlfMzI=",
    # Not required by Settings, but asserted on by tests. Settings reads
    # `env_file=".env"` relative to the CWD, so a developer running pytest from
    # backend/ with a local backend/.env had their own values substituted for
    # these — the budget and OTP-cap tests then failed on their machine and
    # nowhere else, because CI has no such file. Pinning them here restores the
    # documented defaults; os.environ takes precedence over env_file.
    "LLM_DAILY_TOKEN_LIMIT": "500000",
    "OTP_MAX_SENDS_PER_DAY": "5",
}

# Applied at conftest IMPORT time, not from the fixture below, because a
# session-scoped fixture runs after collection — and `settings` is a module-level
# singleton built the first time anything imports app.core.config. A test module
# that imports an app module at top level (needed when enum members appear in a
# @parametrize) does that during collection, so the singleton would be built from
# the developer's real .env and keep those values for the whole session. That is
# silent and remote: it surfaced as "HMAC mismatch" in the Telegram auth tests,
# which sign with the token below and were then verified against a real one.
#
# conftest is imported before any test module in its directory, so setting the
# vars here is early enough. No restore: the values are only meant to outlive the
# process, and pytest owns it.
def _real_db_optin() -> str | None:
    """A `DATABASE_URL` that explicitly names the localhost `test_polymer` database.

    Pinning the env above is what keeps a developer's `.env` out of the `settings`
    singleton — but it also made `DATABASE_URL` impossible to override, and that is
    the ONE variable the real-Postgres suites key off (`_verification_db.IS_REAL_DB`,
    which reads it at import time, after this module has already run). The result was
    silent: all 424 `@requires_real_db` tests skipped unconditionally, including in a
    session that set the variable on purpose, and reported themselves as "skipped"
    exactly as they do on a machine with no Postgres at all.

    This lets that single opt-in through, using the same predicate the guard applies
    so the two cannot drift. CI has no `test_polymer`, so its behaviour is unchanged
    and the suite stays hermetic there by default.
    """
    url = os.environ.get("DATABASE_URL", "")
    return url if "localhost" in url and "test_polymer" in url else None


_REAL_DB_URL = _real_db_optin()

# Test values win over anything already exported, matching the fixture's
# patch.dict(..., clear=False) semantics.
os.environ.update(_TEST_ENV)
if _REAL_DB_URL is not None:
    os.environ["DATABASE_URL"] = _REAL_DB_URL

#: What the fixture below restores — the pinned env, plus the real-DB opt-in when
#: one was made, so the session cannot silently lose it at the first teardown.
_SESSION_ENV: dict[str, str] = (
    _TEST_ENV if _REAL_DB_URL is None else {**_TEST_ENV, "DATABASE_URL": _REAL_DB_URL}
)


@pytest.fixture(scope="session", autouse=True)
def patch_env() -> Generator[None, None, None]:
    """Keep the test env in place for the session, and restore it afterwards.

    The values are already set at import time (see above) — this fixture exists so
    a test that deliberately mutates one of them is still rolled back at teardown.
    """
    with patch.dict(os.environ, _SESSION_ENV, clear=False):
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


# ── Adapter registry isolation ────────────────────────────────────────────────
# The source-adapter registry is a process-global mutated by import side-effects AND
# by tests that call _clear_registry()/register_adapter(). main.py now imports the
# uzex/cbu_rates adapters at startup, so they get cached early — a later
# `import app.ingest.uzex` no longer re-registers them after a _clear_registry(),
# which left the adapter-registration tests order-dependent. Snapshot the full
# production set once and restore it after every test so order no longer matters.


@pytest.fixture(scope="session")
def _production_adapters(patch_env: None) -> dict[str, object]:
    """Import every production adapter once (env patched) and snapshot the registry."""
    import app.ingest.cbu_rates  # noqa: F401, PLC0415
    import app.ingest.html_table  # noqa: F401, PLC0415
    import app.ingest.llm_page  # noqa: F401, PLC0415
    import app.ingest.rss  # noqa: F401, PLC0415
    import app.ingest.telegram_channel  # noqa: F401, PLC0415
    import app.ingest.uzex  # noqa: F401, PLC0415
    from app.ingest import registry  # noqa: PLC0415

    return dict(registry._REGISTRY)


@pytest.fixture(autouse=True)
def _restore_adapter_registry(
    _production_adapters: dict[str, object],
) -> Generator[None, None, None]:
    """Reset the global adapter registry to the full production set after each test."""
    from app.ingest import registry  # noqa: PLC0415

    yield
    registry._REGISTRY.clear()
    registry._REGISTRY.update(_production_adapters)
