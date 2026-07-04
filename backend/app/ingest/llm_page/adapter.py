"""
LlmPageAdapter — no-code adapter for LLM-based web-page extraction.

Fetches a public web page, extracts its (optionally selector-scoped) text, and
emits ONE RawItemDraft whose ``content`` is the page text. The Phase-5 LLM
extraction pipeline (``parse_telegram_item`` → ``parsing.extractor.extract_signal``)
then turns that text into a signal — identical to how Telegram messages are
processed. The ``llm_page_fetch`` Celery task (``app/tasks/ingest_llm_page.py``)
drives this on a schedule and enqueues the extractor per new raw_item.

Security (T-04-19): is_safe_url() is called BEFORE any HTTP fetch (SSRF guard),
mirroring the html_table adapter. Response body size is capped by http_client.

Self-registers at import time via register_adapter().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.ingest.base import RawItemDraft, TestResult
from app.ingest.registry import register_adapter

if TYPE_CHECKING:
    from app.models.sources import Source

logger = logging.getLogger(__name__)

# Cap the extracted page text stored in raw_items.content. The parse pipeline
# (prepare_message_text) only feeds the first ~8000 chars to the LLM, so this
# generous bound keeps storage sane without discarding selector-scoped content.
_MAX_PAGE_CHARS = 20_000

# Length of the text excerpt returned by test() for the wizard preview.
_TEST_EXCERPT_CHARS = 300


# ── Lazy imports (DEC-http-client-deferred-import, mirrors html_table) ────────
# is_safe_url and fetch_url are imported inside functions to avoid triggering
# Settings() at pytest collection time (same pattern as the uzex/html_table adapters).


def is_safe_url(url: str) -> bool:
    """SSRF guard proxy — imported lazily from http_client."""
    from app.ingest.http_client import is_safe_url as _is_safe_url  # noqa: PLC0415
    return _is_safe_url(url)


async def fetch_url(url: str):  # type: ignore[no-untyped-def]
    """HTTP fetch proxy — imported lazily from http_client."""
    from app.ingest.http_client import fetch_url as _fetch_url  # noqa: PLC0415
    return await _fetch_url(url)


# ── Config schema ─────────────────────────────────────────────────────────────


class LlmPageConfig(BaseModel):
    """Configuration for the llm_page adapter.

    Fields the admin fills in when creating a source of this type via the
    no-code source constructor wizard. Extraction itself uses the versioned
    system prompt (``LLM_PROMPT_VERSION``) and configured model
    (``LLM_EXTRACT_MODEL``); per-source prompt/model overrides are a future
    enhancement.
    """

    url: str = Field(
        ...,
        description="Public URL of the web page to extract polymer-market signals from",
    )
    selectors: list[str] = Field(
        default_factory=list,
        description=(
            "Optional CSS selectors limiting extraction to specific page sections "
            "(reduces token usage). If empty, the whole page body text is used."
        ),
    )


# ── Page-text extraction ──────────────────────────────────────────────────────


def _extract_page_text(html: str, selectors: list[str] | None) -> str:
    """Extract readable text from an HTML page, optionally scoped to CSS selectors.

    Uses selectolax (same parser as html_table). When ``selectors`` is provided,
    only the text of matching nodes is concatenated; otherwise the <body> (or
    whole document) text is used. Whitespace is collapsed and the result is
    capped at ``_MAX_PAGE_CHARS``.
    """
    from selectolax.parser import HTMLParser  # noqa: PLC0415

    tree = HTMLParser(html)

    parts: list[str] = []
    if selectors:
        for selector in selectors:
            for node in tree.css(selector):
                text = node.text(separator=" ", strip=True)
                if text:
                    parts.append(text)
    else:
        node = tree.css_first("body") or tree.root
        if node is not None:
            parts.append(node.text(separator=" ", strip=True))

    joined = "\n".join(p for p in parts if p)
    # Collapse runs of whitespace to keep the text (and token count) compact.
    collapsed = " ".join(joined.split())
    return collapsed[:_MAX_PAGE_CHARS]


# ── Adapter ───────────────────────────────────────────────────────────────────


@dataclass
class LlmPageAdapter:
    """SourceAdapter for LLM-based extraction from a public web page.

    fetch()  → SSRF-guard, fetch the page, emit ONE RawItemDraft (content=page
               text). The LLM extraction runs later in parse_telegram_item.
    test()   → SSRF-guard, fetch, return a text excerpt so the admin can confirm
               the page is reachable and non-empty (no LLM spend at test time).
    """

    type_name: str = "llm_page"
    config_schema: type[BaseModel] = LlmPageConfig

    async def fetch(self, source: Source) -> list[RawItemDraft]:
        """Fetch the page and return a single page-text draft (or [] on error)."""
        cfg: dict[str, object] = dict(source.config or {})
        url = str(cfg.get("url") or "")
        if not url:
            return []

        if not is_safe_url(url):
            logger.warning("llm_page.fetch_ssrf_reject", extra={"url": url})
            return []

        selectors = list(cfg.get("selectors") or [])
        try:
            response = await fetch_url(url)
            text = _extract_page_text(response.text, selectors)
        except Exception as exc:
            logger.error("llm_page.fetch_error", extra={"url": url, "error": str(exc)})
            return []

        if not text:
            logger.info("llm_page.fetch_empty", extra={"url": url})
            return []

        # external_id = url (stable): identical page content dedups via content_hash
        # (ON CONFLICT DO NOTHING); changed content → new raw_item → new extraction.
        draft = RawItemDraft(
            external_id=url,
            content=text,
            payload={"url": url},
            event_at=None,
        )
        logger.info("llm_page.fetch_done", extra={"url": url, "chars": len(text)})
        return [draft]

    async def test(self, config: dict[str, object]) -> TestResult:
        """SSRF-guard, fetch the page, and return a text excerpt (no LLM call).

        Security (T-04-19): is_safe_url() runs before any network activity.
        Returns ok=False if the URL is unsafe, unreachable, or has no text — so
        the enable-gate keeps the source disabled (last_test_ok_at stays NULL).
        """
        url = str(config.get("url") or "")
        if not url:
            return TestResult(ok=False, error="URL is required")

        # SSRF guard — must come first, before any network call (T-04-19)
        if not is_safe_url(url):
            return TestResult(
                ok=False,
                error="URL is not publicly reachable (SSRF guard: private/loopback/reserved address).",
            )

        selectors = list(config.get("selectors") or [])
        try:
            response = await fetch_url(url)
            text = _extract_page_text(response.text, selectors)
        except Exception as exc:
            logger.error("llm_page.test_error", extra={"url": url, "error": str(exc)})
            return TestResult(ok=False, error=str(exc))

        if not text:
            return TestResult(
                ok=False,
                error="No text extracted from the page. Check the URL and selectors.",
            )

        return TestResult(
            ok=True,
            sample_rows=[
                {
                    "url": url,
                    "content_chars": len(text),
                    "text_excerpt": text[:_TEST_EXCERPT_CHARS],
                }
            ],
        )


# ── Self-register on import ────────────────────────────────────────────────────
_llm_page_adapter = LlmPageAdapter()
register_adapter(_llm_page_adapter)
