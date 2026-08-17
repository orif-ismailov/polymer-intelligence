"""Didox `user-key` minting and caching (R6 / P7.a).

A `user-key` identifies the acting user/company. It is a **UUID, not a JWT** — no
expiry can be read out of it — and it dies after 360 minutes, so we cache it for
300 and re-mint on a miss.

There are three ways to mint one and only one of them works unattended:

  * by E-IMZO — needs the client's private key, which lives on their machine;
  * by password — the only server-side path, and the one used here;
  * "enter a company" — needs an individual's key first.

Which is why this module mints a key for **our own service account** only. It is
what makes the registry lookup work in production, where the endpoint refuses a
request that carries no user-key (the test contour does not ask for one).

**The password path is dangerous and is treated accordingly.** The lockout ladder
is 3 wrong attempts/minute → 10-minute block, 10 → 24 hours, 25 → **permanent**
(`reference/03-login.md`). So a failed mint writes a cooldown marker and every
caller in that window degrades instead of trying again. One attempt per cooldown,
never a loop, never a retry decorator.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.integrations.didox.client import DidoxClient, ProviderUnavailable, get_didox_client

if TYPE_CHECKING:  # pragma: no cover
    import redis

logger = logging.getLogger(__name__)

#: Well under the provider's 360-minute TTL — a key that expires mid-request
#: would surface as a 401 the caller cannot distinguish from a bad token.
KEY_TTL_SECONDS = 300 * 60
#: How long to stay away after a failed password login. Deliberately long: the
#: ladder's punishments escalate to permanent, and a lookup is never worth that.
FAILURE_COOLDOWN_SECONDS = 3600

_KEY = "didox:user_key:{tin}"
_COOLDOWN = "didox:user_key_cooldown:{tin}"


def service_user_key(
    redis_client: redis.Redis[str] | None,
    *,
    client: DidoxClient | None = None,
) -> str | None:
    """A cached `user-key` for the platform's own Didox account, or `None`.

    `None` is a normal answer, not an error: no service credentials configured,
    a cooldown after a failed attempt, or Didox being unreachable. The caller
    proceeds without the header — which the test contour accepts and production
    refuses with a 401 that the gateway already turns into `ProviderUnavailable`.
    """
    from app.core.config import settings  # noqa: PLC0415 — lazy: import-safe module

    tin = settings.DIDOX_SERVICE_TIN.strip()
    password = settings.DIDOX_SERVICE_PASSWORD
    if not tin or not password:
        return None

    if redis_client is not None:
        try:
            cached = redis_client.get(_KEY.format(tin=tin))
            if cached:
                return str(cached)
            if redis_client.get(_COOLDOWN.format(tin=tin)):
                logger.info("didox.auth.cooldown", extra={"tin": tin})
                return None
        except Exception as exc:  # noqa: BLE001 — Redis must not decide whether we can look up
            logger.warning("didox.auth.cache_unavailable", extra={"error": str(exc)})

    try:
        token = (client or get_didox_client()).auth_by_password(tin, password)
    except ProviderUnavailable as exc:
        logger.warning("didox.auth.unavailable", extra={"error": str(exc)})
        return None
    except Exception as exc:  # noqa: BLE001 — a 4xx here is a wrong/blocked credential
        logger.warning("didox.auth.rejected", extra={"error": str(exc)})
        _cooldown(redis_client, tin)
        return None

    if redis_client is not None:
        try:
            redis_client.setex(_KEY.format(tin=tin), KEY_TTL_SECONDS, token)
        except Exception as exc:  # noqa: BLE001
            logger.warning("didox.auth.cache_write_failed", extra={"error": str(exc)})
    return token


def _cooldown(redis_client: Any, tin: str) -> None:  # noqa: ANN401
    """Stop trying. A second wrong password is how a 10-minute block becomes a
    permanent one."""
    if redis_client is None:
        return
    try:
        redis_client.setex(_COOLDOWN.format(tin=tin), FAILURE_COOLDOWN_SECONDS, "1")
    except Exception as exc:  # noqa: BLE001
        logger.warning("didox.auth.cooldown_write_failed", extra={"error": str(exc)})
