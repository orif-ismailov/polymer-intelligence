"""
Tests for per-source 7-day token spend in the admin sources API.

Verifies:
- SourceOut schema has a token_spend_7d: int field
- AI adapter sources return per_source_spend from budget module
- Non-AI sources return token_spend_7d = 0
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Schema test
# ---------------------------------------------------------------------------


def test_source_health_item_has_token_spend_7d():
    """SourceHealthItem (admin/sources/health response) must have token_spend_7d: int field."""
    from app.api.admin_sources import SourceHealthItem  # noqa: PLC0415

    fields = SourceHealthItem.model_fields
    assert "token_spend_7d" in fields, (
        f"token_spend_7d missing from SourceHealthItem; fields: {list(fields.keys())}"
    )
    field = fields["token_spend_7d"]
    annotation = field.annotation
    # Should be int
    import typing
    args = typing.get_args(annotation)
    inner = args[0] if args else annotation
    assert inner is int or annotation is int, (
        f"token_spend_7d should be int, got: {annotation}"
    )


# ---------------------------------------------------------------------------
# Endpoint behavior: AI sources return real spend
# ---------------------------------------------------------------------------


def test_ai_source_returns_token_spend_7d():
    """get_sources_health returns token_spend_7d > 0 for telegram_channel sources."""
    from app.api.admin_sources import get_sources_health  # noqa: PLC0415

    mock_db = MagicMock()
    # Simulate one telegram_channel source row
    mock_row = (
        1,                          # id
        "Test Channel",             # name
        "telegram_channel",         # adapter
        "telegram_channel",         # kind
        True,                       # is_enabled
        None,                       # last_fetch_at
        None,                       # last_success_at
        0,                          # consecutive_failures
    )
    mock_db.execute.return_value.fetchall.return_value = [mock_row]
    mock_user = MagicMock()

    with patch("app.api.admin_sources.per_source_spend", return_value=1500) as mock_spend:
        items = get_sources_health(_current_user=mock_user, db=mock_db)

    assert len(items) == 1
    item = items[0]
    assert item.token_spend_7d == 1500
    mock_spend.assert_called_once()


def test_non_ai_source_returns_zero_token_spend():
    """get_sources_health returns token_spend_7d=0 for non-AI sources."""
    from app.api.admin_sources import get_sources_health  # noqa: PLC0415

    mock_db = MagicMock()
    # Simulate one UZEX source row
    mock_row = (
        2,                          # id
        "UZEX Feed",                # name
        "uzex_offers",              # adapter  (non-AI)
        "exchange",                 # kind
        True,                       # is_enabled
        None,                       # last_fetch_at
        None,                       # last_success_at
        0,                          # consecutive_failures
    )
    mock_db.execute.return_value.fetchall.return_value = [mock_row]
    mock_user = MagicMock()

    with patch("app.api.admin_sources.per_source_spend", return_value=9999):
        items = get_sources_health(_current_user=mock_user, db=mock_db)

    assert len(items) == 1
    item = items[0]
    # Non-AI source should return 0 regardless of per_source_spend
    assert item.token_spend_7d == 0


def test_llm_page_source_returns_token_spend():
    """llm_page adapter is also an AI source type — should return real spend."""
    from app.api.admin_sources import get_sources_health  # noqa: PLC0415

    mock_db = MagicMock()
    mock_row = (
        3,
        "LLM Page Source",
        "llm_page",             # adapter — AI type
        "website",
        True,
        None,
        None,
        0,
    )
    mock_db.execute.return_value.fetchall.return_value = [mock_row]

    with patch("app.api.admin_sources.per_source_spend", return_value=800) as mock_spend:
        items = get_sources_health(_current_user=MagicMock(), db=mock_db)

    assert items[0].token_spend_7d == 800
    mock_spend.assert_called_once()
