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
    # Not required by Settings, but asserted on by tests. Settings reads the
    # developer's real `.env`, so their own values were substituted for these —
    # the budget and OTP-cap tests then failed on their machine and nowhere
    # else, because CI has no such file. Pinning them here restores the
    # documented defaults; os.environ takes precedence over env_file.
    #
    # (The original trigger was a second env file at `backend/.env` that only
    # a CWD-relative `env_file` could see. That file is gone and `Settings` now
    # reads one absolute path, but the pinning is still needed: the repo-root
    # `.env` a developer edits is read all the same.)
    "LLM_DAILY_TOKEN_LIMIT": "500000",
    "OTP_MAX_SENDS_PER_DAY": "5",
    # The runtime feature switches, pinned at their SHIPPED defaults for the same
    # reason as the two above, and with more at stake now that they come from
    # `.env` rather than a table the tests could truncate. A developer whose
    # `.env` says `GOV_REGISTRY_MODE=didox` (a perfectly reasonable thing to want
    # locally) would otherwise run a suite where the registry rail is live —
    # green here, red in CI, or worse, quietly exercising a different branch.
    # Tests that need a switch flipped use the `set_switch` helper below.
    "NEWS_AI_ENABLED": "true",
    "NEWS_REQUIRE_APPROVAL": "false",
    "REPORT_AUTO_PUBLISH": "false",
    "NEWS_PROMPT_VERSION": "v3",
    "NEWS_REFRESH_INTERVAL_MINUTES": "60",
    "VERIFICATION_AUTO_APPROVE": "false",
    "CONTRACT_PENDING_TTL_DAYS": "30",
    "ESCROW_MODE": "stub",
    "RFQ_SUPPLIER_PUSH_ENABLED": "false",
    "RFQ_SUPPLIER_PUSH_TOP_N": "10",
    "RFQ_SUPPLIER_OFFER_MAX_AGE_DAYS": "90",
    "SUBSTANCE_AI_ENABLED": "true",
    "DANGEROUS_CHECK_ENFORCED": "false",
    "CHEM_REGISTRY_MODE": "stub",
    "GOV_REGISTRY_MODE": "stub",
    "DIDOX_MODE": "stub",
    "APP_ENV": "development",
    # Both Didox rails ship `stub`, so no partner token is needed to boot — but
    # a developer .env supplies one and some tests assert the degraded path.
    "DIDOX_PARTNER_TOKEN": "",
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


def set_switch(**switches: object) -> None:
    """Point one or more runtime feature switches at a value for this test.

    Writes the OVERRIDE layer, not the env layer, so a test exercises the same
    precedence path production does. Setting `settings.<ENV_VAR>` instead would
    be shadowed by any override present, and would therefore prove nothing about
    the code that ships — it would only have kept working here by accident,
    because a unit-test process starts with an empty snapshot.

    Keyed by the snake_case setting name (`escrow_mode`), not the env var, so a
    typo raises `KeyError` from `SPECS` rather than silently setting an attribute
    nothing reads. `_restore_switches` below clears the snapshot afterwards.
    """
    from app.services import settings_service  # noqa: PLC0415

    merged = settings_service.current_overrides()
    for key, value in switches.items():
        settings_service.SPECS[key]  # noqa: B018 — resolves the key, raising on a typo
        merged[key] = value  # type: ignore[assignment]
    settings_service.seed_overrides(merged)


@pytest.fixture(autouse=True)
def _restore_switches() -> Generator[None, None, None]:
    """Undo any `set_switch` after every test.

    Both layers, because tests reach for both: the snapshot is where `set_switch`
    writes, and a few tests still monkeypatch the `settings` singleton directly.
    Either one leaking turns the next test's failure into an order-dependent one,
    which is the expensive kind to chase.

    It also pins `AUTO_REFRESH` off for the whole suite. `refresh()` is wired
    into `get_db` and Celery's `task_prerun`, and the unit suite has neither a
    Redis nor a migrated Postgres — leaving it on would spend a connect timeout
    per request against a Redis that is not there, to load overrides that do not
    exist.
    """
    from app.core.config import settings  # noqa: PLC0415
    from app.services import settings_service  # noqa: PLC0415

    settings_service.AUTO_REFRESH = False
    env_vars = [spec.env_var for spec in settings_service.SPECS.values()]
    before = {name: getattr(settings, name) for name in env_vars}
    try:
        yield
    finally:
        settings_service.clear_snapshot()
        for name, value in before.items():
            setattr(settings, name, value)


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
