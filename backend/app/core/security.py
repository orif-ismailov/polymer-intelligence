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
import secrets
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

# REFRESH_TOKEN_EXPIRE_DAYS = 7 used to live here, and PORTAL_SESSION_TTL_DAYS = 30 in
# Settings, so the same product had two session policies depending on which door you
# came in by. Both are now `settings.REFRESH_SESSION_TTL_DAYS` (IMEX-1).


def new_family_id() -> str:
    """A refresh-token family id: one sign-in, however many rotations it survives."""
    return secrets.token_hex(16)


def new_jti() -> str:
    """A single refresh token's identity within its family."""
    return secrets.token_hex(16)


def _refresh_exp(now: datetime, abs_exp: int) -> datetime:
    """The sliding window, clamped so a token never outlives its family's ceiling.

    The clamp is cosmetic for security — `abx` is checked on every refresh, so a
    longer `exp` could not actually extend anything — and load-bearing for everyone
    who debugs a session by decoding its cookie.
    """
    sliding = now + timedelta(days=settings.REFRESH_SESSION_TTL_DAYS)
    ceiling = datetime.fromtimestamp(abs_exp, UTC)
    return min(sliding, ceiling)


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


def create_access_token(subject: str, *, fam: str | None = None) -> str:
    """Create a short-lived access JWT (15 minutes).

    The token carries:
    - sub: staff_user_id (string)
    - type: 'access' (used to prevent token-type confusion, T-03-03)
    - fam: the refresh-session family, when one is known (IMEX-1)
    - iat: issued-at timestamp
    - exp: expiry (15 minutes from now)

    `fam` is OPTIONAL, and that is a decision rather than convenience: it is what
    lets `require_recent_auth` find the session behind a bearer token, and a token
    minted without one simply cannot satisfy a step-up gate. Tokens issued before
    this shipped therefore fail closed on sensitive actions and behave exactly as
    before everywhere else, for the fifteen minutes they have left.

    No authorization claim is embedded. Every guard loads the staff row and reads
    `is_admin` from it, so revoking access takes effect on the next request
    instead of waiting out an unexpired token. The dashboard asks
    `GET /auth/me` rather than decoding the token.

    Args:
        subject: The staff_user.id as a string (used as JWT sub claim).

    Returns:
        A signed JWT access token string.
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if fam is not None:
        payload["fam"] = fam
    return str(jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM))


def create_refresh_token(subject: str, *, fam: str, jti: str, abs_exp: int) -> str:
    """Create a rotating refresh JWT for the staff surface.

    The token carries:
    - sub: staff_user_id (string)
    - type: 'refresh' (used to prevent token-type confusion, T-03-03)
    - fam: the refresh-session family this token belongs to
    - jti: this token's identity — Redis holds exactly one live jti per family,
           which is what makes rotation, invalidation and reuse detection possible
    - abx: the ABSOLUTE session ceiling, fixed at sign-in
    - iat / exp: issued-at and the sliding window, clamped to `abx`

    `abx` is signed and copied UNCHANGED into every successor. That is what stops
    rotation from extending the ceiling, and it means the cap still holds even if
    Redis loses the family record entirely.

    Note: no authorization claim is included here either; it is read from the
    staff row on every request (see create_access_token).

    Args:
        subject: The staff_user.id as a string (used as JWT sub claim).
        fam: The family id (`security.new_family_id()`).
        jti: This token's id (`security.new_jti()`).
        abs_exp: Epoch seconds at which the session dies regardless of activity.

    Returns:
        A signed JWT refresh token string.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": "refresh",
        "fam": fam,
        "jti": jti,
        "abx": abs_exp,
        "iat": now,
        "exp": _refresh_exp(now, abs_exp),
    }
    return str(jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM))


def create_client_session_token(subject: str) -> str:
    """Create a browser client-session JWT for a Telegram-Login-Widget-authed client.

    Distinct from staff tokens: carries type='client_session' and role='client' so it
    can NEVER be replayed against staff endpoints (which decode with expected_type
    'access'/'refresh'). The subject is the client's telegram_user_id (as a string) —
    the same identity the Mini App initData path yields — so both auth paths resolve
    to the same Client row.

    Lifetime is settings.CLIENT_SESSION_TTL_SECONDS (default 30 days); low-privilege
    clients re-authenticate via the widget on expiry (no refresh flow).

    Args:
        subject: The client's telegram_user_id as a string (JWT sub claim).

    Returns:
        A signed JWT client-session token string.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": "client",
        "type": "client_session",
        "iat": now,
        "exp": now + timedelta(seconds=settings.CLIENT_SESSION_TTL_SECONDS),
    }
    return str(jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM))


def create_portal_access_token(subject: str, *, fam: str | None = None) -> str:
    """Create a short-lived portal access JWT (15 min) for a UserAccount.

    Audience isolation uses the SAME mechanism as staff/client tokens — the
    `type` claim (here `portal_access`), enforced by decode_token(expected_type=…).
    A portal token therefore fails on staff/webapp deps (which expect
    'access'/'client_session') and vice versa. We deliberately do NOT set a JWT
    `aud` claim: python-jose would then demand an `audience=` on every decode,
    breaking the shared decode_token. A random `jti` makes each token unique so
    refresh rotation yields an observably new token.

    Args:
        subject: The user_accounts.id as a string (JWT sub claim).

    Returns:
        A signed JWT portal access token string.
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": "account",
        "type": "portal_access",
        "jti": secrets.token_hex(8),
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if fam is not None:
        payload["fam"] = fam
    return str(jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM))


def create_portal_refresh_token(
    subject: str, *, fam: str, jti: str, abs_exp: int
) -> str:
    """Create a rotating portal refresh JWT. Same shape as the staff one.

    Delivered only via the httpOnly `portal_session` cookie. Carries
    type='portal_refresh' plus the family/jti/absolute-cap claims the session
    machinery reads back — see `create_refresh_token` for what each one is for.
    The role is re-read from the DB on refresh, so it is not embedded here.

    Args:
        subject: The user_accounts.id as a string (JWT sub claim).
        fam: The family id (`security.new_family_id()`).
        jti: This token's id (`security.new_jti()`).
        abs_exp: Epoch seconds at which the session dies regardless of activity.

    Returns:
        A signed JWT portal refresh token string.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": "portal_refresh",
        "fam": fam,
        "jti": jti,
        "abx": abs_exp,
        "iat": now,
        "exp": _refresh_exp(now, abs_exp),
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

    # T-03-03: enforce token-type claim to prevent cross-use of access/refresh tokens.
    # WR-04: do NOT echo the caller-supplied claim value back into the exception text —
    # only the server-known expected_type is included, so no attacker-controlled data
    # is reflected into logs or error responses.
    if raw_payload.get("type") != expected_type:
        raise JWTError(f"Token type mismatch: expected '{expected_type}'")

    return raw_payload
