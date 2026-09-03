"""Redis clients.

`get_redis` is a FastAPI dependency that yields a short-lived, string-decoding
sync Redis client (mirrors `get_db`). Used by the portal OTP endpoints; overridable
in tests via `dependency_overrides[get_redis]`.

`signal_client()` is the other shape: a long-lived, process-wide client for the
tiny out-of-band reads that happen on a HOT path and must never be the reason a
request is slow. Today that is one caller — the settings-override generation
counter (`app/services/settings_service.py`), read once per request and once per
Celery task.
"""

from __future__ import annotations

from collections.abc import Generator

import redis

from app.core.config import settings

#: How long `signal_client()` will wait on Redis, in seconds.
#:
#: Deliberately two orders of magnitude below `get_redis`'s 3 s. That client
#: serves OTP endpoints, where three seconds of patience is right; this one is
#: consulted before ordinary requests, so the same patience would put a 3 s stall
#: on every company lookup for as long as Redis was unwell. A quarter second is
#: long enough for a healthy local Redis and short enough to be invisible — and
#: the caller backs off entirely after a failure rather than paying it again.
SIGNAL_TIMEOUT_SECONDS = 0.25

_signal_client: redis.Redis | None = None  # type: ignore[type-arg]


def signal_client() -> redis.Redis:  # type: ignore[type-arg]
    """A process-wide Redis client for small, latency-critical signal reads.

    Built once and reused: this is called on every request, and constructing a
    client per call would spend a TCP handshake to read one integer.

    Deliberately NOT one of the two clients that already exist. `get_redis` is a
    per-request FastAPI dependency and cannot be reached from a Celery task at
    all; `parsing.budget`'s singleton is `decode_responses=False` and is patched
    wholesale by the budget tests, so borrowing it would couple an unrelated
    subsystem's cache to those fixtures.
    """
    global _signal_client
    if _signal_client is None:
        _signal_client = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=SIGNAL_TIMEOUT_SECONDS,
            socket_timeout=SIGNAL_TIMEOUT_SECONDS,
            decode_responses=True,
        )
    return _signal_client


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
