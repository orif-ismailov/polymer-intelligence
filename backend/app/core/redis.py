"""Redis client dependency (R1 W3).

`get_redis` is a FastAPI dependency that yields a short-lived, string-decoding
sync Redis client (mirrors `get_db`). Used by the portal OTP endpoints; overridable
in tests via `dependency_overrides[get_redis]`.
"""

from __future__ import annotations

from collections.abc import Generator

import redis

from app.core.config import settings


def get_redis() -> Generator[redis.Redis, None, None]:  # type: ignore[type-arg]
    """Yield a Redis client (decode_responses=True) and close it after the request.

    NB: the return annotation is unsubscripted on purpose. FastAPI evaluates it at
    runtime via get_type_hints, and redis-py's runtime `Redis` class is not a real
    generic (`redis.Redis[str]` → TypeError). otp_service still sees `Redis[str]`
    (string annotations, never evaluated) for the mypy-strict gate.
    """
    client = redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=3,
        socket_timeout=3,
        decode_responses=True,
    )
    try:
        yield client
    finally:
        client.close()
