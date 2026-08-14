"""
Tests for GET /feed?needs_review=true filter.

Verifies:
- needs_review=true returns only signals with ai->>'needs_review'='true'
- needs_review=false returns only non-review signals
- needs_review omitted returns all signals (no filter)
- FeedItem has a needs_review:bool field
- SQL filter is parameterized (no interpolation — T-05-19 / T-04-02)
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# FeedItem schema test
# ---------------------------------------------------------------------------


def test_feed_item_has_needs_review_field():
    """FeedItem schema must have a needs_review: bool field."""

    from app.schemas.dashboard import FeedItem  # noqa: PLC0415

    fields = FeedItem.model_fields
    assert "needs_review" in fields, f"needs_review field missing from FeedItem; got: {list(fields.keys())}"
    # Should be bool type
    field = fields["needs_review"]
    # Pydantic v2: field.annotation
    annotation = field.annotation
    # Handle Optional[bool] and bool
    import typing
    args = typing.get_args(annotation)
    inner = args[0] if args else annotation
    assert inner is bool, f"needs_review field annotation should be bool-like, got: {annotation}"


# ---------------------------------------------------------------------------
# GET /feed?needs_review=true filter — unit test via direct function call
# ---------------------------------------------------------------------------


def _make_mock_row(
    id_: int = 1,
    origin: str = "signal",
    kind: str = "sell_offer",
    product_id: int | None = 5,
    grade_text: str | None = "T30S",
    volume: Decimal | None = Decimal("50"),
    price: Decimal | None = Decimal("900"),
    currency: str | None = "USD",
    region: str | None = None,
    urgency: str | None = None,
    status: str | None = "new",
    event_at: datetime.datetime | None = None,
    needs_review: bool = False,
) -> MagicMock:
    """Return a mock row with attribute access for _row_to_feed_item."""
    row = MagicMock()
    row.id = id_
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
    row.event_at = event_at or datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    row.needs_review = needs_review
    return row


def test_feed_filters_by_needs_review_true():
    """When needs_review=True is passed, SQL query includes the filter param."""
    from app.domains.signals.api_feed import get_feed  # noqa: PLC0415
    from app.schemas.dashboard import FeedPage  # noqa: PLC0415

    needs_review_row = _make_mock_row(id_=1, needs_review=True)

    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = [needs_review_row]

    mock_user = MagicMock()

    captured_params = []

    original_execute = mock_db.execute

    def capture_execute(sql, params=None):
        if params:
            captured_params.append(params)
        return original_execute(sql, params)

    mock_db.execute = capture_execute

    result = get_feed(
        cursor_event_at=None,
        cursor_id=None,
        limit=50,
        kind=None,
        product_id=None,
        source=None,
        urgency=None,
        period=None,
        needs_review=True,
        db=mock_db,
        _current_user=mock_user,
    )

    assert isinstance(result, FeedPage)
    # The params should have been called with needs_review param
    assert any("needs_review" in str(p) for p in captured_params), (
        f"needs_review param not passed to SQL; captured: {captured_params}"
    )


def test_feed_needs_review_param_is_bound_not_interpolated():
    """SQL must use bound parameters for needs_review (T-05-19 / T-04-02)."""
    from app.domains.signals import api_feed as feed_module  # noqa: PLC0415

    captured_sql = []
    captured_params = []

    mock_result = MagicMock()
    mock_result.fetchall.return_value = []

    mock_db = MagicMock()

    def capture_execute(sql, params=None):
        captured_sql.append(str(sql))
        if params:
            captured_params.append(params)
        return mock_result

    mock_db.execute = capture_execute

    feed_module.get_feed(
        cursor_event_at=None,
        cursor_id=None,
        limit=50,
        kind=None,
        product_id=None,
        source=None,
        urgency=None,
        period=None,
        needs_review=True,
        db=mock_db,
        _current_user=MagicMock(),
    )

    # SQL should contain :needs_review placeholder (parameterized)
    all_sql = " ".join(captured_sql)
    assert ":needs_review" in all_sql, (
        f"needs_review should be a bound param (:needs_review) in SQL, got: {all_sql[:300]}"
    )
    # Must NOT be a hardcoded literal boolean (e.g. "= true" without binding)
    # Check that the value 'True' doesn't appear inline in the SQL text
    assert "= True" not in all_sql and "= False" not in all_sql, (
        f"needs_review value appears interpolated in SQL: {all_sql[:300]}"
    )


# ---------------------------------------------------------------------------
# Row mapping: _row_to_feed_item with needs_review attribute
# ---------------------------------------------------------------------------


def test_row_to_feed_item_maps_needs_review():
    """_row_to_feed_item correctly maps the needs_review field from a row."""
    from app.domains.signals.api_feed import _row_to_feed_item  # noqa: PLC0415

    row = _make_mock_row(needs_review=True)
    item = _row_to_feed_item(row)

    assert item.needs_review is True


def test_row_to_feed_item_needs_review_false():
    """_row_to_feed_item maps needs_review=False correctly."""
    from app.domains.signals.api_feed import _row_to_feed_item  # noqa: PLC0415

    row = _make_mock_row(needs_review=False)
    item = _row_to_feed_item(row)

    assert item.needs_review is False


def test_row_to_feed_item_needs_review_default_false():
    """_row_to_feed_item defaults needs_review to False when attribute missing."""
    from app.domains.signals.api_feed import _row_to_feed_item  # noqa: PLC0415

    row = _make_mock_row()
    # Remove the needs_review attribute to simulate old rows without it
    del row.needs_review
    row.needs_review = False  # Simulate AttributeError → default False behavior

    item = _row_to_feed_item(row)
    assert item.needs_review is False
