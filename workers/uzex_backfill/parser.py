"""Deterministic, generic parsing of a UZEX offer-detail page.

No LLM, no hardcoded field list. Every row of the details table becomes a
``{label: value}`` pair with the original (Russian, culture=ru) labels preserved.
Value cells that contain links are stored href-aware — links are unrecoverable
from text-only extraction, so we never silently drop them.

Failure signatures (confirmed empirically against live pages):

* **ok** — HTTP 200 with a ``table.custom-table-dark`` details table that yields
  at least one label/value pair (~19 rows on a real offer).
* **not_found** — HTTP 200 but the offer table is absent; the rest of the site
  chrome (header/footer) still renders. This is an empty ID gap, safe to skip.
* **parse_empty** — the page rendered but we could extract nothing usable (table
  present with zero pairs, or the offer table is absent AND the page does not
  look like a complete site render, i.e. a malformed/truncated page).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from selectolax.parser import HTMLParser, Node

# The details table on an offer page. Absence of this table is the primary
# "empty ID gap" signal (the empty template omits it entirely).
DETAILS_TABLE_SELECTOR = "table.custom-table-dark"

STATUS_OK = "ok"
STATUS_NOT_FOUND = "not_found"
STATUS_PARSE_EMPTY = "parse_empty"

# Defensive caps so one pathological page cannot blow up memory / a JSONB row.
_MAX_CELL_CHARS = 8192
_MAX_LABEL_CHARS = 512
_MAX_PAIRS = 200


@dataclass
class ParseResult:
    status: str
    fields: dict[str, Any] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)  # raw labels, in page order

    @property
    def field_count(self) -> int:
        return len(self.fields)


def _clean(text: str, limit: int) -> str:
    # Collapse whitespace and strip control chars (except tab/newline handled by
    # the whitespace collapse); cap length.
    text = "".join(ch for ch in text if ch >= " " or ch in "\t\n")
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit]
    return text


def _extract_links(cell: Node) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for a in cell.css("a"):
        href = (a.attributes.get("href") or "").strip()
        if not href:
            continue
        links.append({"text": _clean(a.text(strip=True), _MAX_CELL_CHARS), "href": href})
    return links


def _cell_value(cell: Node) -> Any:
    """Return the value for a value-cell — a str, or an href-aware dict."""
    text = _clean(cell.text(strip=True), _MAX_CELL_CHARS)
    links = _extract_links(cell)
    if not links:
        return text
    value: dict[str, Any] = {"text": text, "href": links[0]["href"]}
    if len(links) > 1:
        # Preserve every link; the primary one stays under "href" for convenience.
        value["hrefs"] = [link["href"] for link in links]
    return value


def _looks_like_full_page(tree: HTMLParser, html: str) -> bool:
    """Heuristic: does this look like a complete site render (just without an
    offer), versus a truncated/garbage response?"""
    if tree.css_first("footer") is not None:
        return True
    lowered = html.rstrip().lower()
    return lowered.endswith("</html>") and len(html) > 10_000


def parse_detail(html: str) -> ParseResult:
    """Parse a detail-page HTML string into a :class:`ParseResult`."""
    tree = HTMLParser(html)
    table = tree.css_first(DETAILS_TABLE_SELECTOR)

    if table is None:
        if _looks_like_full_page(tree, html):
            return ParseResult(status=STATUS_NOT_FOUND)
        return ParseResult(status=STATUS_PARSE_EMPTY)

    fields: dict[str, Any] = {}
    labels: list[str] = []
    for row in table.css("tr"):
        cells = row.css("td, th")
        if len(cells) < 2:
            continue
        label = _clean(cells[0].text(strip=True), _MAX_LABEL_CHARS)
        if not label:
            continue
        value = _cell_value(cells[1])
        labels.append(label)

        # Preserve duplicate labels rather than overwriting — never lose a row.
        key = label
        if key in fields:
            n = 2
            while f"{label} ({n})" in fields:
                n += 1
            key = f"{label} ({n})"
        fields[key] = value
        if len(fields) >= _MAX_PAIRS:
            break

    if not fields:
        return ParseResult(status=STATUS_PARSE_EMPTY)
    return ParseResult(status=STATUS_OK, fields=fields, labels=labels)


def hash_fields(fields: dict[str, Any]) -> str:
    """Stable sha256 of the normalized fields JSON (order-independent)."""
    normalized = json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def status_sentinel_hash(status: str) -> str:
    """Deterministic content_hash for non-ok rows.

    Keeps the ``(source, external_id, content_hash)`` uniqueness meaningful for
    not_found/parse_empty/fetch_failed so re-running the same id never inserts a
    duplicate, while a later transition to a real offer still lands as a new
    revision row.
    """
    return hashlib.sha256(f"__{status}__".encode()).hexdigest()
