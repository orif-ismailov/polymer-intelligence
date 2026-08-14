"""`feed_bus.subscribe_feed_events` — the Redis half of the live-feed SSE stream.

Every test in `test_feed_sse.py` patches this function out to focus on framing
and auth, which is reasonable but left the subscriber itself with no coverage at
all. A bug lived there undetected as a result: the generator iterated
`pubsub.listen()`, which raises `redis.exceptions.TimeoutError` after ~5 seconds
of silence even with `socket_timeout=None`. An idle feed therefore died every 5
seconds and the browser's `EventSource` silently reconnected — the feed still
worked, so nothing looked wrong, while every open dashboard re-ran a JWT decode,
a StaffUser lookup and a fresh Redis connection twelve times a minute.

The subscriber now polls with `get_message(timeout=...)`, which returns None on
an idle tick instead of raising. These tests pin the two properties that
distinguishes the fix from the bug: an idle tick must not end the stream, and a
real message must still come through.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class _FakePubSub:
    """Minimal stand-in for `redis.asyncio.client.PubSub`.

    `get_message` replays a script of return values. `None` models the idle
    timeout — the case that used to be an exception.
    """

    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.subscribed_to: list[str] = []
        self.unsubscribed_from: list[str] = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed_to.append(channel)

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed_from.append(channel)

    async def aclose(self) -> None:
        self.closed = True

    async def get_message(self, **_kwargs: Any) -> Any:
        if not self._script:
            raise AssertionError("generator polled more times than the script allows")
        return self._script.pop(0)


class _FakeRedis:
    def __init__(self, pubsub: _FakePubSub) -> None:
        self._pubsub = pubsub
        self.closed = False

    def pubsub(self) -> _FakePubSub:
        return self._pubsub

    async def aclose(self) -> None:
        self.closed = True


async def _collect(script: list[Any], limit: int) -> tuple[list[str], _FakePubSub]:
    """Run the subscriber against a scripted pubsub, taking up to `limit` yields."""
    from app.core.feed_bus import subscribe_feed_events  # noqa: PLC0415

    fake_pubsub = _FakePubSub(script)
    fake_client = _FakeRedis(fake_pubsub)

    got: list[str] = []
    with patch("redis.asyncio.from_url", MagicMock(return_value=fake_client)):
        agen = subscribe_feed_events()
        try:
            async for item in agen:
                got.append(item)
                if len(got) >= limit:
                    break
        finally:
            await agen.aclose()
    return got, fake_pubsub


@pytest.mark.asyncio
async def test_idle_ticks_do_not_end_the_stream() -> None:
    """`get_message` returning None means "nothing yet", not "stream over".

    This is the regression: treating an idle poll as terminal (or letting it
    raise, as `listen()` did) is what killed the stream every 5 seconds.
    """
    got, _ = await _collect([None, None, None, _msg("signal:42")], limit=1)
    assert got == ["signal:42"], "an idle poll must not end the stream"


@pytest.mark.asyncio
async def test_message_payload_is_decoded_to_str() -> None:
    """Redis hands back bytes; the SSE frame needs a str."""
    got, _ = await _collect([_msg(b"signal:7")], limit=1)
    assert got == ["signal:7"]


@pytest.mark.asyncio
async def test_subscribes_and_cleans_up_the_channel() -> None:
    """The channel is subscribed on entry and released on exit.

    A leaked subscription is a leaked Redis connection per dashboard tab, which
    is the cost the 5-second reconnect loop was quietly paying.
    """
    from app.core.feed_bus import FEED_CHANNEL  # noqa: PLC0415

    _, pubsub = await _collect([_msg("signal:1")], limit=1)
    assert pubsub.subscribed_to == [FEED_CHANNEL]
    assert pubsub.unsubscribed_from == [FEED_CHANNEL]
    assert pubsub.closed


def _msg(data: str | bytes) -> dict[str, Any]:
    return {"type": "message", "channel": b"feed:new", "data": data}
