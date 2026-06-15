"""
Security helpers: argon2 password hashing and JWT issue/verify.

DEC-auth-split: JWT dashboard (access 15 min + refresh 7 d httpOnly cookie)
Passwords are hashed with argon2-cffi (salted, never plaintext).
JWT tokens are signed with HS256 using JWT_SECRET.

REQ-nfr-security: plaintext passwords never stored or logged.
T-03-01: argon2-cffi hashing (salted); login returns generic 401 (no user-enumeration).
T-03-02: JWT signed with JWT_SECRET; tampered tokens rejected.
T-03-03: type claim distinguishes access vs refresh; cross-use rejected.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import settings

# ── Argon2 password hasher ─────────────────────────────────────────────────────
# Using recommended parameters; time_cost=2, memory_cost=65536 (64 MB), parallelism=2
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

# ── Timing-attack mitigation: precomputed real dummy hash ──────────────────────
# CR-05 / T-03-01: a REAL argon2 hash computed once at import.
# When a login attempt arrives for a non-existent user, dummy_verify() is called
# so the unknown-user path performs the SAME full KDF work as a wrong-password path.
# The old approach used a malformed hash string ("$argon2id$...dummysalt$dummyhash")
# which raised InvalidHashError immediately (no KDF work done), making the
# user-not-found path dramatically faster than the wrong-password path and
# reintroducing the user-enumeration timing oracle.
_DUMMY_HASH = _hasher.hash("timing-attack-mitigation-dummy")

# ── JWT constants ──────────────────────────────────────────────────────────────
_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


def hash_password(plain: str) -> str:
    """Hash a plaintext password using argon2.

    Returns an argon2 hash string (starts with $argon2id).
    Never stores or returns plaintext.

    Args:
        plain: The plaintext password to hash.

    Returns:
        The argon2 hash string.
    """
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against an argon2 hash.

    Returns True if the password matches the hash, False otherwise.
    Never raises on mismatch — returns False instead (safe for auth flows).

    Args:
        plain: The plaintext password to verify.
        hashed: The argon2 hash to verify against.

    Returns:
        True if the password matches, False otherwise.
    """
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def dummy_verify(plain: str) -> None:
    """Perform real argon2 KDF work against the precomputed dummy hash.

    CR-05 / T-03-01: called on the user-not-found path in authenticate() so the
    timing of a login attempt for a non-existent user converges with the timing of
    a wrong-password attempt for a valid user.

    The verify call will ALWAYS fail (VerifyMismatchError) because no real user
    ever has a password that hashes to _DUMMY_HASH — but the full argon2 KDF work
    IS performed (salted, iterated), preventing the timing oracle.

    Does NOT raise — the mismatch is expected and swallowed.

    Args:
        plain: The candidate plaintext password (the attacker's guess).
    """
    # Expected: the real dummy hash will never match any attacker-supplied password.
    # We still performed full argon2 KDF work — that is the whole point.
    with contextlib.suppress(VerifyMismatchError, VerificationError):
        _hasher.verify(_DUMMY_HASH, plain)


def create_access_token(subject: str, role: str) -> str:
    """Create a short-lived access JWT (15 minutes).

    The token carries:
    - sub: staff_user_id (string)
    - role: the staff_role value (e.g. 'admin', 'analyst', 'trader', 'viewer')
    - type: 'access' (used to prevent token-type confusion, T-03-03)
    - iat: issued-at timestamp
    - exp: expiry (15 minutes from now)

    Args:
        subject: The staff_user.id as a string (used as JWT sub claim).
        role: The staff_role value (admin/analyst/trader/viewer).

    Returns:
        A signed JWT access token string.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return str(jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM))


def create_refresh_token(subject: str) -> str:
    """Create a long-lived refresh JWT (7 days).

    The token carries:
    - sub: staff_user_id (string)
    - type: 'refresh' (used to prevent token-type confusion, T-03-03)
    - iat: issued-at timestamp
    - exp: expiry (7 days from now)

    Note: the role is NOT included in the refresh token; it is re-read from
    the DB on refresh to pick up any role changes.

    Args:
        subject: The staff_user.id as a string (used as JWT sub claim).

    Returns:
        A signed JWT refresh token string.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return str(jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM))


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Verifies:
    1. Signature (rejects tampered tokens, T-03-02)
    2. Expiry (rejects expired tokens)
    3. Token type claim matches expected_type (rejects type-confusion, T-03-03)

    Args:
        token: The JWT string to decode.
        expected_type: The expected value of the 'type' claim ('access' or 'refresh').

    Returns:
        The decoded payload dict if all checks pass.

    Raises:
        JWTError: If the signature is invalid, the token is expired, or the
                  token type does not match expected_type.
    """
    try:
        raw_payload: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[_ALGORITHM],
        )
    except JWTError as exc:
        raise JWTError(f"Token validation failed: {exc}") from exc

    # T-03-03: enforce token-type claim to prevent cross-use of access/refresh tokens
    token_type = raw_payload.get("type")
    if token_type != expected_type:
        raise JWTError(
            f"Token type mismatch: expected '{expected_type}', got '{token_type}'"
        )

    return raw_payload
