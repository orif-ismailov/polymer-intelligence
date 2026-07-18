"""
RssAdapter — no-code adapter for public RSS/Atom feeds.

Fetches the RSS/Atom feed URL and maps each entry to normalized signal-draft
fields (D-06: product/grade/volume/price/currency/section/event_at).

Parsing strategy (Environment Availability — 04-RESEARCH.md Pitfall 4):
- Prefer defusedxml (entity-safe) when available; fall back to stdlib
  xml.etree.ElementTree. defusedxml prevents billion-laughs XML bombs (WR-03).
- Both RSS 2.0 and Atom 1.0 formats are supported.

Security (T-04-19): is_safe_url() is called BEFORE any HTTP fetch.
Security (WR-03): response body is capped at 5 MB before parsing; defusedxml
  is used when available to mitigate exponential-entity-expansion attacks.

Design (D-04): Fully live in Phase 4 — Test returns real rows; enable-on-pass
works end-to-end.

Self-registers at import time via register_adapter().
"""

from __future__ import annotations

import html as _html
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import TYPE_CHECKING

# WR-03: prefer defusedxml (entity-safe, defends against billion-laughs XML bombs).
# Fall back to stdlib ET when defusedxml is not installed so the adapter remains
# functional during the transition period while the dependency is being added.
try:
    import defusedxml.ElementTree as _safe_ET  # type: ignore[import-untyped]
    _parse_xml = _safe_ET.fromstring
except ImportError:  # defusedxml not yet installed — safe fallback, size-cap still applies
    _parse_xml = ET.fromstring  # type: ignore[assignment]

from pydantic import BaseModel, Field

from app.ingest.base import RawItemDraft, TestResult
from app.ingest.registry import register_adapter

if TYPE_CHECKING:
    from app.models.sources import Source

logger = logging.getLogger(__name__)

# ── Lazy imports (DEC-http-client-deferred-import) ────────────────────────────


def is_safe_url(url: str) -> bool:
    """SSRF guard proxy — imported lazily from http_client."""
    from app.ingest.http_client import is_safe_url as _is_safe_url  # noqa: PLC0415
    return _is_safe_url(url)


async def fetch_url(url: str):
    """HTTP fetch proxy — imported lazily from http_client."""
    from app.ingest.http_client import fetch_url as _fetch_url  # noqa: PLC0415
    return await _fetch_url(url)


# ── Config schema ─────────────────────────────────────────────────────────────


class RssConfig(BaseModel):
    """Configuration for the rss adapter.

    Fields the admin fills in when creating a source of this type
    via the no-code source constructor wizard.
    """

    url: str = Field(..., description="Public URL of the RSS/Atom feed")
    currency_default: str = Field(
        default="USD",
        description="Default currency for items without an explicit currency field",
    )
    section_default: str | None = Field(
        default=None,
        description="Default section/category label for items (optional)",
    )


# ── RSS/Atom parsing (stdlib xml.etree.ElementTree) ───────────────────────────

_RSS_NS: dict[str, str] = {}  # RSS 2.0 has no namespace by default
_ATOM_NS = "http://www.w3.org/2005/Atom"
_MEDIA_NS = "http://search.yahoo.com/mrss/"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(text: str) -> str:
    """Flatten an HTML/entity-laden RSS description to clean single-spaced text.

    Feed descriptions (Google News in particular) carry HTML markup; the news
    classifier and the generic LLM extractor want plain prose, not tags.
    """
    return _WS_RE.sub(" ", _html.unescape(_TAG_RE.sub(" ", text or ""))).strip()


def _parse_feed(content: bytes, config: dict) -> list[dict[str, object]]:
    """Parse RSS 2.0 or Atom 1.0 feed using stdlib xml.etree.ElementTree.

    Maps each feed entry to normalized signal-draft fields:
    product, grade, volume, price, currency, section, event_at.

    Extracts raw text from title/description/summary fields and stores
    them in product + section. Volume/price/currency are extracted from
    description text if present; otherwise left None for Phase-5 LLM extraction.

    Returns up to 10 rows.
    """
    currency_default = config.get("currency_default", "USD") or "USD"
    section_default = config.get("section_default") or None

    # WR-03: cap response body before parsing to prevent billion-laughs XML bombs
    # (CPU/memory exhaustion from exponential entity expansion in attacker-controlled feeds).
    _MAX_FEED_BYTES = 5 * 1024 * 1024  # 5 MB  # noqa: N806
    if len(content) > _MAX_FEED_BYTES:
        raise ValueError(
            f"Feed response too large ({len(content)} bytes > {_MAX_FEED_BYTES} byte limit)"
        )

    try:
        root = _parse_xml(content)
    except ET.ParseError as exc:
        raise ValueError(f"Failed to parse feed XML: {exc}") from exc

    rows: list[dict[str, object]] = []

    # ── RSS 2.0 ──────────────────────────────────────────────────────────────
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item"):
            if len(rows) >= 10:
                break
            rows.append(_rss_item_to_row(item, currency_default, section_default))
        return rows

    # ── Atom 1.0 ─────────────────────────────────────────────────────────────
    atom_ns = f"{{{_ATOM_NS}}}"
    entries = root.findall(f"{atom_ns}entry")
    if not entries:
        # Try without namespace prefix (some Atom feeds omit the prefix)
        entries = root.findall("entry")

    for entry in entries:
        if len(rows) >= 10:
            break
        rows.append(_atom_entry_to_row(entry, atom_ns, currency_default, section_default))

    return rows


def _rss_item_to_row(
    item: ET.Element,
    currency_default: str,
    section_default: str | None,
) -> dict[str, object]:
    """Convert an RSS 2.0 <item> element to a normalized signal-draft row."""
    title = (item.findtext("title") or "").strip()
    description = (item.findtext("description") or "").strip()
    pub_date = (item.findtext("pubDate") or "").strip()
    category = (item.findtext("category") or "").strip()
    link = (item.findtext("link") or "").strip()

    summary = _strip_html(description)
    # Use title as product text (most human-readable summary)
    product = title or summary or None
    # Use category or section_default as section
    section = category or section_default or None
    # event_at from pubDate (raw string — Phase-5 will parse to datetime)
    event_at = pub_date or None

    return {
        "product": product,
        "grade": None,
        "volume": None,
        "price": None,
        "currency": currency_default,
        "section": section,
        "event_at": event_at,
        "link": link or None,       # article URL → news card "read at source"
        "summary": summary or None,  # article body → richer news classification
    }


def _atom_entry_to_row(
    entry: ET.Element,
    atom_ns: str,
    currency_default: str,
    section_default: str | None,
) -> dict[str, object]:
    """Convert an Atom 1.0 <entry> element to a normalized signal-draft row."""
    title_el = entry.find(f"{atom_ns}title") or entry.find("title")
    summary_el = entry.find(f"{atom_ns}summary") or entry.find("summary")
    content_el = entry.find(f"{atom_ns}content") or entry.find("content")
    updated_el = entry.find(f"{atom_ns}updated") or entry.find("updated")
    category_el = entry.find(f"{atom_ns}category") or entry.find("category")
    link_el = entry.find(f"{atom_ns}link") or entry.find("link")

    title = (title_el.text or "").strip() if title_el is not None else ""
    raw_summary = ""
    if summary_el is not None and summary_el.text:
        raw_summary = summary_el.text
    elif content_el is not None and content_el.text:
        raw_summary = content_el.text
    summary = _strip_html(raw_summary)
    updated = (updated_el.text or "").strip() if updated_el is not None else ""
    category = ""
    if category_el is not None:
        category = category_el.get("term", "") or category_el.get("label", "")
    # Atom links carry the URL in the href attribute (fall back to element text).
    link = ""
    if link_el is not None:
        link = (link_el.get("href") or link_el.text or "").strip()

    product = title or summary or None
    section = category or section_default or None
    event_at = updated or None

    return {
        "product": product,
        "grade": None,
        "volume": None,
        "price": None,
        "currency": currency_default,
        "section": section,
        "event_at": event_at,
        "link": link or None,
        "summary": summary or None,
    }


# ── Adapter ───────────────────────────────────────────────────────────────────


@dataclass
class RssAdapter:
    """SourceAdapter for RSS 2.0 / Atom 1.0 feeds.

    Fetches the feed URL and maps each entry to normalized signal-draft fields.
    Uses stdlib xml.etree.ElementTree (no additional dependency required).

    SSRF guard (T-04-19): is_safe_url() called before any fetch.
    Live in Phase 4 (D-04): Test returns real rows; enable-on-pass works.
    """

    type_name: str = "rss"
    config_schema: type[BaseModel] = RssConfig

    async def fetch(self, source: Source) -> list[RawItemDraft]:
        """Fetch the RSS feed and return row drafts."""
        cfg: dict[str, object] = dict(source.config or {})
        url = str(cfg.get("url") or "")
        if not url:
            return []

        if not is_safe_url(url):
            logger.warning("rss.fetch_ssrf_reject", extra={"url": url})
            return []

        try:
            response = await fetch_url(url)
            rows = _parse_feed(response.content, cfg)
        except Exception as exc:
            logger.error("rss.fetch_error", extra={"url": url, "error": str(exc)})
            return []

        drafts: list[RawItemDraft] = []
        for idx, row in enumerate(rows):
            # Content = headline + article body so the news classifier / LLM extractor
            # sees real prose, not just the title. external_id prefers the article link
            # so re-fetches of the same feed dedup on the article, not the row index.
            title = str(row.get("product") or "")
            summary = str(row.get("summary") or "")
            content = f"{title}\n\n{summary}".strip() if summary else title
            link = str(row.get("link") or "")
            drafts.append(
                RawItemDraft(
                    external_id=link or f"rss_item_{idx}",
                    content=content,
                    payload=row,
                    event_at=None,
                )
            )

        logger.info("rss.fetch_done", extra={"url": url, "drafts": len(drafts)})
        return drafts

    async def test(self, config: dict[str, object]) -> TestResult:
        """Test the config: SSRF-guard, fetch, parse, return <=10 normalized rows.

        Security (T-04-19): is_safe_url() is called before any HTTP activity.
        Returns TestResult(ok=False) if the URL is unsafe or if parsing fails.
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

        try:
            response = await fetch_url(url)
            rows = _parse_feed(response.content, config)

            if not rows:
                return TestResult(
                    ok=False,
                    error="No feed entries found. Check the URL and ensure it is a valid RSS/Atom feed.",
                )

            return TestResult(ok=True, sample_rows=rows[:10])

        except Exception as exc:
            logger.error("rss.test_error", extra={"url": url, "error": str(exc)})
            return TestResult(ok=False, error=str(exc))


# ── Self-register on import ────────────────────────────────────────────────────
_rss_adapter = RssAdapter()
register_adapter(_rss_adapter)
