"""
Tests for GET /api/v1/feed/stream — SSE live feed stream.

Wave-0 scaffold: these tests go RED until Task 2 ships the router.

Covers:
- GET /feed/stream returns content-type: text/event-stream
- GET /feed/stream returns header X-Accel-Buffering: no (Pitfall 3 — nginx buffering)
- GET /feed/stream without a valid JWT returns 401 (T-04-01 auth guard)
- SSE generator yields `data: {id}\\n\\n` format frames

Security invariants:
- T-04-01: 401 returned when no Bearer token is present
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_staff_user(is_admin: bool = True, user_id: int = 1) -> MagicMock:
    """Return a MagicMock that quacks like a StaffUser ORM object."""

    user = MagicMock()
    user.id = user_id
    user.email = f"staff{user_id}@polymer.uz"
    user.is_admin = is_admin
    user.is_active = True
    return user


def _auth_headers(user_id: int = 1) -> dict[str, str]:
    """Create a Bearer Authorization header with a valid access token."""
    from app.core.security import create_access_token  # noqa: PLC0415

    token = create_access_token(subject=str(user_id))
    return {"Authorization": f"Bearer {token}"}


def _make_sse_client(staff_user: MagicMock | None = None) -> TestClient:
    """Build a TestClient with the db and staff user dep overridden for SSE tests."""
    from app.api.deps import get_current_staff_user  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    if staff_user is None:
        staff_user = _make_staff_user()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = staff_user

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    def _override_get_current_staff_user() -> Any:
        return staff_user

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_current_staff_user] = _override_get_current_staff_user

    return TestClient(application, raise_server_exceptions=True)


async def _fake_subscribe_one_event() -> Any:
    """Async generator that yields one fake ID then stops (for monkeypatching)."""
    yield "signal:42"


# ── GET /api/v1/feed/stream — SSE headers ─────────────────────────────────────


class TestFeedSSE:
    """SSE endpoint header and content-type tests."""

    def test_sse_returns_text_event_stream_content_type(self) -> None:
        """GET /feed/stream returns content-type: text/event-stream."""
        client = _make_sse_client()

        with patch("app.api.health._check_redis", return_value="ok"), \
             patch("app.domains.signals.api_feed.subscribe_feed_events", return_value=_fake_subscribe_one_event()):
            resp = client.get("/api/v1/feed/stream", headers=_auth_headers())

        assert resp.status_code == 200, resp.text
        content_type = resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type, (
            f"Expected text/event-stream, got: {content_type}"
        )

    def test_sse_returns_x_accel_buffering_no_header(self) -> None:
        """GET /feed/stream returns X-Accel-Buffering: no (prevents nginx buffering, Pitfall 3)."""
        client = _make_sse_client()

        with patch("app.api.health._check_redis", return_value="ok"), \
             patch("app.domains.signals.api_feed.subscribe_feed_events", return_value=_fake_subscribe_one_event()):
            resp = client.get("/api/v1/feed/stream", headers=_auth_headers())

        assert resp.status_code == 200, resp.text
        accel_header = resp.headers.get("x-accel-buffering", "")
        assert accel_header.lower() == "no", (
            f"Expected X-Accel-Buffering: no, got: {accel_header!r}"
        )

    def test_sse_emits_data_frame_format(self) -> None:
        """SSE stream emits frames in `data: {id}\\n\\n` format."""
        client = _make_sse_client()

        with patch("app.api.health._check_redis", return_value="ok"), \
             patch("app.domains.signals.api_feed.subscribe_feed_events", return_value=_fake_subscribe_one_event()):
            resp = client.get("/api/v1/feed/stream", headers=_auth_headers())

        assert resp.status_code == 200, resp.text
        # The response body should contain an SSE frame
        body = resp.text
        assert "data: " in body, f"Expected SSE data frame in body, got: {body!r}"

    def test_sse_emits_entity_id_in_frame(self) -> None:
        """SSE stream emits the entity ID published to feed:new."""
        client = _make_sse_client()

        with patch("app.api.health._check_redis", return_value="ok"), \
             patch("app.domains.signals.api_feed.subscribe_feed_events", return_value=_fake_subscribe_one_event()):
            resp = client.get("/api/v1/feed/stream", headers=_auth_headers())

        body = resp.text
        assert "signal:42" in body, f"Expected 'signal:42' in SSE body, got: {body!r}"

    def test_sse_returns_no_cache_header(self) -> None:
        """GET /feed/stream returns Cache-Control: no-cache.

        Set by FastAPI's SSE layer rather than by our handler, which is exactly
        why it is asserted here: the route no longer names it, so nothing else
        would notice if an upgrade stopped emitting it and a proxy began caching
        a stream that must never be cached.
        """
        client = _make_sse_client()

        with patch("app.api.health._check_redis", return_value="ok"), \
             patch("app.domains.signals.api_feed.subscribe_feed_events", return_value=_fake_subscribe_one_event()):
            resp = client.get("/api/v1/feed/stream", headers=_auth_headers())

        assert "no-cache" in resp.headers.get("cache-control", "").lower()

    def test_sse_emits_keepalive_while_idle(self) -> None:
        """An idle stream emits a comment frame instead of going silent.

        This is the behaviour the endpoint was switched to `EventSourceResponse`
        for. A feed with no traffic used to send nothing at all, so nginx's
        `proxy_read_timeout 60s` closed it and every open dashboard tab silently
        reconnected once a minute — paying a JWT decode, a StaffUser load and a
        new Redis connection each time. It reproduces only behind nginx, so a
        test is the only place it is cheaply observable.

        `_PING_INTERVAL` is documented in `fastapi/sse.py` as private-but-
        importable precisely so tests can shorten it.
        """
        client = _make_sse_client()

        async def _idle_then_stop() -> Any:
            """Idle long enough for one ping, then end the stream."""
            import anyio  # noqa: PLC0415

            await anyio.sleep(0.05)
            yield "signal:7"

        with patch("app.api.health._check_redis", return_value="ok"), \
             patch("fastapi.routing._PING_INTERVAL", 0.01), \
             patch("app.domains.signals.api_feed.subscribe_feed_events", return_value=_idle_then_stop()):
            resp = client.get("/api/v1/feed/stream", headers=_auth_headers())

        assert resp.status_code == 200, resp.text
        # A comment frame is a line starting with ':' — invisible to EventSource
        # consumers but enough to keep the connection alive through a proxy.
        # Match the line exactly: a substring check for ":" also matches
        # "data: signal:7" and would pass on a stream with no keep-alive at all.
        lines = resp.text.split("\n")
        assert any(ln.startswith(": ") for ln in lines), (
            f"expected a keep-alive comment frame in an idle stream, got: {resp.text!r}"
        )
        assert "data: signal:7" in resp.text  # and the real event still arrives


# ── GET /api/v1/feed/stream — 401 without token ───────────────────────────────


class TestFeedSSEAuth:
    """Authentication gate tests for GET /feed/stream (T-04-01)."""

    def test_no_token_returns_401(self) -> None:
        """GET /feed/stream without Authorization header → 401 (T-04-01)."""
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        def _override_get_db() -> Generator[Any, None, None]:
            yield mock_db

        application = create_app()
        application.dependency_overrides[get_db] = _override_get_db

        with patch("app.api.health._check_redis", return_value="ok"), \
                TestClient(application, raise_server_exceptions=False) as tc:
            resp = tc.get("/api/v1/feed/stream")

        assert resp.status_code == 401, resp.text


# ── Admin gate on the SSE route ───────────────────────────────────────────────
#
# The stream needs its own guard (`require_admin_sse`) rather than the Bearer-only
# `require_admin` every other route uses: `EventSource` cannot set an
# Authorization header, so the token arrives as a query parameter. Stacking the
# Bearer guard here would have rejected every browser that connected — and no
# header-based test would have noticed.


class TestSseAdminGate:
    """GET /feed/stream is administrator-only, on BOTH auth paths."""

    def test_admin_allowed_via_query_param(self) -> None:
        """An admin token supplied as ?access_token= is accepted — the EventSource path."""
        from app.core.security import create_access_token  # noqa: PLC0415

        client = _make_sse_client()
        token = create_access_token(subject="1")

        with patch("app.api.health._check_redis", return_value="ok"), \
             patch("app.domains.signals.api_feed.subscribe_feed_events", return_value=_fake_subscribe_one_event()):
            resp = client.get(f"/api/v1/feed/stream?access_token={token}")

        assert resp.status_code == 200, resp.text

    def test_non_admin_rejected_via_query_param(self) -> None:
        """A valid non-administrator token is refused on the query-param path too."""
        from app.core.security import create_access_token  # noqa: PLC0415

        client = _make_sse_client(_make_staff_user(is_admin=False))
        token = create_access_token(subject="1")

        with patch("app.api.health._check_redis", return_value="ok"), \
             patch("app.domains.signals.api_feed.subscribe_feed_events", return_value=_fake_subscribe_one_event()):
            resp = client.get(f"/api/v1/feed/stream?access_token={token}")

        assert resp.status_code == 403, resp.text

    def test_non_admin_rejected_via_header(self) -> None:
        """The header path is gated identically."""
        client = _make_sse_client(_make_staff_user(is_admin=False))

        with patch("app.api.health._check_redis", return_value="ok"), \
             patch("app.domains.signals.api_feed.subscribe_feed_events", return_value=_fake_subscribe_one_event()):
            resp = client.get("/api/v1/feed/stream", headers=_auth_headers())

        assert resp.status_code == 403, resp.text

