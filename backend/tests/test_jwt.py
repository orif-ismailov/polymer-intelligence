"""
Tests for JWT token helpers in app.core.security.

Covers:
- create_access_token encodes role + subject, type='access', expires in ~15 min
- create_refresh_token encodes subject, type='refresh', expires in ~7 d
- decode_token returns claims for valid token
- decode_token rejects tampered signature
- decode_token rejects expired token
- Token-type confusion: access token rejected where refresh is expected and vice-versa
"""

from __future__ import annotations

import time

import pytest


def test_create_access_token_has_access_type():
    """Access token has type='access' claim."""
    from app.core.security import create_access_token, decode_token

    token = create_access_token(subject="1", role="admin")
    payload = decode_token(token, expected_type="access")
    assert payload["type"] == "access"


def test_create_access_token_encodes_subject_and_role():
    """Access token encodes sub (staff_user_id) and role."""
    from app.core.security import create_access_token, decode_token

    token = create_access_token(subject="42", role="analyst")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "42"
    assert payload["role"] == "analyst"


def test_create_access_token_expires_in_15_minutes():
    """Access token expiry is approximately 15 minutes (800–910 seconds from now)."""
    from app.core.security import create_access_token, decode_token

    token = create_access_token(subject="1", role="viewer")
    payload = decode_token(token, expected_type="access")
    # exp should be roughly 15 min = 900 s from now
    remaining = payload["exp"] - int(time.time())
    assert 800 <= remaining <= 920, f"Access token expiry off: {remaining}s remaining"


def test_create_refresh_token_has_refresh_type():
    """Refresh token has type='refresh' claim."""
    from app.core.security import create_refresh_token, decode_token

    token = create_refresh_token(subject="1")
    payload = decode_token(token, expected_type="refresh")
    assert payload["type"] == "refresh"


def test_create_refresh_token_encodes_subject():
    """Refresh token encodes the sub claim."""
    from app.core.security import create_refresh_token, decode_token

    token = create_refresh_token(subject="99")
    payload = decode_token(token, expected_type="refresh")
    assert payload["sub"] == "99"


def test_create_refresh_token_expires_in_7_days():
    """Refresh token expiry is approximately 7 days (604400–605300 seconds from now)."""
    from app.core.security import create_refresh_token, decode_token

    token = create_refresh_token(subject="1")
    payload = decode_token(token, expected_type="refresh")
    seven_days_seconds = 7 * 24 * 60 * 60
    remaining = payload["exp"] - int(time.time())
    # Allow ±100 s tolerance for clock skew/execution time
    assert seven_days_seconds - 100 <= remaining <= seven_days_seconds + 100, (
        f"Refresh token expiry off: {remaining}s remaining, expected ~{seven_days_seconds}s"
    )


def test_decode_token_rejects_tampered_signature():
    """A JWT with a tampered signature is rejected (raises an exception)."""
    from app.core.security import create_access_token, decode_token

    token = create_access_token(subject="1", role="admin")
    # Tamper the last few chars of the signature segment
    parts = token.split(".")
    parts[-1] = parts[-1][:-4] + "XXXX"
    tampered = ".".join(parts)

    with pytest.raises(Exception):
        decode_token(tampered, expected_type="access")


def test_decode_token_rejects_expired_token():
    """An expired token is rejected."""
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app.core.config import settings

    # Manually create an already-expired token
    payload = {
        "sub": "1",
        "role": "admin",
        "type": "access",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=60),
        "iat": datetime.now(timezone.utc) - timedelta(seconds=900),
    }
    expired_token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

    from app.core.security import decode_token

    with pytest.raises(Exception):
        decode_token(expired_token, expected_type="access")


def test_decode_token_rejects_access_as_refresh():
    """An access token presented where a refresh token is expected is rejected."""
    from app.core.security import create_access_token, decode_token

    token = create_access_token(subject="1", role="admin")

    with pytest.raises(Exception):
        decode_token(token, expected_type="refresh")


def test_decode_token_rejects_refresh_as_access():
    """A refresh token presented where an access token is expected is rejected."""
    from app.core.security import create_refresh_token, decode_token

    token = create_refresh_token(subject="1")

    with pytest.raises(Exception):
        decode_token(token, expected_type="access")
