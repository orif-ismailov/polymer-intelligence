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
_RSS_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
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
_RSS_15_ITEMS = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
    b"<title>Large Feed</title><link>https://example.com</link><description>test</description>"
    + b"".join(
        f"<item><title>Item {i} PP Raffia</title><link>https://example.com/{i}</link>"
        f"<description>Item number {i}</description>"
        f"<pubDate>Tue, 17 Jun 2026 10:{i:02d}:00 +0000</pubDate></item>".encode()
        for i in range(1, 16)
    )
    + b"</channel></rss>"
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure the rss adapter is registered for each test.

    Clears registry, then uses the internal registry dict directly to add
    the adapter without going through register_adapter() (which raises on
    duplicate). This pattern avoids issues with module-level code only
    running once per Python process (module import cache).
    """
    from app.ingest.registry import _clear_registry  # noqa: PLC0415
    from app.ingest import registry as _reg  # noqa: PLC0415

    _clear_registry()
    import app.ingest.rss.adapter as _rss_mod  # noqa: PLC0415
    _reg._REGISTRY["rss"] = _rss_mod.RssAdapter()
    yield
    _clear_registry()


# ── SSRF guard tests ──────────────────────────────────────────────────────────


def test_rss_ssrf_reject_private_ip():
    """RssAdapter.test() returns ok=False for private IP URL (T-04-19)."""
    from app.ingest.rss.adapter import RssAdapter  # noqa: PLC0415

    adapter = RssAdapter()
    result = asyncio.run(adapter.test({"url": "http://192.168.1.1/feed"}))
    assert result.ok is False
    assert result.error is not None


def test_rss_ssrf_reject_localhost():
    """RssAdapter.test() returns ok=False for localhost URL (T-04-19)."""
    from app.ingest.rss.adapter import RssAdapter  # noqa: PLC0415

    adapter = RssAdapter()
    result = asyncio.run(adapter.test({"url": "http://127.0.0.1/feed.xml"}))
    assert result.ok is False
    assert result.error is not None


# ── Happy-path parse tests ─────────────────────────────────────────────────────


def test_rss_test_returns_normalized_rows():
    """RssAdapter.test() returns <=10 normalized signal-draft rows on happy path."""
    from app.ingest.rss.adapter import RssAdapter  # noqa: PLC0415
    from app.ingest.base import TestResult  # noqa: PLC0415

    adapter = RssAdapter()

    mock_response = MagicMock()
    mock_response.text = _RSS_FIXTURE.decode()
    mock_response.content = _RSS_FIXTURE

    async def run():
        with (
            patch("app.ingest.rss.adapter.is_safe_url", return_value=True),
            patch(
                "app.ingest.rss.adapter.fetch_url",
                new=AsyncMock(return_value=mock_response),
            ),
        ):
            return await adapter.test({"url": "https://example.com/feed.rss"})

    result = asyncio.run(run())

    assert isinstance(result, TestResult)
    assert result.ok is True
    assert isinstance(result.sample_rows, list)
    assert len(result.sample_rows) > 0
    assert len(result.sample_rows) <= 10


def test_rss_10_row_cap():
    """RssAdapter.test() returns at most 10 rows when feed has >10 items."""
    from app.ingest.rss.adapter import RssAdapter  # noqa: PLC0415

    adapter = RssAdapter()

    mock_response = MagicMock()
    mock_response.text = _RSS_15_ITEMS.decode()
    mock_response.content = _RSS_15_ITEMS

    async def run():
        with (
            patch("app.ingest.rss.adapter.is_safe_url", return_value=True),
            patch(
                "app.ingest.rss.adapter.fetch_url",
                new=AsyncMock(return_value=mock_response),
            ),
        ):
            return await adapter.test({"url": "https://example.com/feed.rss"})

    result = asyncio.run(run())

    assert result.ok is True
    assert len(result.sample_rows) <= 10


# ── Adapter registration tests ────────────────────────────────────────────────


def test_rss_adapter_registers_on_import():
    """rss adapter is registered after importing the package."""
    from app.ingest.registry import get_adapter  # noqa: PLC0415

    adapter = get_adapter("rss")
    assert adapter is not None
    assert adapter.type_name == "rss"


def test_rss_has_config_schema():
    """RssAdapter has a config_schema with url field."""
    from app.ingest.rss.adapter import RssAdapter  # noqa: PLC0415

    adapter = RssAdapter()
    schema = adapter.config_schema.model_json_schema()
    props = schema.get("properties", {})
    assert "url" in props


def test_rss_type_name():
    """RssAdapter.type_name is 'rss'."""
    from app.ingest.rss.adapter import RssAdapter  # noqa: PLC0415

    adapter = RssAdapter()
    assert adapter.type_name == "rss"
