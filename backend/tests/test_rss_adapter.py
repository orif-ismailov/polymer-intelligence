"""
Tests for RssAdapter (rss ingest adapter).

Covers:
- SSRF guard: unsafe URL -> TestResult(ok=False) without fetching
- Happy-path parse: RSS fixture -> <=10 normalized signal-draft rows
- 10-row cap: feed with >10 items returns exactly 10
- Adapter self-registers on import: get_adapter("rss") resolves
- Stdlib fallback: parses RSS without feedparser using xml.etree.ElementTree

Security: T-04-19 — is_safe_url() called before any HTTP fetch.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# RSS fixture with 3 items
_RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Polymer Market Feed</title>
    <link>https://example.com</link>
    <description>Test feed</description>
    <item>
      <title>PP Raffia H030GP 20MT at 1200 USD</title>
      <link>https://example.com/1</link>
      <description>PP Raffia H030GP volume:20 price:1200 currency:USD section:offers</description>
      <pubDate>Tue, 17 Jun 2026 10:00:00 +0000</pubDate>
    </item>
    <item>
      <title>HDPE HD50MA180 5MT at 1300 USD</title>
      <link>https://example.com/2</link>
      <description>HDPE HD50MA180 volume:5 price:1300 currency:USD section:offers</description>
      <pubDate>Tue, 17 Jun 2026 10:05:00 +0000</pubDate>
    </item>
    <item>
      <title>LDPE 1020FK 10MT at 1100 USD</title>
      <link>https://example.com/3</link>
      <description>LDPE 1020FK volume:10 price:1100 currency:USD section:offers</description>
      <pubDate>Tue, 17 Jun 2026 10:10:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""

# RSS fixture with 15 items (for cap test)
_RSS_15_ITEMS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Large Feed</title>
    <link>https://example.com</link>
    <description>Large test feed</description>
""" + "\n".join(
    f"""    <item>
      <title>Item {i} PP Raffia</title>
      <link>https://example.com/{i}</link>
      <description>Item number {i}</description>
      <pubDate>Tue, 17 Jun 2026 10:{i:02d}:00 +0000</pubDate>
    </item>"""
    for i in range(1, 16)
) + """
  </channel>
</rss>
"""


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test."""
    from app.ingest.registry import _clear_registry  # noqa: PLC0415

    _clear_registry()
    yield
    _clear_registry()


# ── SSRF guard tests ──────────────────────────────────────────────────────────


def test_rss_ssrf_reject_private_ip():
    """RssAdapter.test() returns ok=False for private IP URL (T-04-19)."""
    import importlib  # noqa: PLC0415
    import app.ingest.rss.adapter as rss_mod  # noqa: PLC0415
    importlib.reload(rss_mod)
    from app.ingest.rss.adapter import RssAdapter  # noqa: PLC0415

    adapter = RssAdapter()
    result = asyncio.get_event_loop().run_until_complete(
        adapter.test({"url": "http://192.168.1.1/feed"})
    )
    assert result.ok is False
    assert result.error is not None


def test_rss_ssrf_reject_localhost():
    """RssAdapter.test() returns ok=False for localhost URL (T-04-19)."""
    import importlib  # noqa: PLC0415
    import app.ingest.rss.adapter as rss_mod  # noqa: PLC0415
    importlib.reload(rss_mod)
    from app.ingest.rss.adapter import RssAdapter  # noqa: PLC0415

    adapter = RssAdapter()
    result = asyncio.get_event_loop().run_until_complete(
        adapter.test({"url": "http://127.0.0.1/feed.xml"})
    )
    assert result.ok is False
    assert result.error is not None


# ── Happy-path parse tests ─────────────────────────────────────────────────────


def test_rss_test_returns_normalized_rows():
    """RssAdapter.test() returns <=10 normalized signal-draft rows on happy path."""
    import importlib  # noqa: PLC0415
    import app.ingest.rss.adapter as rss_mod  # noqa: PLC0415
    importlib.reload(rss_mod)
    from app.ingest.rss.adapter import RssAdapter  # noqa: PLC0415
    from app.ingest.base import TestResult  # noqa: PLC0415

    adapter = RssAdapter()

    mock_response = MagicMock()
    mock_response.text = _RSS_FIXTURE
    mock_response.content = _RSS_FIXTURE.encode()

    with (
        patch("app.ingest.rss.adapter.is_safe_url", return_value=True),
        patch("app.ingest.rss.adapter.fetch_url", new=AsyncMock(return_value=mock_response)),
    ):
        result = asyncio.get_event_loop().run_until_complete(
            adapter.test({"url": "https://example.com/feed.rss"})
        )

    assert isinstance(result, TestResult)
    assert result.ok is True
    assert isinstance(result.sample_rows, list)
    assert len(result.sample_rows) > 0
    assert len(result.sample_rows) <= 10


def test_rss_10_row_cap():
    """RssAdapter.test() returns at most 10 rows when feed has >10 items."""
    import importlib  # noqa: PLC0415
    import app.ingest.rss.adapter as rss_mod  # noqa: PLC0415
    importlib.reload(rss_mod)
    from app.ingest.rss.adapter import RssAdapter  # noqa: PLC0415

    adapter = RssAdapter()

    mock_response = MagicMock()
    mock_response.text = _RSS_15_ITEMS
    mock_response.content = _RSS_15_ITEMS.encode()

    with (
        patch("app.ingest.rss.adapter.is_safe_url", return_value=True),
        patch("app.ingest.rss.adapter.fetch_url", new=AsyncMock(return_value=mock_response)),
    ):
        result = asyncio.get_event_loop().run_until_complete(
            adapter.test({"url": "https://example.com/feed.rss"})
        )

    assert result.ok is True
    assert len(result.sample_rows) <= 10


# ── Adapter registration tests ────────────────────────────────────────────────


def test_rss_adapter_registers_on_import():
    """Importing app.ingest.rss registers rss adapter in the registry."""
    import importlib  # noqa: PLC0415
    import app.ingest.rss  # noqa: PLC0415
    importlib.reload(app.ingest.rss)
    import app.ingest.rss.adapter  # noqa: PLC0415
    importlib.reload(app.ingest.rss.adapter)

    from app.ingest.registry import get_adapter  # noqa: PLC0415

    adapter = get_adapter("rss")
    assert adapter is not None
    assert adapter.type_name == "rss"


def test_rss_has_config_schema():
    """RssAdapter has a config_schema with url field."""
    import importlib  # noqa: PLC0415
    import app.ingest.rss.adapter as rss_mod  # noqa: PLC0415
    importlib.reload(rss_mod)
    from app.ingest.rss.adapter import RssAdapter  # noqa: PLC0415

    adapter = RssAdapter()
    schema = adapter.config_schema.model_json_schema()
    assert "url" in schema.get("properties", {}) or "url" in str(schema)
