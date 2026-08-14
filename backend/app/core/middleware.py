"""Request-scoped correlation ID.

Every log line the app emits already passes through
`structlog.contextvars.merge_contextvars` (see `configure_logging`), so binding a
value into the contextvar here makes it appear on every subsequent line for that
request — including lines from libraries that know nothing about this module.
Before this, a failure in a 20-domain app produced JSON logs with no way to tell
which lines belonged to the same request, or to connect an api log to the Celery
task it spawned.

WHY A RAW ASGI MIDDLEWARE, NOT BaseHTTPMiddleware
-------------------------------------------------
Starlette's `BaseHTTPMiddleware` wraps the response in an anyio task group and
consumes the body stream to re-emit it. That is fine for JSON and fatal for
`text/event-stream`: it defeats incremental flushing, which is the entire point
of the live-feed SSE endpoint (and of the keep-alive frames that stop nginx
dropping it). A raw ASGI middleware passes `send` through untouched, so a
streaming response stays streaming. Do not "simplify" this into
`@app.middleware("http")` — that is `BaseHTTPMiddleware` under a friendlier name.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

import structlog
from starlette.datastructures import Headers, MutableHeaders

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

#: Inbound header honoured so a trace started at the edge (nginx, a load balancer,
#: another service) keeps its id through this app.
REQUEST_ID_HEADER = "x-request-id"

#: An inbound id is caller-controlled and lands in logs, so it is bounded and
#: restricted rather than trusted. Log processors here emit JSON, so a newline
#: could otherwise forge a whole log record; the charset below excludes it, along
#: with anything else that is not plausibly an id.
_MAX_ID_LENGTH = 64
_ID_ALPHABET = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)


def _clean_request_id(raw: str | None) -> str:
    """Return a safe request id: the caller's if it is plausible, else a new one."""
    if not raw:
        return uuid.uuid4().hex
    candidate = raw.strip()[:_MAX_ID_LENGTH]
    if candidate and all(ch in _ID_ALPHABET for ch in candidate):
        return candidate
    return uuid.uuid4().hex


class RequestIdMiddleware:
    """Bind a request id into the structlog context and echo it on the response."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Lifespan and websocket scopes have no headers to read or set.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _clean_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        # bind_contextvars returns tokens for precise reset. Resetting rather than
        # clearing matters because contextvars are shared with whatever else runs
        # in this task; unbinding only our key leaves other bindings alone.
        tokens = structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            await self.app(scope, receive, send_with_header)
        finally:
            structlog.contextvars.reset_contextvars(**tokens)
