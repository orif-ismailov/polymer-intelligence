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
    """
    import redis.asyncio  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415

    client = redis.asyncio.from_url(settings.REDIS_URL)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(FEED_CHANNEL)
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    yield data.decode("utf-8")
                else:
                    yield str(data)
    finally:
        await pubsub.unsubscribe(FEED_CHANNEL)
        await pubsub.aclose()
        await client.aclose()
