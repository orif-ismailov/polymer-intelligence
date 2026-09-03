"""Per-company Didox sessions — the 360-minute wall (P7.a Stage 2 — W5).

Every Didox call carries two tokens: our `Partner-Authorization` (a server-side
secret) and a `user-key` identifying the acting company. The second one is the
awkward half:

  * it can only be minted with **that company's own E-IMZO key**, in that
    company's own browser — there is no server-side path for someone else's
    company;
  * it is a UUID, so no expiry can be read out of it;
  * it dies after 360 minutes.

Which makes a cache miss a **domain condition**, not an error: the answer is "ask
the user to sign again", surfaced as `UserKeyRequired` → HTTP 409. Falling back to
`auth_by_password` here would use OUR service credentials to act as somebody else's
company, and would spend attempts against a ladder whose last rung is a permanent
block — so `require_user_key` never mints, and minting has its own explicit door.

The UX rule that keeps the wall from wedging anything lives in the portal: a Didox
action never asks for a session as a separate ceremony. On a miss it mints and then
CONTINUES to the original action — the user is already at the machine with a card
inserted, because they were about to sign something anyway.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from app.integrations.didox.auth import KEY_TTL_SECONDS, USER_KEY_CACHE
from app.integrations.didox.client import get_didox_client

if TYPE_CHECKING:  # pragma: no cover
    import redis

    from app.domains.companies.models import Company

logger = logging.getLogger(__name__)


class _Minter(Protocol):
    """The slice of `DidoxClient` this module needs — keeps the tests honest."""

    def timestamp(self, pkcs7_64: str, signature_hex: str) -> str: ...
    def auth_by_eimzo(self, tax_id: str, signature: str, locale: str = ...) -> str: ...


class UserKeyRequired(Exception):
    """No live Didox session for this company; the user must sign again.

    Deliberately NOT an auth failure (401 means "you are not signed into the
    portal") and NOT an outage (503 means something is down). It is 409
    `didox_session_required`: a precondition the user can satisfy in one click.
    """

    def __init__(self, tax_id: str) -> None:
        super().__init__(f"no cached didox user-key for {tax_id}")
        self.tax_id = tax_id


def cached_user_key(redis_client: redis.Redis[str] | None, tax_id: str) -> str | None:
    """Read-only. Never mints — that is the entire point of the split."""
    if redis_client is None:
        return None
    try:
        value = redis_client.get(USER_KEY_CACHE.format(tin=tax_id))
    except Exception as exc:  # noqa: BLE001 — Redis must not decide whether we can act
        logger.warning("didox.session.cache_unavailable", extra={"error": str(exc)})
        return None
    return str(value) if value else None


def require_user_key(
    redis_client: redis.Redis[str] | None,
    company: Company,
    *,
    client: _Minter | None = None,  # noqa: ARG001 — accepted so callers can pass one uniformly
) -> str:
    """The company's live `user-key`, or `UserKeyRequired`.

    `client` is accepted and ignored on purpose: a caller should be able to hand
    the same client to every function in this module, and the fact that this one
    can never use it is a property worth making visible rather than hiding behind
    a different signature.
    """
    key = cached_user_key(redis_client, company.tax_id)
    if not key:
        raise UserKeyRequired(company.tax_id)
    return key


def cache_user_key(redis_client: redis.Redis[str] | None, tax_id: str, token: str) -> None:
    """Hold a freshly minted key.

    TTL is well under the provider's 360 minutes: a key that expires mid-request
    surfaces as a 401 the caller cannot distinguish from a bad token.
    """
    if redis_client is None:
        return
    try:
        redis_client.setex(USER_KEY_CACHE.format(tin=tax_id), KEY_TTL_SECONDS, token)
    except Exception as exc:  # noqa: BLE001 — a cache miss costs one signature, not correctness
        logger.warning("didox.session.cache_write_failed", extra={"error": str(exc)})


def mint_user_key(
    redis_client: redis.Redis[str] | None,
    company: Company,
    *,
    pkcs7_64: str,
    signature_hex: str,
    client: _Minter | None = None,
) -> str:
    """Mint from a browser signature over the company's INN, and cache it.

    The signature must be TIMESTAMPED before Didox will accept it as auth — a bare
    PKCS#7 is refused by every endpoint that takes a `signature` — so the TSA round
    trip happens here rather than being left to the caller to remember.
    """
    didox = client or get_didox_client()
    token = didox.auth_by_eimzo(company.tax_id, didox.timestamp(pkcs7_64, signature_hex))
    cache_user_key(redis_client, company.tax_id, token)
    return token
