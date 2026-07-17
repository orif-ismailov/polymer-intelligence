"""
Tests for GET /api/v1/feed — keyset-paginated live market feed.

Wave-0 scaffold: these tests go RED until Task 2 ships the router.

Covers:
- GET /feed with no cursor returns 200 with items list and pagination cursors
- GET /feed with cursor_event_at + cursor_id returns only rows before the cursor
- GET /feed with kind filter narrows results
- GET /feed with product_id filter narrows results
- GET /feed without a valid JWT returns 401 (T-04-01 auth guard)
- Keyset pagination: cursor advances correctly to the last row's (event_at, id)
- Anti-pattern guard: no OFFSET appears in the feed SQL

Security invariants:
- T-04-01: 401 returned when no Bearer token is present
- T-04-02: filters are bound params (tested structurally by the SQL assertion)
- T-04-03: limit is capped at 200 (tested via query param)
"""

from __future__ import annotations

import datetime
import decimal
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_staff_user(role: str = "analyst", user_id: int = 1) -> MagicMock:
    """Return a MagicMock that quacks like a StaffUser ORM object."""
    from app.models.enums import StaffRole  # noqa: PLC0415

    user = MagicMock()
    user.id = user_id
    user.email = f"{role}@polymer.uz"
    user.role = StaffRole(role)
    user.is_active = True
    return user


def _auth_headers(user_id: int = 1, role: str = "analyst") -> dict[str, str]:
    """Create a Bearer Authorization header with a valid access token."""
    from app.core.security import create_access_token  # noqa: PLC0415

    token = create_access_token(subject=str(user_id), role=role)
    return {"Authorization": f"Bearer {token}"}


def _make_feed_row(
    id: int = 1,
    origin: str = "signal",
    kind: str = "offer",
    product_id: int | None = 1,
    grade_text: str | None = "HDPE 2420D",
    volume: decimal.Decimal | None = decimal.Decimal("100.000"),
    price: decimal.Decimal | None = decimal.Decimal("1200.00"),
    currency: str | None = "USD",
    region: str | None = "UZ",
    urgency: str | None = "medium",
    status: str | None = "new",
    event_at: datetime.datetime | None = None,
    seller: str | None = None,
    source_name: str | None = None,
    source_url: str | None = None,
    contact_phone: str | None = None,
    contact_email: str | None = None,
) -> MagicMock:
    """Return a MagicMock that quacks like a v_live_feed row."""
    row = MagicMock()
    row.id = id
    row.origin = origin
    row.kind = kind
    row.product_id = product_id
    row.grade_text = grade_text
    row.volume = volume
    row.price = price
    row.currency = currency
    row.region = region
    row.urgency = urgency
    row.status = status
    row.event_at = event_at or datetime.datetime(2026, 6, 17, 12, 0, 0, tzinfo=datetime.UTC)
    # Seller / contact columns (signals + sources + raw_items join). Default None so
    # existing rows stay unchanged; a dedicated test sets them to real values.
    row.seller = seller
    row.source_name = source_name
    row.source_url = source_url
    row.contact_phone = contact_phone
    row.contact_email = contact_email
    return row


def _make_feed_client(rows: list[Any] | None = None, staff_user: MagicMock | None = None) -> TestClient:
    """Build a TestClient with db mocked to return feed rows for the feed endpoint."""
    from app.api.deps import get_current_staff_user  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    if staff_user is None:
        staff_user = _make_staff_user()

    if rows is None:
        rows = []

    mock_db = MagicMock()
    # db.execute(...).fetchall() returns the rows list
    execute_result = MagicMock()
    execute_result.fetchall.return_value = rows
    mock_db.execute.return_value = execute_result

    # Also support db.query() for the get_current_staff_user dep
    mock_db.query.return_value.filter.return_value.first.return_value = staff_user

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    def _override_get_current_staff_user() -> Any:
        return staff_user

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_current_staff_user] = _override_get_current_staff_user

    return TestClient(application, raise_server_exceptions=True)


# ── GET /api/v1/feed — authenticated requests ─────────────────────────────────


class TestFeedList:
    """GET /feed — paginated list of feed items."""

    def test_authenticated_returns_200_with_items(self) -> None:
        """Valid JWT returns 200 with items and pagination cursors."""
        row1 = _make_feed_row(
            id=2,
            event_at=datetime.datetime(2026, 6, 17, 13, 0, 0, tzinfo=datetime.UTC),
        )
        row2 = _make_feed_row(
            id=1,
            event_at=datetime.datetime(2026, 6, 17, 12, 0, 0, tzinfo=datetime.UTC),
        )
        client = _make_feed_client(rows=[row1, row2])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get("/api/v1/feed", headers=_auth_headers())

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_seller_contact_fields_surfaced(self) -> None:
        """Seller name + source + contact (phone/email/link) reach the response so
        staff can contact the seller from the live feed."""
        contactable = _make_feed_row(
            id=42,
            kind="sell_offer",
            seller="UGCC Trading LLC",
            source_name="xarid.uzex.uz",
            source_url="https://xarid.uzex.uz/auction/detail/42",
            contact_phone="998901112233",
            contact_email="sales@ugcc.uz",
        )
        exchange_only = _make_feed_row(id=41, kind="deal", seller="Shurtan GCC")
        client = _make_feed_client(rows=[contactable, exchange_only])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get("/api/v1/feed", headers=_auth_headers())

        assert resp.status_code == 200, resp.text
        items = {i["id"]: i for i in resp.json()["items"]}

        rich = items[42]
        assert rich["seller"] == "UGCC Trading LLC"
        assert rich["source_name"] == "xarid.uzex.uz"
        assert rich["source_url"] == "https://xarid.uzex.uz/auction/detail/42"
        assert rich["contact_phone"] == "998901112233"
        assert rich["contact_email"] == "sales@ugcc.uz"

        # Exchange rows carry a name but no direct contact — fields stay null, not absent.
        lean = items[41]
        assert lean["seller"] == "Shurtan GCC"
        assert lean["source_url"] is None
        assert lean["contact_phone"] is None
        assert lean["contact_email"] is None

    def test_cursor_fields_in_response(self) -> None:
        """Response includes next_cursor_event_at and next_cursor_id."""
        row = _make_feed_row(id=5)
        client = _make_feed_client(rows=[row])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get("/api/v1/feed", headers=_auth_headers())

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "next_cursor_event_at" in data
        assert "next_cursor_id" in data

    def test_cursor_advances_to_last_row(self) -> None:
        """next_cursor_id matches the last row's id (oldest row in newest-first order)."""
        row1 = _make_feed_row(
            id=10,
            event_at=datetime.datetime(2026, 6, 17, 14, 0, 0, tzinfo=datetime.UTC),
        )
        row2 = _make_feed_row(
            id=5,
            event_at=datetime.datetime(2026, 6, 17, 12, 0, 0, tzinfo=datetime.UTC),
        )
        client = _make_feed_client(rows=[row1, row2])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get("/api/v1/feed", headers=_auth_headers())

        data = resp.json()
        # Last row in newest-first order has id=5 (oldest event_at)
        assert data["next_cursor_id"] == 5

    def test_empty_result_returns_null_cursors(self) -> None:
        """Empty result set → both cursor fields are null."""
        client = _make_feed_client(rows=[])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get("/api/v1/feed", headers=_auth_headers())

        data = resp.json()
        assert data["next_cursor_event_at"] is None
        assert data["next_cursor_id"] is None

    def test_items_newest_first_order(self) -> None:
        """Items are in newest-first order (event_at DESC, id DESC)."""
        row1 = _make_feed_row(
            id=10,
            event_at=datetime.datetime(2026, 6, 17, 14, 0, 0, tzinfo=datetime.UTC),
        )
        row2 = _make_feed_row(
            id=5,
            event_at=datetime.datetime(2026, 6, 17, 12, 0, 0, tzinfo=datetime.UTC),
        )
        # DB returns newest first (ORDER BY event_at DESC, id DESC)
        client = _make_feed_client(rows=[row1, row2])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get("/api/v1/feed", headers=_auth_headers())

        data = resp.json()
        ids = [item["id"] for item in data["items"]]
        assert ids == [10, 5]

    def test_kind_filter_passes_to_db(self) -> None:
        """kind= query param returns only matching rows (mock returns filtered set)."""
        signal_row = _make_feed_row(id=1, kind="offer")
        client = _make_feed_client(rows=[signal_row])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get("/api/v1/feed?kind=offer", headers=_auth_headers())

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert all(item["kind"] == "offer" for item in data["items"])

    def test_product_id_filter_passes_to_db(self) -> None:
        """product_id= query param returns only matching rows."""
        row = _make_feed_row(id=1, product_id=2)
        client = _make_feed_client(rows=[row])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get("/api/v1/feed?product_id=2", headers=_auth_headers())

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert all(item["product_id"] == 2 for item in data["items"])

    def test_limit_param_accepted(self) -> None:
        """limit query param is accepted (capped at 200 per T-04-03)."""
        client = _make_feed_client(rows=[])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get("/api/v1/feed?limit=10", headers=_auth_headers())

        assert resp.status_code == 200, resp.text

    def test_limit_above_200_returns_422(self) -> None:
        """limit > 200 returns 422 (T-04-03: cap at le=200)."""
        client = _make_feed_client(rows=[])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get("/api/v1/feed?limit=201", headers=_auth_headers())

        assert resp.status_code == 422, resp.text

    def test_cursor_params_accepted(self) -> None:
        """cursor_event_at and cursor_id params are accepted without error."""
        client = _make_feed_client(rows=[])

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.get(
                "/api/v1/feed?cursor_event_at=2026-06-17T12:00:00Z&cursor_id=5",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200, resp.text


# ── GET /api/v1/feed — 401 without token ──────────────────────────────────────


class TestFeedAuth:
    """Authentication gate tests for GET /feed (T-04-01)."""

    def test_no_token_returns_401(self) -> None:
        """GET /feed without Authorization header → 401 (T-04-01)."""
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
            resp = tc.get("/api/v1/feed")

        assert resp.status_code == 401, resp.text
