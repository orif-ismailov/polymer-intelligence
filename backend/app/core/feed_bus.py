"""
Redis pub/sub helper for the live feed SSE endpoint.

Phase 4, Plan 01: Feed bus for real-time event notification.

Publishes new entity IDs to the `feed:new` channel after signal/request creation.
The SSE endpoint subscribes and yields `data: {id}\\n\\n` frames to connected browsers.

Design notes:
- All Redis imports are deferred into function bodies (lazy imports) so that
  this module can be imported at pytest collection time without a running Redis
  or socket activity (mirrors the lazy-import convention from request_service.py).
- The async client is created per-call with `redis.asyncio.from_url(settings.REDIS_URL)`.
  For the subscribe generator this is acceptable since SSE connections are long-lived;
  one client per connected browser is the expected pattern.
- FEED_CHANNEL is the canonical constant; never hardcode the string elsewhere.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

# Constant — the single Redis pub/sub channel name for new feed events.
FEED_CHANNEL = "feed:new"

#: How long one `get_message` poll waits before returning None and looping.
#: Only affects how promptly the generator notices cancellation on client
#: disconnect — delivery of a real message is still immediate, not polled.
_POLL_TIMEOUT_SECONDS = 1.0


async def publish_feed_event(entity_ref: str) -> None:
    """Publish a new feed event to the Redis `feed:new` channel.

    Args:
        entity_ref: A string identifying the new entity, e.g. "signal:42"
                    or a bare numeric ID string. The SSE client uses this to
                    trigger a feed refresh (queryClient.invalidateQueries).

    The function is intentionally fire-and-forget: publish errors are logged
    but not raised so a Redis hiccup does not fail the entity creation path.
    """
    import logging  # noqa: PLC0415

    import redis.asyncio  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415

    logger = logging.getLogger(__name__)
    client = redis.asyncio.from_url(settings.REDIS_URL)
    try:
        await client.publish(FEED_CHANNEL, entity_ref)
    except Exception:  # noqa: BLE001
        logger.exception("feed_bus.publish_failed", extra={"entity_ref": entity_ref})
    finally:
        await client.aclose()


async def subscribe_feed_events() -> AsyncGenerator[str, None]:
    """Async generator that yields decoded messages from the `feed:new` channel.

    Intended for use inside the SSE event generator in feed.py:

        async for msg in subscribe_feed_events():
            yield f"data: {msg}\\n\\n"

    The generator runs as long as the SSE connection is open. When the client
    disconnects, FastAPI cancels the generator coroutine; the try/finally block
    ensures the pubsub and client are closed.

    Each yielded value is the raw decoded message string published by
    `publish_feed_event`.

    Polls with `get_message(timeout=...)` rather than iterating `pubsub.listen()`.
    That is not a style preference — `listen()` raises
    `redis.exceptions.TimeoutError: Timeout reading from ...` after ~5 seconds of
    silence, even with `socket_timeout=None` and no health check configured
    (reproduced standalone against redis-py's asyncio client, outside this app).
    The exception killed the generator, so an idle stream died after 5s and the
    browser's EventSource reconnected — every 5 seconds, for every open dashboard,
    each reconnect paying for a JWT decode, a StaffUser lookup and a fresh Redis
    connection. It was invisible because EventSource reconnects silently and the
    feed still worked.

    `get_message` RETURNS None on timeout instead of raising, so the loop simply
    goes round again. Verified: 20s idle with no exception, and a message
    published at t+8s still arrives.
    """
    import redis.asyncio  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415

    client = redis.asyncio.from_url(settings.REDIS_URL)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(FEED_CHANNEL)
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=_POLL_TIMEOUT_SECONDS
            )
            if message is None:  # idle tick, not a disconnect
                continue
            if message.get("type") == "message":
                data = message["data"]
                yield data.decode("utf-8") if isinstance(data, bytes) else str(data)
    finally:
        await pubsub.unsubscribe(FEED_CHANNEL)
        await pubsub.aclose()
        await client.aclose()
