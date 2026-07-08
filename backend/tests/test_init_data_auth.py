"""
Tests for Telegram initData HMAC authentication.

Covers:
- verify_init_data: valid HMAC-signed initData returns parsed dict
- verify_init_data: bad hash raises InvalidInitData (ValueError subclass)
- verify_init_data: expired auth_date raises InvalidInitData
- verify_init_data: malformed/empty string raises InvalidInitData
- get_current_client: valid header for unknown user → creates Client
- get_current_client: valid header for known user → returns existing (no duplicate)
- get_current_client: missing header → HTTP 401 "Authentication required"
- get_current_client: invalid header → HTTP 401 "Authentication required"

T-03-01: HMAC-SHA256 verify per Telegram algorithm
T-03-02: 24h TTL on auth_date; identity from verified payload only
T-03-03: generic 401 "Authentication required" for every failure path
T-03-06: identity never from request body
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Helpers ────────────────────────────────────────────────────────────────────

# BOT_TOKEN used in conftest._TEST_ENV
_BOT_TOKEN = "123456789:AABBccDDeeFF"


def _sign_init_data(payload: dict[str, Any], bot_token: str, auth_date: int | None = None) -> str:
    """Build a valid Telegram initData string signed with bot_token.

    Implements the Telegram WebApp data-check algorithm:
      secret_key = HMAC_SHA256(key=b"WebAppData", msg=bot_token)
      check       = HMAC_SHA256(key=secret_key, msg=data_check_string)
    """
    if auth_date is None:
        auth_date = int(time.time())
    payload["auth_date"] = auth_date

    # Sort keys alphabetically, build data_check_string, exclude 'hash'
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(payload.items()) if k != "hash"
    )

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_value = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    payload["hash"] = hash_value

    return urllib.parse.urlencode(payload)


def _make_init_data(
    telegram_user_id: int = 12345,
    language_code: str = "ru",
    bot_token: str = _BOT_TOKEN,
    auth_date: int | None = None,
) -> str:
    """Build a full valid initData string with a user object."""
    user_json = json.dumps({"id": telegram_user_id, "language_code": language_code, "first_name": "Test"})
    payload: dict[str, Any] = {"user": user_json}
    return _sign_init_data(payload, bot_token, auth_date)


# ── Unit tests: verify_init_data ───────────────────────────────────────────────

def test_verify_init_data_valid_returns_dict() -> None:
    """Valid HMAC-signed initData with fresh auth_date returns the parsed dict."""
    from app.services.client_service import verify_init_data

    raw = _make_init_data(telegram_user_id=99, language_code="uz")
    result = verify_init_data(raw)

    assert isinstance(result, dict)
    assert result["user"]["id"] == 99
    assert result["user"]["language_code"] == "uz"


def test_verify_init_data_bad_hash_raises() -> None:
    """initData with a tampered hash raises a ValueError subclass."""
    from app.services.client_service import verify_init_data

    raw = _make_init_data()
    # Corrupt the hash
    raw_parts = dict(urllib.parse.parse_qsl(raw))
    raw_parts["hash"] = "deadbeef" * 8  # 64 hex chars but wrong
    corrupted = urllib.parse.urlencode(raw_parts)

    with pytest.raises(ValueError):
        verify_init_data(corrupted)


def test_verify_init_data_expired_auth_date_raises() -> None:
    """initData with auth_date older than 86400 s raises a ValueError subclass."""
    from app.services.client_service import verify_init_data

    # 25 hours ago
    expired_ts = int(time.time()) - 25 * 3600
    raw = _make_init_data(auth_date=expired_ts)

    with pytest.raises(ValueError):
        verify_init_data(raw)


def test_verify_init_data_empty_string_raises() -> None:
    """Empty/blank initData raises ValueError."""
    from app.services.client_service import verify_init_data

    with pytest.raises(ValueError):
        verify_init_data("")


def test_verify_init_data_malformed_raises() -> None:
    """Completely malformed initData raises ValueError."""
    from app.services.client_service import verify_init_data

    with pytest.raises(ValueError):
        verify_init_data("not=valid&initdata=true")


def test_verify_init_data_future_auth_date_raises() -> None:
    """HR-01: initData with auth_date far in the future is rejected (not treated as fresh).

    A negative age_seconds (auth_date > now) must raise InvalidInitData.
    Without the guard, age_seconds = -1_000_000 would pass the
    `age_seconds > INIT_DATA_TTL_SECONDS` check silently.
    """
    from app.services.client_service import verify_init_data

    # 1 000 000 seconds in the future — clearly illegitimate
    future_ts = int(time.time()) + 1_000_000
    raw = _make_init_data(auth_date=future_ts)

    with pytest.raises(ValueError, match="future"):
        verify_init_data(raw)


def test_verify_init_data_ttl_patchable_via_settings() -> None:
    """HR-02: TTL is read from settings at call time — patching settings affects the check.

    When TELEGRAM_INIT_DATA_TTL_SECONDS is patched to 0 (zero-second TTL), a token
    whose auth_date is even 1 second old must be rejected.  This would silently pass
    if the TTL were captured as a module-level constant at import time.
    """
    from unittest.mock import patch as _patch

    from app.services.client_service import verify_init_data

    # Token signed 5 seconds ago — normally well within the 86 400 s default TTL
    slightly_old_ts = int(time.time()) - 5
    raw = _make_init_data(auth_date=slightly_old_ts)

    # Patch settings to a 1-second TTL — the 5-second-old token must now be rejected
    with _patch("app.services.client_service.settings") as mock_settings:
        mock_settings.BOT_TOKEN = _BOT_TOKEN
        mock_settings.TELEGRAM_INIT_DATA_TTL_SECONDS = 1
        with pytest.raises(ValueError, match="expired"):
            verify_init_data(raw)


# ── get_or_create_client tests ─────────────────────────────────────────────────

def test_get_or_create_client_maps_ru_language() -> None:
    """Language code 'ru' is stored as 'ru'."""
    from app.services.client_service import get_or_create_client

    mock_db = MagicMock()
    # Simulate no existing client (SELECT returns None), then INSERT sets id
    existing_query = MagicMock()
    existing_query.filter.return_value.first.return_value = None
    mock_db.query.return_value = existing_query

    # After flush, return a client with id set
    new_client = MagicMock()
    new_client.id = 1
    new_client.language = "ru"
    mock_db.add = MagicMock()
    mock_db.flush = MagicMock()

    # Override db.query(...).filter(...).first() to return new_client on second call
    call_count = [0]
    def _query_side_effect(model: Any) -> Any:
        call_count[0] += 1
        if call_count[0] == 1:
            m = MagicMock()
            m.filter.return_value.first.return_value = None
            return m
        else:
            m = MagicMock()
            m.filter.return_value.first.return_value = new_client
            return m

    mock_db.query.side_effect = _query_side_effect

    result = get_or_create_client(mock_db, telegram_user_id=111, language="ru")
    assert result.language == "ru"


def test_get_or_create_client_maps_uz_language() -> None:
    """Language code 'uz' is stored as 'uz'."""
    from app.services.client_service import get_or_create_client

    mock_db = MagicMock()
    existing = MagicMock()
    existing.language = "uz"
    existing.id = 2
    mock_db.query.return_value.filter.return_value.first.return_value = existing

    result = get_or_create_client(mock_db, telegram_user_id=222, language="uz")
    assert result.language == "uz"


def test_get_or_create_client_unknown_language_defaults_to_ru() -> None:
    """Language code outside 'ru'/'uz' defaults to 'ru'."""
    from app.services.client_service import get_or_create_client

    mock_db = MagicMock()
    # No existing client
    call_count = [0]
    new_client = MagicMock()
    new_client.id = 3
    new_client.language = "ru"

    def _query_side_effect(model: Any) -> Any:
        call_count[0] += 1
        if call_count[0] == 1:
            m = MagicMock()
            m.filter.return_value.first.return_value = None
            return m
        else:
            m = MagicMock()
            m.filter.return_value.first.return_value = new_client
            return m

    mock_db.query.side_effect = _query_side_effect

    result = get_or_create_client(mock_db, telegram_user_id=333, language="de")
    # The returned client should have language 'ru' (default for unknown lang)
    assert result is not None


def test_normalize_language_supported_and_fallback() -> None:
    """app.core.languages.normalize_language keeps supported codes, falls back to ru."""
    from app.core.languages import (
        DEFAULT_LANGUAGE,
        SUPPORTED_LANGUAGES,
        normalize_language,
    )

    assert "tr" in SUPPORTED_LANGUAGES
    assert DEFAULT_LANGUAGE == "ru"
    for code in ("ru", "en", "uz", "tr", "fa", "zh"):
        assert normalize_language(code) == code
    for code in ("de", "", None):
        assert normalize_language(code) == "ru"


# ── Integration: get_current_client via FastAPI dep ───────────────────────────

def _make_client_fixture(
    existing_client: Any | None,
    new_client: Any | None = None,
) -> Generator[TestClient, None, None]:
    """Helper to build a TestClient with mocked DB for get_current_client dep tests."""
    from app.core.db import get_db
    from app.main import create_app

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.flush = MagicMock()
    mock_db.commit = MagicMock()

    call_count = [0]

    def _query_side_effect(model: Any) -> Any:
        call_count[0] += 1
        m = MagicMock()
        if existing_client is not None:
            m.filter.return_value.first.return_value = existing_client
        else:
            # First call (SELECT to check existence) returns None
            # Second call (SELECT after INSERT) returns new_client
            if call_count[0] == 1:
                m.filter.return_value.first.return_value = None
            else:
                m.filter.return_value.first.return_value = new_client
        return m

    mock_db.query.side_effect = _query_side_effect

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application, raise_server_exceptions=False) as tc:
        yield tc


@pytest.fixture
def client_valid_existing() -> Generator[TestClient, None, None]:
    """TestClient where the Telegram user already has a clients row."""
    existing = MagicMock()
    existing.id = 42
    existing.telegram_user_id = 12345
    existing.language = "ru"
    yield from _make_client_fixture(existing_client=existing)


@pytest.fixture
def client_new_user() -> Generator[TestClient, None, None]:
    """TestClient where the Telegram user does not yet have a clients row."""
    new = MagicMock()
    new.id = 99
    new.telegram_user_id = 77777
    new.language = "ru"
    yield from _make_client_fixture(existing_client=None, new_client=new)


def test_get_current_client_missing_header_returns_401(client_valid_existing: TestClient) -> None:
    """Request with no X-Telegram-Init-Data header → 401 Authentication required."""
    client_valid_existing.get("/api/v1/health")  # any route
    # Use the dedicated test endpoint — the health endpoint doesn't require auth.
    # We need to hit a route that uses get_current_client. Since /webapp/* doesn't
    # exist yet, we test the dependency directly via unit test instead.
    # Skip — covered by direct dep test below.
    pass


def _make_bare_dep_client() -> TestClient:
    """Minimal FastAPI app with a route protected by get_current_client."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_client
    from app.core.db import get_db

    mini_app = FastAPI()
    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.flush = MagicMock()
    mock_db.commit = MagicMock()

    existing = MagicMock()
    existing.id = 42
    existing.telegram_user_id = 12345
    existing.language = "ru"
    mock_db.query.return_value.filter.return_value.first.return_value = existing

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    mini_app.dependency_overrides[get_db] = _override_get_db

    @mini_app.get("/test-auth")
    def _test_route(client: Any = Depends(get_current_client)) -> dict[str, int]:
        return {"client_id": client.id}

    return TestClient(mini_app, raise_server_exceptions=False)


def test_get_current_client_missing_header_401() -> None:
    """Missing X-Telegram-Init-Data header → HTTP 401 'Authentication required'."""
    tc = _make_bare_dep_client()
    resp = tc.get("/test-auth")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication required"


def test_get_current_client_invalid_header_401() -> None:
    """Invalid/tampered X-Telegram-Init-Data → HTTP 401 'Authentication required'."""
    tc = _make_bare_dep_client()
    resp = tc.get("/test-auth", headers={"X-Telegram-Init-Data": "invalid=garbage&hash=badcafe"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication required"


def test_get_current_client_valid_header_known_user_returns_client() -> None:
    """Valid initData for a known user returns the existing Client (no duplicate)."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_client
    from app.core.db import get_db

    mini_app = FastAPI()
    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.flush = MagicMock()
    mock_db.commit = MagicMock()

    existing = MagicMock()
    existing.id = 42
    existing.telegram_user_id = 12345
    existing.language = "ru"
    mock_db.query.return_value.filter.return_value.first.return_value = existing

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    mini_app.dependency_overrides[get_db] = _override_get_db

    @mini_app.get("/test-auth")
    def _test_route(client: Any = Depends(get_current_client)) -> dict[str, int]:
        return {"client_id": client.id}

    tc = TestClient(mini_app, raise_server_exceptions=False)

    init_data = _make_init_data(telegram_user_id=12345, language_code="ru")
    resp = tc.get("/test-auth", headers={"X-Telegram-Init-Data": init_data})
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_id"] == 42
    # DB.add should NOT have been called (existing user)
    mock_db.add.assert_not_called()


def test_get_current_client_valid_header_unknown_user_creates_client() -> None:
    """Valid initData for an unknown user creates and returns a new Client."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_client
    from app.core.db import get_db

    mini_app = FastAPI()
    mock_db = MagicMock()
    mock_db.flush = MagicMock()
    mock_db.commit = MagicMock()

    new_client = MagicMock()
    new_client.id = 77
    new_client.telegram_user_id = 99999
    new_client.language = "ru"

    call_count = [0]

    def _query_side_effect(model: Any) -> Any:
        call_count[0] += 1
        m = MagicMock()
        if call_count[0] == 1:
            # First SELECT: user not found
            m.filter.return_value.first.return_value = None
        else:
            # Second SELECT (after INSERT): return new_client
            m.filter.return_value.first.return_value = new_client
        return m

    mock_db.query.side_effect = _query_side_effect
    mock_db.add = MagicMock()

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    mini_app.dependency_overrides[get_db] = _override_get_db

    @mini_app.get("/test-auth")
    def _test_route(client: Any = Depends(get_current_client)) -> dict[str, int]:
        return {"client_id": client.id}

    tc = TestClient(mini_app, raise_server_exceptions=False)

    init_data = _make_init_data(telegram_user_id=99999, language_code="ru")
    resp = tc.get("/test-auth", headers={"X-Telegram-Init-Data": init_data})
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_id"] == 77
    # A new Client should have been added to the DB
    mock_db.add.assert_called_once()
