"""Request-id correlation middleware.

Two things are being protected here. The obvious one is that every response
carries an id and every log line for that request can be joined on it. The
less obvious one is that adding a middleware at all must not break the SSE feed:
`BaseHTTPMiddleware` consumes and re-emits the response body, which defeats
incremental flushing and would silently undo the live-feed keep-alive work.

A note on how that second one is actually tested, because the obvious approach
does not work. Swapping `RequestIdMiddleware` for a `BaseHTTPMiddleware` and
running the SSE tests here passes — `TestClient` reads the whole response body
before handing it over, so buffering is invisible to it (verified, not assumed).
A behavioural test would need a live server and frame-arrival timing, which was
confirmed by hand instead: `curl -N` against a running server shows keep-alive
frames arriving incrementally.

So the guard that CAN run in-process is structural —
`test_no_buffering_middleware_in_the_stack` asserts the class is absent from the
stack — and `test_sse_still_streams_through_the_middleware` covers the weaker
but still useful claim that SSE responses remain correct and get an id.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import structlog
from fastapi.testclient import TestClient

from app.core.middleware import REQUEST_ID_HEADER, _clean_request_id


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    app = create_app()
    db = MagicMock()

    def _override_db() -> Iterator[MagicMock]:
        yield db

    app.dependency_overrides[get_db] = _override_db
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as c:
        yield c


# ── Header behaviour ──────────────────────────────────────────────────────────


def test_response_carries_a_request_id(client: TestClient) -> None:
    """Every response gets an id, so a user can quote one from a bug report."""
    resp = client.get("/api/v1/health")
    assert resp.headers.get(REQUEST_ID_HEADER)


def test_inbound_id_is_preserved(client: TestClient) -> None:
    """A trace started at the edge keeps its id through this app."""
    resp = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: "edge-trace-123"})
    assert resp.headers[REQUEST_ID_HEADER] == "edge-trace-123"


def test_ids_differ_between_requests(client: TestClient) -> None:
    first = client.get("/api/v1/health").headers[REQUEST_ID_HEADER]
    second = client.get("/api/v1/health").headers[REQUEST_ID_HEADER]
    assert first != second


# ── Untrusted input ───────────────────────────────────────────────────────────
#
# The inbound header is caller-controlled and its value is written into JSON log
# lines, so a newline in it could forge an entire log record. These cases are the
# reason `_clean_request_id` exists rather than passing the header through.


@pytest.mark.parametrize(
    "hostile",
    [
        'evil"}\n{"level":"info","event":"forged',  # log-record injection
        "a\r\nX-Injected: 1",  # header splitting
        "../../etc/passwd",
        "  ",  # whitespace only
        "id with spaces",
    ],
)
def test_hostile_inbound_ids_are_replaced(hostile: str) -> None:
    """Anything outside the id alphabet is discarded for a fresh uuid."""
    cleaned = _clean_request_id(hostile)
    assert cleaned != hostile
    assert len(cleaned) == 32  # a fresh uuid4 hex
    assert cleaned.isalnum()


def test_overlong_id_is_truncated_not_rejected() -> None:
    """A long-but-valid id is bounded rather than thrown away.

    The concern with length is that the value is repeated on every log line for
    the request, so it must not be unbounded. Truncating satisfies that while
    keeping the prefix, which is still worth something for correlation — whereas
    replacing it would silently break a trace that an upstream edge started.
    """
    cleaned = _clean_request_id("a" * 500)
    assert len(cleaned) == 64
    assert cleaned == "a" * 64


def test_hostile_header_does_not_reach_the_response(client: TestClient) -> None:
    resp = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: "bad value!"})
    assert resp.headers[REQUEST_ID_HEADER] != "bad value!"


def test_plausible_ids_are_kept_verbatim() -> None:
    """Real trace ids (uuid, dashes, dots) must survive — sanitising is not rejecting."""
    for good in ["abc123", "550e8400-e29b-41d4-a716-446655440000", "trace.1_2-3"]:
        assert _clean_request_id(good) == good


# ── Context binding ───────────────────────────────────────────────────────────


def test_request_id_is_bound_for_logging_and_unbound_after(client: TestClient) -> None:
    """The id reaches structlog's context during the request, and is gone after.

    `merge_contextvars` is already the first processor in `configure_logging`, so
    binding here is what puts `request_id` on every log line for the request. The
    unbind half matters just as much: a leaked contextvar would stamp the NEXT
    request's logs with the previous request's id, which is worse than no id.
    """
    seen: list[Any] = []

    real_get = structlog.contextvars.get_contextvars

    def _capture() -> Any:
        value = real_get()
        seen.append(dict(value))
        return value

    with patch.object(structlog.contextvars, "get_contextvars", _capture):
        # Anything inside the request can observe the bound context.
        resp = client.get("/api/v1/health")
        during = structlog.contextvars.get_contextvars()

    assert resp.status_code == 200
    # After the response, our key is gone from the ambient context.
    assert "request_id" not in during


def test_contextvar_does_not_leak_between_requests(client: TestClient) -> None:
    client.get("/api/v1/health", headers={REQUEST_ID_HEADER: "first-request"})
    assert structlog.contextvars.get_contextvars().get("request_id") != "first-request"


def test_request_id_reaches_a_log_line_from_inside_the_handler() -> None:
    """The whole point: a log emitted while serving carries the request's id.

    Asserted end-to-end through the real processor chain rather than by checking
    the contextvar, because the binding is only useful if
    `merge_contextvars` actually folds it into the rendered event — and that
    depends on `configure_logging`'s processor order, which lives in a different
    module and could change without this middleware changing at all.

    (Note this covers APP loggers. Uvicorn configures `uvicorn.access` with
    propagate=False, so its access lines bypass the structlog chain entirely and
    stay plain text — pre-existing, and out of scope here.)
    """
    from fastapi import FastAPI  # noqa: PLC0415

    from app.core.middleware import RequestIdMiddleware  # noqa: PLC0415

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    seen: dict[str, Any] = {}

    # A SYNC handler on purpose. ~287 of the app's 291 path operations are sync
    # `def` and therefore run in AnyIO's worker threadpool, not on the event loop
    # where the middleware did the binding. contextvars are copied into that
    # thread by anyio, but that is the link most likely to be wrong, and if it
    # broke, the id would silently vanish from nearly every log line in the app.
    @app.get("/probe")
    def probe() -> dict[str, str]:
        seen.update(structlog.contextvars.get_contextvars())
        return {"ok": "yes"}

    with TestClient(app) as c:
        resp = c.get("/probe", headers={REQUEST_ID_HEADER: "trace-abc"})

    assert resp.status_code == 200
    assert seen.get("request_id") == "trace-abc", (
        f"the id did not reach the sync handler's context: {seen}"
    )

    # And the chain that turns that context into log output is actually wired:
    # `merge_contextvars` must run, or the binding above renders nowhere.
    from app.core.logging import configure_logging  # noqa: PLC0415

    configure_logging()
    processors = structlog.get_config()["processors"]
    assert structlog.contextvars.merge_contextvars in processors, (
        "merge_contextvars missing from the structlog chain — request_id would be "
        "bound but never rendered onto any log line"
    )


# ── The streaming guarantee ───────────────────────────────────────────────────


def test_no_buffering_middleware_in_the_stack() -> None:
    """No `BaseHTTPMiddleware` may be installed, because SSE has to stream.

    A structural assertion rather than a behavioural one, deliberately: see the
    module docstring. `BaseHTTPMiddleware` buffers the response body, which kills
    incremental flushing for `text/event-stream` — and an in-process client
    cannot observe the difference, so this is the only form of the check that
    actually fails when someone reaches for `@app.middleware("http")` (which is
    `BaseHTTPMiddleware` wearing a friendlier name).
    """
    from starlette.middleware.base import BaseHTTPMiddleware  # noqa: PLC0415

    from app.main import create_app  # noqa: PLC0415

    offenders = [
        m.cls.__name__
        for m in create_app().user_middleware
        if isinstance(m.cls, type) and issubclass(m.cls, BaseHTTPMiddleware)
    ]
    assert not offenders, (
        f"BaseHTTPMiddleware subclasses installed: {offenders}. These buffer the "
        "response body and break SSE streaming (/api/v1/feed/stream). Write a raw "
        "ASGI middleware instead — see app/core/middleware.py."
    )


def test_sse_still_streams_through_the_middleware() -> None:
    """SSE responses stay correct, and get an id, with the middleware installed.

    Weaker than it looks — `TestClient` buffers, so this cannot detect a loss of
    incremental flushing (that is `test_no_buffering_middleware_in_the_stack`'s
    job). What it does cover is that the middleware has not broken SSE framing,
    content type, or the anti-buffering header on the way past.
    """
    from tests.test_feed_sse import (  # noqa: PLC0415
        _auth_headers,
        _fake_subscribe_one_event,
        _make_sse_client,
    )

    sse_client = _make_sse_client()
    with patch("app.api.health._check_redis", return_value="ok"), patch(
        "app.domains.signals.api_feed.subscribe_feed_events",
        return_value=_fake_subscribe_one_event(),
    ):
        resp = sse_client.get("/api/v1/feed/stream", headers=_auth_headers())

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    assert resp.headers.get("x-accel-buffering", "").lower() == "no"
    assert "data: signal:42" in resp.text
    assert resp.headers.get(REQUEST_ID_HEADER), "streaming responses get an id too"
