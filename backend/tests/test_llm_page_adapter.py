"""
Tests for LlmPageAdapter (llm_page ingest adapter) and its fetch-task routing.

Covers:
- SSRF guard: unsafe URL -> TestResult(ok=False) / fetch() -> [] without fetching
- Happy-path test(): HTML fixture -> ok=True with a text excerpt (no LLM call)
- Empty page -> ok=False
- fetch(): HTML fixture -> ONE RawItemDraft whose content is the page text
- Selector scoping: only text inside the configured CSS selectors is extracted
- Adapter self-registers on import; type_name + config_schema
- Routing: _enqueue_parse_tasks dispatches the requested task
  ('parse_telegram_item' for llm_page, 'parse_raw_item' by default)

Security: T-04-19 — is_safe_url() called before any HTTP fetch.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

# HTML fixture: a polymer price announcement plus surrounding noise
_HTML_FIXTURE = """
<html>
<head><title>Prices</title></head>
<body>
<nav>Home About Contact</nav>
<div class="announcement">PP Raffia H030GP 20 MT at 1200 USD delivered Tashkent</div>
<footer>Copyright 2026</footer>
</body>
</html>
"""

_HTML_EMPTY = "<html><body></body></html>"


def _clean_registry_add():
    """Clear the registry and re-add the llm_page adapter (per-test isolation)."""
    from app.ingest import registry as _reg  # noqa: PLC0415
    from app.ingest.registry import _clear_registry  # noqa: PLC0415

    _clear_registry()
    import app.ingest.llm_page.adapter as _llm_mod  # noqa: PLC0415
    _reg._REGISTRY["llm_page"] = _llm_mod.LlmPageAdapter()


# ── SSRF guard tests ──────────────────────────────────────────────────────────


def test_llm_page_test_ssrf_reject_private_ip():
    """test() returns ok=False for a private IP URL without fetching (T-04-19)."""
    from app.ingest.llm_page.adapter import LlmPageAdapter  # noqa: PLC0415

    adapter = LlmPageAdapter()
    result = asyncio.run(adapter.test({"url": "http://192.168.1.1/data"}))
    assert result.ok is False
    assert result.error is not None


def test_llm_page_fetch_ssrf_reject_localhost():
    """fetch() returns [] for a localhost URL without fetching (T-04-19)."""
    from app.ingest.llm_page.adapter import LlmPageAdapter  # noqa: PLC0415

    adapter = LlmPageAdapter()
    source = SimpleNamespace(id=1, config={"url": "http://localhost:8080/secret"})
    drafts = asyncio.run(adapter.fetch(source))  # type: ignore[arg-type]
    assert drafts == []


# ── Happy-path tests ──────────────────────────────────────────────────────────


def test_llm_page_test_returns_excerpt():
    """test() returns ok=True with a text excerpt on the happy path (no LLM call)."""
    from app.ingest.base import TestResult  # noqa: PLC0415
    from app.ingest.llm_page.adapter import LlmPageAdapter  # noqa: PLC0415

    adapter = LlmPageAdapter()
    mock_response = MagicMock()
    mock_response.text = _HTML_FIXTURE

    async def run():
        with (
            patch("app.ingest.llm_page.adapter.is_safe_url", return_value=True),
            patch(
                "app.ingest.llm_page.adapter.fetch_url",
                new=AsyncMock(return_value=mock_response),
            ),
        ):
            return await adapter.test({"url": "https://example.com/prices"})

    result = asyncio.run(run())

    assert isinstance(result, TestResult)
    assert result.ok is True
    assert len(result.sample_rows) == 1
    row = result.sample_rows[0]
    assert "PP Raffia H030GP" in str(row["text_excerpt"])
    assert int(row["content_chars"]) > 0


def test_llm_page_test_empty_page_fails():
    """test() returns ok=False when the page yields no text."""
    from app.ingest.llm_page.adapter import LlmPageAdapter  # noqa: PLC0415

    adapter = LlmPageAdapter()
    mock_response = MagicMock()
    mock_response.text = _HTML_EMPTY

    async def run():
        with (
            patch("app.ingest.llm_page.adapter.is_safe_url", return_value=True),
            patch(
                "app.ingest.llm_page.adapter.fetch_url",
                new=AsyncMock(return_value=mock_response),
            ),
        ):
            return await adapter.test({"url": "https://example.com/empty"})

    result = asyncio.run(run())
    assert result.ok is False
    assert result.error is not None


def test_llm_page_fetch_returns_single_page_draft():
    """fetch() returns exactly one RawItemDraft whose content is the page text."""
    from app.ingest.llm_page.adapter import LlmPageAdapter  # noqa: PLC0415

    adapter = LlmPageAdapter()
    mock_response = MagicMock()
    mock_response.text = _HTML_FIXTURE
    source = SimpleNamespace(id=7, config={"url": "https://example.com/prices"})

    async def run():
        with (
            patch("app.ingest.llm_page.adapter.is_safe_url", return_value=True),
            patch(
                "app.ingest.llm_page.adapter.fetch_url",
                new=AsyncMock(return_value=mock_response),
            ),
        ):
            return await adapter.fetch(source)  # type: ignore[arg-type]

    drafts = asyncio.run(run())

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.external_id == "https://example.com/prices"
    assert "PP Raffia H030GP" in (draft.content or "")
    assert draft.payload == {"url": "https://example.com/prices"}


def test_llm_page_selectors_scope_extraction():
    """When selectors are set, only the matching nodes' text is extracted."""
    from app.ingest.llm_page.adapter import LlmPageAdapter  # noqa: PLC0415

    adapter = LlmPageAdapter()
    mock_response = MagicMock()
    mock_response.text = _HTML_FIXTURE
    source = SimpleNamespace(
        id=8,
        config={"url": "https://example.com/prices", "selectors": [".announcement"]},
    )

    async def run():
        with (
            patch("app.ingest.llm_page.adapter.is_safe_url", return_value=True),
            patch(
                "app.ingest.llm_page.adapter.fetch_url",
                new=AsyncMock(return_value=mock_response),
            ),
        ):
            return await adapter.fetch(source)  # type: ignore[arg-type]

    drafts = asyncio.run(run())
    assert len(drafts) == 1
    content = drafts[0].content or ""
    assert "PP Raffia H030GP" in content
    # The nav/footer noise must be excluded by the selector scoping
    assert "Copyright" not in content
    assert "Home About Contact" not in content


# ── Registration / schema tests ───────────────────────────────────────────────


def test_llm_page_adapter_registers_on_import():
    """llm_page adapter is resolvable from the registry after import."""
    _clean_registry_add()
    from app.ingest.registry import get_adapter  # noqa: PLC0415

    adapter = get_adapter("llm_page")
    assert adapter is not None
    assert adapter.type_name == "llm_page"


def test_llm_page_has_url_config_schema():
    """LlmPageAdapter config_schema exposes a 'url' field."""
    from app.ingest.llm_page.adapter import LlmPageAdapter  # noqa: PLC0415

    adapter = LlmPageAdapter()
    props = adapter.config_schema.model_json_schema().get("properties", {})
    assert "url" in props


# ── Fetch-task routing ────────────────────────────────────────────────────────


def test_enqueue_parse_tasks_routes_to_requested_task():
    """_enqueue_parse_tasks dispatches the requested task name (default + override)."""
    from app.tasks import ingest as ingest_mod  # noqa: PLC0415

    with patch.object(ingest_mod.celery_app, "send_task") as mock_send:
        ingest_mod._enqueue_parse_tasks([11, 12])  # default
        ingest_mod._enqueue_parse_tasks([13], task_name="parse_telegram_item")

    dispatched = [c.args[0] for c in mock_send.call_args_list]
    assert dispatched == ["parse_raw_item", "parse_raw_item", "parse_telegram_item"]
