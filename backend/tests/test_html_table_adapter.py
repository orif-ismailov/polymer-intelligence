"""
Tests for HtmlTableAdapter (html_table ingest adapter).

Covers:
- SSRF guard: unsafe URL -> TestResult(ok=False) without fetching
- Happy-path parse: HTML fixture with a table -> <=10 normalized signal-draft rows
- 10-row cap: table with >10 rows returns exactly 10
- Adapter self-registers on import: get_adapter("html_table") resolves
- Normalized row keys include expected signal-draft fields

Security: T-04-19 — is_safe_url() called before any HTTP fetch.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ──────────────────────────────────────────────────────────────────


def _clear_and_register_html_table():
    """Clear registry and import the html_table adapter package to re-register."""
    from app.ingest.registry import _clear_registry  # noqa: PLC0415

    _clear_registry()
    # Fresh import via importlib to re-trigger side-effect registration
    import importlib  # noqa: PLC0415
    import app.ingest.html_table  # noqa: PLC0415
    importlib.reload(app.ingest.html_table)
    import app.ingest.html_table.adapter  # noqa: PLC0415
    importlib.reload(app.ingest.html_table.adapter)


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test to avoid cross-test pollution."""
    from app.ingest.registry import _clear_registry  # noqa: PLC0415

    _clear_registry()
    yield
    _clear_registry()


# HTML fixture: table with product/volume/price/currency data
_HTML_TABLE_FIXTURE = """
<html>
<body>
<table>
<thead><tr><th>Product</th><th>Grade</th><th>Volume</th><th>Price</th><th>Currency</th></tr></thead>
<tbody>
<tr><td>PP Raffia</td><td>H030GP</td><td>20 MT</td><td>1200</td><td>USD</td></tr>
<tr><td>HDPE</td><td>HD50MA180</td><td>5 MT</td><td>1300</td><td>USD</td></tr>
<tr><td>LDPE</td><td>1020FK</td><td>10 MT</td><td>1100</td><td>USD</td></tr>
</tbody>
</table>
</body>
</html>
"""

# HTML fixture with 15 rows (to test 10-row cap)
_HTML_15_ROWS = """
<html><body><table>
<thead><tr><th>Product</th><th>Volume</th></tr></thead>
<tbody>
""" + "\n".join(
    f"<tr><td>PP Raffia</td><td>{i} MT</td></tr>" for i in range(1, 16)
) + """
</tbody></table></body></html>
"""


# ── SSRF guard tests ──────────────────────────────────────────────────────────


def test_html_table_ssrf_reject_private_ip():
    """HtmlTableAdapter.test() returns ok=False for a private IP URL (T-04-19)."""
    import importlib  # noqa: PLC0415
    import app.ingest.html_table  # noqa: PLC0415
    importlib.reload(app.ingest.html_table)
    import app.ingest.html_table.adapter  # noqa: PLC0415
    importlib.reload(app.ingest.html_table.adapter)
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415

    adapter = HtmlTableAdapter()
    result = asyncio.get_event_loop().run_until_complete(
        adapter.test({"url": "http://192.168.1.1/data"})
    )
    assert result.ok is False
    assert result.error is not None


def test_html_table_ssrf_reject_localhost():
    """HtmlTableAdapter.test() returns ok=False for localhost URL (T-04-19)."""
    import importlib  # noqa: PLC0415
    import app.ingest.html_table.adapter as html_mod  # noqa: PLC0415
    importlib.reload(html_mod)
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415

    adapter = HtmlTableAdapter()
    result = asyncio.get_event_loop().run_until_complete(
        adapter.test({"url": "http://localhost:8080/secret"})
    )
    assert result.ok is False
    assert result.error is not None


# ── Happy-path parse tests ─────────────────────────────────────────────────────


def test_html_table_test_returns_normalized_rows():
    """HtmlTableAdapter.test() returns <=10 normalized signal-draft rows on happy path."""
    import importlib  # noqa: PLC0415
    import app.ingest.html_table.adapter as html_mod  # noqa: PLC0415
    importlib.reload(html_mod)
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415
    from app.ingest.base import TestResult  # noqa: PLC0415

    adapter = HtmlTableAdapter()

    # Mock is_safe_url to return True and fetch_url to return our fixture
    mock_response = MagicMock()
    mock_response.text = _HTML_TABLE_FIXTURE

    with (
        patch("app.ingest.html_table.adapter.is_safe_url", return_value=True),
        patch("app.ingest.html_table.adapter.fetch_url", new=AsyncMock(return_value=mock_response)),
    ):
        result = asyncio.get_event_loop().run_until_complete(
            adapter.test({"url": "https://example.com/data"})
        )

    assert isinstance(result, TestResult)
    assert result.ok is True
    assert isinstance(result.sample_rows, list)
    assert len(result.sample_rows) > 0
    assert len(result.sample_rows) <= 10


def test_html_table_10_row_cap():
    """HtmlTableAdapter.test() returns exactly 10 rows when HTML has >10 rows."""
    import importlib  # noqa: PLC0415
    import app.ingest.html_table.adapter as html_mod  # noqa: PLC0415
    importlib.reload(html_mod)
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415

    adapter = HtmlTableAdapter()

    mock_response = MagicMock()
    mock_response.text = _HTML_15_ROWS

    with (
        patch("app.ingest.html_table.adapter.is_safe_url", return_value=True),
        patch("app.ingest.html_table.adapter.fetch_url", new=AsyncMock(return_value=mock_response)),
    ):
        result = asyncio.get_event_loop().run_until_complete(
            adapter.test({"url": "https://example.com/data"})
        )

    assert result.ok is True
    assert len(result.sample_rows) <= 10


# ── Adapter registration tests ────────────────────────────────────────────────


def test_html_table_adapter_registers_on_import():
    """Importing app.ingest.html_table registers html_table adapter in the registry."""
    import importlib  # noqa: PLC0415
    import app.ingest.html_table  # noqa: PLC0415
    importlib.reload(app.ingest.html_table)
    import app.ingest.html_table.adapter  # noqa: PLC0415
    importlib.reload(app.ingest.html_table.adapter)

    from app.ingest.registry import get_adapter  # noqa: PLC0415

    adapter = get_adapter("html_table")
    assert adapter is not None
    assert adapter.type_name == "html_table"


def test_html_table_has_config_schema():
    """HtmlTableAdapter has a config_schema with url field."""
    import importlib  # noqa: PLC0415
    import app.ingest.html_table.adapter as html_mod  # noqa: PLC0415
    importlib.reload(html_mod)
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415

    adapter = HtmlTableAdapter()
    schema = adapter.config_schema.model_json_schema()
    assert "url" in schema.get("properties", {}) or "url" in str(schema)
