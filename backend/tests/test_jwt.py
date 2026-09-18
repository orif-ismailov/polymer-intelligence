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
from datetime import UTC

import pytest
from jose import JWTError


def test_create_access_token_has_access_type():
    """Access token has type='access' claim."""
    from app.core.security import create_access_token, decode_token

    token = create_access_token(subject="1")
    payload = decode_token(token, expected_type="access")
    assert payload["type"] == "access"


def test_create_access_token_encodes_subject_and_no_authorization_claim():
    """Access token encodes sub, and deliberately carries NO authorization claim.

    Authorization is read from the staff row on every request, so demoting or
    deactivating someone takes effect immediately rather than when their
    15-minute token expires.
    """
    from app.core.security import create_access_token, decode_token

    token = create_access_token(subject="42")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "42"
    assert "role" not in payload
    assert "is_admin" not in payload


def test_create_access_token_expires_in_15_minutes():
    """Access token expiry is approximately 15 minutes (800–910 seconds from now)."""
    from app.core.security import create_access_token, decode_token

    token = create_access_token(subject="1")
    payload = decode_token(token, expected_type="access")
    # exp should be roughly 15 min = 900 s from now
    remaining = payload["exp"] - int(time.time())
    assert 800 <= remaining <= 920, f"Access token expiry off: {remaining}s remaining"


def _abs_exp(days: int = 90) -> int:
    return int(time.time()) + days * 86400


def test_create_refresh_token_has_refresh_type():
    """Refresh token has type='refresh' claim."""
    from app.core.security import create_refresh_token, decode_token

    token = create_refresh_token(subject="1", fam="f", jti="j", abs_exp=_abs_exp())
    payload = decode_token(token, expected_type="refresh")
    assert payload["type"] == "refresh"


def test_create_refresh_token_encodes_subject():
    """Refresh token encodes the sub claim."""
    from app.core.security import create_refresh_token, decode_token

    token = create_refresh_token(subject="99", fam="f", jti="j", abs_exp=_abs_exp())
    payload = decode_token(token, expected_type="refresh")
    assert payload["sub"] == "99"


def test_create_refresh_token_expires_in_30_days():
    """The sliding window is 30 days for BOTH surfaces (IMEX-1).

    It was 7 for staff and 30 for the cabinet, which is the kind of difference
    nobody remembers and no screen shows.
    """
    from app.core.config import settings
    from app.core.security import create_refresh_token, decode_token

    token = create_refresh_token(subject="1", fam="f", jti="j", abs_exp=_abs_exp())
    payload = decode_token(token, expected_type="refresh")
    expected = settings.REFRESH_SESSION_TTL_DAYS * 24 * 60 * 60
    remaining = payload["exp"] - int(time.time())
    assert expected - 100 <= remaining <= expected + 100, (
        f"Refresh token expiry off: {remaining}s remaining, expected ~{expected}s"
    )


def test_refresh_token_carries_its_family_jti_and_absolute_cap():
    """The three claims the session machinery reads back on every refresh."""
    from app.core.security import create_refresh_token, decode_token

    cap = _abs_exp()
    token = create_refresh_token(subject="1", fam="fam-x", jti="jti-x", abs_exp=cap)
    payload = decode_token(token, expected_type="refresh")

    assert payload["fam"] == "fam-x"
    assert payload["jti"] == "jti-x"
    assert payload["abx"] == cap


def test_refresh_token_expiry_never_outlives_the_absolute_cap():
    """A session 2 days from its ceiling gets a 2-day token, not a 30-day one.

    The `abx` claim is checked on refresh, so a longer `exp` would not actually
    extend the session — but it would hand out a cookie that LOOKS valid for 28
    days after the session is dead, and the first thing anyone does when debugging
    a session bug is decode the token.
    """
    from app.core.security import create_refresh_token, decode_token

    cap = _abs_exp(days=2)
    token = create_refresh_token(subject="1", fam="f", jti="j", abs_exp=cap)
    payload = decode_token(token, expected_type="refresh")

    assert payload["exp"] <= cap


def test_portal_refresh_token_carries_the_same_claims():
    from app.core.security import create_portal_refresh_token, decode_token

    cap = _abs_exp()
    token = create_portal_refresh_token(
        subject="7", fam="fam-p", jti="jti-p", abs_exp=cap
    )
    payload = decode_token(token, expected_type="portal_refresh")

    assert payload["sub"] == "7"
    assert payload["fam"] == "fam-p"
    assert payload["jti"] == "jti-p"
    assert payload["abx"] == cap


def test_access_token_binds_to_its_session_when_given_a_family():
    """`fam` is what lets the step-up guard find the session behind an access token."""
    from app.core.security import create_access_token, create_portal_access_token, decode_token

    staff = decode_token(create_access_token(subject="1", fam="fam-s"), expected_type="access")
    portal = decode_token(
        create_portal_access_token(subject="7", fam="fam-p"), expected_type="portal_access"
    )

    assert staff["fam"] == "fam-s"
    assert portal["fam"] == "fam-p"


def test_an_access_token_minted_without_a_family_omits_the_claim():
    """Optional on purpose. Tokens minted before this shipped carry no `fam`, and a
    guard that cannot find a session must refuse rather than invent one — so the
    absent claim fails closed at the step-up gate and changes nothing else."""
    from app.core.security import create_access_token, decode_token

    payload = decode_token(create_access_token(subject="1"), expected_type="access")

    assert "fam" not in payload


def test_decode_token_rejects_tampered_signature():
    """A JWT with a tampered signature is rejected (raises an exception)."""
    from app.core.security import create_access_token, decode_token

    token = create_access_token(subject="1")
    # Tamper the last few chars of the signature segment
    parts = token.split(".")
    parts[-1] = parts[-1][:-4] + "XXXX"
    tampered = ".".join(parts)

    with pytest.raises(JWTError):
        decode_token(tampered, expected_type="access")


def test_decode_token_rejects_expired_token():
    """An expired token is rejected."""
    from datetime import datetime, timedelta

    from jose import jwt

    from app.core.config import settings

    # Manually create an already-expired token
    payload = {
        "sub": "1",
        "role": "admin",
        "type": "access",
        "exp": datetime.now(UTC) - timedelta(seconds=60),
        "iat": datetime.now(UTC) - timedelta(seconds=900),
    }
    expired_token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

    from app.core.security import decode_token

    with pytest.raises(JWTError):
        decode_token(expired_token, expected_type="access")


def test_decode_token_rejects_access_as_refresh():
    """An access token presented where a refresh token is expected is rejected."""
    from app.core.security import create_access_token, decode_token

    token = create_access_token(subject="1")

    with pytest.raises(JWTError):
        decode_token(token, expected_type="refresh")


def test_decode_token_rejects_refresh_as_access():
    """A refresh token presented where an access token is expected is rejected."""
    from app.core.security import create_refresh_token, decode_token

    token = create_refresh_token(subject="1", fam="f", jti="j", abs_exp=_abs_exp())

    with pytest.raises(JWTError):
        decode_token(token, expected_type="access")
