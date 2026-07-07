"""
Tests for the BROWSER auth path: Telegram Login Widget verification, the client
session token/cookie, the dual-path get_current_client, the /webapp/auth router,
and the public featured-offers endpoint.

The Mini App initData path is covered by test_init_data_auth.py and is NOT modified
here — these tests only add coverage for the browser session that rides alongside it.

T-03-01: widget HMAC via hmac.compare_digest (constant-time).
T-03-02: auth_date TTL + future-skew guard.
T-03-03: generic 401 on every failure path.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Generator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

# BOT_TOKEN used in conftest._TEST_ENV
_BOT_TOKEN = "123456789:AABBccDDeeFF"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sign_widget(
    fields: dict[str, Any],
    bot_token: str = _BOT_TOKEN,
    auth_date: int | None = None,
) -> dict[str, Any]:
    """Build a valid Telegram Login Widget payload signed with bot_token.

    Login Widget algorithm: secret = SHA256(bot_token); hash = HMAC_SHA256(secret,
    sorted key=value joined by '\\n', excluding hash).
    """
    if auth_date is None:
        auth_date = int(time.time())
    payload = dict(fields)
    payload["auth_date"] = auth_date
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()) if k != "hash")
    secret = hashlib.sha256(bot_token.encode()).digest()
    payload["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return payload


def _valid_widget(telegram_user_id: int = 12345) -> dict[str, Any]:
    return _sign_widget({"id": telegram_user_id, "first_name": "Test", "username": "tester"})


# ── Unit: verify_login_widget ──────────────────────────────────────────────────

def test_verify_login_widget_valid_returns_dict() -> None:
    from app.services.client_service import verify_login_widget

    payload = _valid_widget(telegram_user_id=777)
    result = verify_login_widget({k: str(v) for k, v in payload.items()})

    assert result["id"] == 777  # coerced to int
    assert isinstance(result["auth_date"], int)


def test_verify_login_widget_bad_hash_raises() -> None:
    from app.services.client_service import verify_login_widget

    payload = _valid_widget()
    payload["hash"] = "deadbeef" * 8  # 64 hex chars, wrong
    with pytest.raises(ValueError):
        verify_login_widget({k: str(v) for k, v in payload.items()})


def test_verify_login_widget_tampered_field_raises() -> None:
    """Mutating a signed field after signing must invalidate the hash."""
    from app.services.client_service import verify_login_widget

    payload = _valid_widget(telegram_user_id=1)
    payload["id"] = 999  # tamper — hash no longer matches
    with pytest.raises(ValueError):
        verify_login_widget({k: str(v) for k, v in payload.items()})


def test_verify_login_widget_expired_raises() -> None:
    from app.services.client_service import verify_login_widget

    payload = _sign_widget({"id": 5, "first_name": "X"}, auth_date=int(time.time()) - 25 * 3600)
    with pytest.raises(ValueError, match="expired"):
        verify_login_widget({k: str(v) for k, v in payload.items()})


def test_verify_login_widget_future_raises() -> None:
    from app.services.client_service import verify_login_widget

    payload = _sign_widget({"id": 5, "first_name": "X"}, auth_date=int(time.time()) + 1_000_000)
    with pytest.raises(ValueError, match="future"):
        verify_login_widget({k: str(v) for k, v in payload.items()})


def test_verify_login_widget_empty_raises() -> None:
    from app.services.client_service import verify_login_widget

    with pytest.raises(ValueError):
        verify_login_widget({})


# ── Unit: client session token ─────────────────────────────────────────────────

def test_client_session_token_round_trip() -> None:
    from app.core.security import create_client_session_token, decode_token

    token = create_client_session_token(subject="12345")
    payload = decode_token(token, expected_type="client_session")
    assert payload["sub"] == "12345"
    assert payload["type"] == "client_session"
    assert payload["role"] == "client"


def test_client_session_token_rejected_as_access() -> None:
    """A client_session token must NOT validate as a staff access token (T-03-03)."""
    from jose import JWTError

    from app.core.security import create_client_session_token, decode_token

    token = create_client_session_token(subject="12345")
    with pytest.raises(JWTError):
        decode_token(token, expected_type="access")


# ── Integration: get_current_client dual path ──────────────────────────────────

def _protected_app(existing_client: Any | None) -> TestClient:
    """Minimal app with a route guarded by get_current_client + a mocked db."""
    from app.api.deps import get_current_client
    from app.core.db import get_db

    mini = FastAPI()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = existing_client

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    mini.dependency_overrides[get_db] = _override_get_db

    @mini.get("/test-auth")
    def _route(client: Any = Depends(get_current_client)) -> dict[str, int]:
        return {"client_id": client.id}

    return TestClient(mini, raise_server_exceptions=False)


def test_get_current_client_accepts_valid_session_cookie() -> None:
    from app.core.security import create_client_session_token

    existing = SimpleNamespace(id=42, telegram_user_id=12345, language="ru")
    tc = _protected_app(existing)
    token = create_client_session_token(subject="12345")

    resp = tc.get("/test-auth", cookies={"client_session": token})
    assert resp.status_code == 200
    assert resp.json()["client_id"] == 42


def test_get_current_client_empty_header_falls_through_to_cookie() -> None:
    """The browser client sends X-Telegram-Init-Data: '' — it must NOT short-circuit
    to 401 but fall through to the session cookie."""
    from app.core.security import create_client_session_token

    existing = SimpleNamespace(id=7, telegram_user_id=555, language="ru")
    tc = _protected_app(existing)
    token = create_client_session_token(subject="555")

    resp = tc.get(
        "/test-auth",
        headers={"X-Telegram-Init-Data": ""},
        cookies={"client_session": token},
    )
    assert resp.status_code == 200
    assert resp.json()["client_id"] == 7


def test_get_current_client_no_header_no_cookie_401() -> None:
    tc = _protected_app(SimpleNamespace(id=1, telegram_user_id=1, language="ru"))
    resp = tc.get("/test-auth")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication required"


def test_get_current_client_bad_cookie_401() -> None:
    tc = _protected_app(SimpleNamespace(id=1, telegram_user_id=1, language="ru"))
    resp = tc.get("/test-auth", cookies={"client_session": "not.a.jwt"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication required"


def test_get_current_client_unknown_session_client_401() -> None:
    """Valid token but no matching clients row → 401 (client resolved to None)."""
    from app.core.security import create_client_session_token

    tc = _protected_app(existing_client=None)  # db returns no client
    token = create_client_session_token(subject="99999")
    resp = tc.get("/test-auth", cookies={"client_session": token})
    assert resp.status_code == 401


# ── Integration: /webapp/auth router ───────────────────────────────────────────

def test_auth_config_returns_bot_username(client: TestClient) -> None:
    from app.core.config import settings

    with patch.object(settings, "BOT_USERNAME", "imex_ai_bot"):
        resp = client.get("/api/v1/webapp/auth/config")
    assert resp.status_code == 200
    assert resp.json()["bot_username"] == "imex_ai_bot"


def test_login_telegram_valid_sets_cookie(client: TestClient) -> None:
    from app.core.config import settings

    payload = _valid_widget(telegram_user_id=321)
    created = SimpleNamespace(id=1, telegram_user_id=321, language="ru")

    with patch.object(settings, "BOT_USERNAME", "imex_ai_bot"), patch(
        "app.services.client_service.get_or_create_client", return_value=created
    ):
        resp = client.post("/api/v1/webapp/auth/telegram", json=payload)

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert "client_session" in resp.cookies


def test_login_telegram_tampered_401(client: TestClient) -> None:
    from app.core.config import settings

    payload = _valid_widget(telegram_user_id=321)
    payload["hash"] = "00" * 32  # wrong

    with patch.object(settings, "BOT_USERNAME", "imex_ai_bot"):
        resp = client.post("/api/v1/webapp/auth/telegram", json=payload)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication required"


def test_login_telegram_disabled_when_no_username(client: TestClient) -> None:
    """With BOT_USERNAME unset (default in tests), browser login is disabled → 404."""
    payload = _valid_widget(telegram_user_id=321)
    resp = client.post("/api/v1/webapp/auth/telegram", json=payload)
    assert resp.status_code == 404


def test_logout_clears_cookie(client: TestClient) -> None:
    resp = client.post("/api/v1/webapp/auth/logout")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# ── Integration: public featured offers ────────────────────────────────────────

def _fake_offer(offer_id: int) -> SimpleNamespace:
    """A stand-in for a SellerOffer ORM row (PublicFeaturedOffer uses from_attributes)."""
    return SimpleNamespace(
        id=offer_id,
        product_id=1,
        product_text="HDPE film grade",
        grade_text="F0863",
        polymer_type="HDPE",
        availability="in_stock",
        qty_available="25.000",
        qty_unit="MT",
        price="1180.00",
        currency="USD",
        incoterms="FCA",
        warehouse_city="Tashkent",
        country="UZ",
        published_at=None,
        files=[],
    )


def test_featured_public_no_auth_and_no_contact(client: TestClient) -> None:
    """GET /webapp/market/featured is public and never leaks seller contact fields."""
    with patch(
        "app.services.offer_service.list_catalog",
        return_value=[_fake_offer(1), _fake_offer(2)],
    ):
        resp = client.get("/api/v1/webapp/market/featured")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    for offer in body:
        assert "seller" not in offer
        assert "phone" not in offer
        assert "contact_name" not in offer
        assert "telegram_username" not in offer
    assert body[0]["polymer_type"] == "HDPE"
