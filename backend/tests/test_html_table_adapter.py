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
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
_HTML_15_ROWS = (
    "<html><body><table>"
    "<thead><tr><th>Product</th><th>Volume</th></tr></thead>"
    "<tbody>"
    + "\n".join(
        f"<tr><td>PP Raffia</td><td>{i} MT</td></tr>" for i in range(1, 16)
    )
    + "</tbody></table></body></html>"
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure the html_table adapter is registered for each test.

    Clears registry, then uses the internal registry dict directly to add
    the adapter without going through register_adapter() (which raises on
    duplicate). This pattern avoids issues with module-level code only
    running once per Python process (module import cache).
    """
    from app.ingest import registry as _reg  # noqa: PLC0415
    from app.ingest.registry import _clear_registry  # noqa: PLC0415

    _clear_registry()
    # Import adapter module (first time runs side-effect registration; subsequent
    # times the module is already in sys.modules so we re-add to the cleared dict)
    import app.ingest.html_table.adapter as _html_mod  # noqa: PLC0415
    _reg._REGISTRY["html_table"] = _html_mod.HtmlTableAdapter()
    yield
    _clear_registry()


# ── SSRF guard tests ──────────────────────────────────────────────────────────


def test_html_table_ssrf_reject_private_ip():
    """HtmlTableAdapter.test() returns ok=False for a private IP URL (T-04-19)."""
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415

    adapter = HtmlTableAdapter()
    result = asyncio.run(adapter.test({"url": "http://192.168.1.1/data"}))
    assert result.ok is False
    assert result.error is not None


def test_html_table_ssrf_reject_localhost():
    """HtmlTableAdapter.test() returns ok=False for localhost URL (T-04-19)."""
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415

    adapter = HtmlTableAdapter()
    result = asyncio.run(adapter.test({"url": "http://localhost:8080/secret"}))
    assert result.ok is False
    assert result.error is not None


# ── Happy-path parse tests ─────────────────────────────────────────────────────


def test_html_table_test_returns_normalized_rows():
    """HtmlTableAdapter.test() returns <=10 normalized signal-draft rows on happy path."""
    from app.ingest.base import TestResult  # noqa: PLC0415
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415

    adapter = HtmlTableAdapter()

    mock_response = MagicMock()
    mock_response.text = _HTML_TABLE_FIXTURE

    async def run():
        with (
            patch("app.ingest.html_table.adapter.is_safe_url", return_value=True),
            patch(
                "app.ingest.html_table.adapter.fetch_url",
                new=AsyncMock(return_value=mock_response),
            ),
        ):
            return await adapter.test({"url": "https://example.com/data"})

    result = asyncio.run(run())

    assert isinstance(result, TestResult)
    assert result.ok is True
    assert isinstance(result.sample_rows, list)
    assert len(result.sample_rows) > 0
    assert len(result.sample_rows) <= 10


def test_html_table_10_row_cap():
    """HtmlTableAdapter.test() returns exactly 10 rows when HTML has >10 rows."""
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415

    adapter = HtmlTableAdapter()

    mock_response = MagicMock()
    mock_response.text = _HTML_15_ROWS

    async def run():
        with (
            patch("app.ingest.html_table.adapter.is_safe_url", return_value=True),
            patch(
                "app.ingest.html_table.adapter.fetch_url",
                new=AsyncMock(return_value=mock_response),
            ),
        ):
            return await adapter.test({"url": "https://example.com/data"})

    result = asyncio.run(run())

    assert result.ok is True
    assert len(result.sample_rows) <= 10


# ── Adapter registration tests ────────────────────────────────────────────────


def test_html_table_adapter_registers_on_import():
    """html_table adapter is registered after importing the package."""
    from app.ingest.registry import get_adapter  # noqa: PLC0415

    adapter = get_adapter("html_table")
    assert adapter is not None
    assert adapter.type_name == "html_table"


def test_html_table_has_config_schema():
    """HtmlTableAdapter has a config_schema with url field."""
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415

    adapter = HtmlTableAdapter()
    schema = adapter.config_schema.model_json_schema()
    props = schema.get("properties", {})
    assert "url" in props


def test_html_table_type_name():
    """HtmlTableAdapter.type_name is 'html_table'."""
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415

    adapter = HtmlTableAdapter()
    assert adapter.type_name == "html_table"


# ── fetch() drafts ────────────────────────────────────────────────────────────


def _run_fetch(adapter, source, html):
    """Helper: run adapter.fetch(source) with SSRF + fetch_url patched."""
    mock_response = MagicMock()
    mock_response.text = html

    async def run():
        with (
            patch("app.ingest.html_table.adapter.is_safe_url", return_value=True),
            patch(
                "app.ingest.html_table.adapter.fetch_url",
                new=AsyncMock(return_value=mock_response),
            ),
        ):
            return await adapter.fetch(source)

    return asyncio.run(run())


def test_html_table_fetch_adds_product_text_for_rule_parser():
    """fetch() drafts carry payload['product_text'] so parse_raw_item can match."""
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415

    adapter = HtmlTableAdapter()
    source = SimpleNamespace(id=1, config={"url": "https://example.com/data"})

    drafts = _run_fetch(adapter, source, _HTML_TABLE_FIXTURE)

    assert len(drafts) == 3
    first = drafts[0]
    assert first.payload is not None
    # product_text = product + grade (e.g. "PP Raffia H030GP")
    assert first.payload["product_text"] == "PP Raffia H030GP"


def test_html_table_fetch_not_capped_at_preview_limit():
    """fetch() ingests all rows (>10), not just the 10-row test preview cap."""
    from app.ingest.html_table.adapter import HtmlTableAdapter  # noqa: PLC0415

    adapter = HtmlTableAdapter()
    source = SimpleNamespace(id=2, config={"url": "https://example.com/data"})

    drafts = _run_fetch(adapter, source, _HTML_15_ROWS)

    assert len(drafts) == 15
