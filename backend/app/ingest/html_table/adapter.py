"""
HtmlTableAdapter — no-code adapter for public HTML pages containing tables.

Fetches a target HTML page, locates a table via a CSS selector, and maps
columns to normalized signal-draft fields (D-06: product/grade/volume/price/
currency/section/event_at) for the Phase-4 source constructor wizard preview.

Security (T-04-19): is_safe_url() is called BEFORE any HTTP fetch.
SSRF guard prevents fetching from loopback/private/link-local/reserved IPs.

Design (D-04): This adapter is fully live in Phase 4 — Test returns real
parsed rows (up to 10). Enable-on-pass works end-to-end.

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

# ── Lazy imports (DEC-http-client-deferred-import) ────────────────────────────
# is_safe_url and fetch_url are imported inside functions to avoid triggering
# Settings() at pytest collection time (same pattern as uzex adapters).


def is_safe_url(url: str) -> bool:
    """SSRF guard proxy — imported lazily from http_client."""
    from app.ingest.http_client import is_safe_url as _is_safe_url  # noqa: PLC0415
    return _is_safe_url(url)


async def fetch_url(url: str):
    """HTTP fetch proxy — imported lazily from http_client."""
    from app.ingest.http_client import fetch_url as _fetch_url  # noqa: PLC0415
    return await _fetch_url(url)


# ── Config schema ─────────────────────────────────────────────────────────────


class HtmlTableConfig(BaseModel):
    """Configuration for the html_table adapter.

    Fields the admin fills in when creating a source of this type
    via the no-code source constructor wizard.
    """

    url: str = Field(..., description="Public URL of the HTML page containing the table")
    table_selector: str = Field(
        default="table",
        description="CSS selector for the target table element (e.g. 'table', 'table.data-table')",
    )
    # Optional column-to-field mapping (0-indexed column number -> field name).
    # If not provided, the adapter will try to use table header cells as field names.
    product_col: int | None = Field(
        default=None,
        description="0-indexed column index for product text (leave blank to auto-detect)",
    )
    grade_col: int | None = Field(
        default=None,
        description="0-indexed column index for grade text",
    )
    volume_col: int | None = Field(
        default=None,
        description="0-indexed column index for volume",
    )
    price_col: int | None = Field(
        default=None,
        description="0-indexed column index for price",
    )
    currency_col: int | None = Field(
        default=None,
        description="0-indexed column index for currency (ISO code)",
    )
    section_col: int | None = Field(
        default=None,
        description="0-indexed column index for section/category",
    )
    event_at_col: int | None = Field(
        default=None,
        description="0-indexed column index for event date/time",
    )
    currency_default: str = Field(
        default="USD",
        description="Default currency when no currency column is available",
    )


# ── Signal-draft field names for normalized rows (D-06) ───────────────────────
_SIGNAL_DRAFT_FIELDS = ("product", "grade", "volume", "price", "currency", "section", "event_at")

# Default preview cap (test button). The scheduled fetch uses _FETCH_MAX_ROWS so
# a real table is not silently truncated to the 10-row preview size.
_PREVIEW_MAX_ROWS = 10
_FETCH_MAX_ROWS = 200


def _parse_html_table(
    html: str, config: dict, max_rows: int = _PREVIEW_MAX_ROWS
) -> list[dict[str, object]]:
    """Parse an HTML table into normalized signal-draft rows using selectolax.

    Tries to map table columns to signal-draft fields using:
    1. Explicit column indices from config (product_col, grade_col, etc.)
    2. Header cell text (case-insensitive match to signal-draft field names)
    3. Positional fallback (first columns mapped in field order)

    Returns up to 10 rows with keys: product, grade, volume, price,
    currency, section, event_at.
    """
    from selectolax.parser import HTMLParser  # noqa: PLC0415

    tree = HTMLParser(html)
    table_selector = config.get("table_selector", "table") or "table"

    table = tree.css_first(table_selector)
    if table is None:
        # Fallback: try the first <table> element
        table = tree.css_first("table")
    if table is None:
        return []

    # ── Build column mapping ──────────────────────────────────────────────────
    # Explicit config overrides header-based detection.
    col_map: dict[str, int] = {}

    for field in _SIGNAL_DRAFT_FIELDS:
        col_key = f"{field}_col"
        if config.get(col_key) is not None:
            col_map[field] = int(config[col_key])

    # ── Header row detection (if explicit mapping is incomplete) ─────────────
    if len(col_map) < len(_SIGNAL_DRAFT_FIELDS):
        header_row = table.css_first("thead tr") or table.css_first("tr")
        if header_row:
            header_cells = header_row.css("th") or header_row.css("td")
            for idx, cell in enumerate(header_cells):
                cell_text = (cell.text(strip=True) or "").lower()
                for field in _SIGNAL_DRAFT_FIELDS:
                    if field not in col_map and (
                        field in cell_text
                        or cell_text.startswith(field[:4])
                    ):
                        col_map[field] = idx

    # ── Parse data rows ───────────────────────────────────────────────────────
    rows_out: list[dict[str, object]] = []
    currency_default = config.get("currency_default", "USD") or "USD"

    # Collect all data rows (tbody tr or plain tr, skipping header)
    tbody = table.css_first("tbody")
    all_rows = (tbody or table).css("tr")

    # Skip the header row if it's the first row and contains <th> cells
    start_idx = 0
    if all_rows and all_rows[0].css("th"):
        start_idx = 1

    for row in all_rows[start_idx:]:
        cells = row.css("td")
        if not cells:
            continue

        row_dict: dict[str, object] = {}

        for field in _SIGNAL_DRAFT_FIELDS:
            if field in col_map:
                col_idx = col_map[field]
                if col_idx < len(cells):
                    row_dict[field] = cells[col_idx].text(strip=True) or None
                else:
                    row_dict[field] = None
            else:
                row_dict[field] = None

        # Apply default currency if not mapped
        if row_dict.get("currency") is None:
            row_dict["currency"] = currency_default

        rows_out.append(row_dict)

        if len(rows_out) >= max_rows:
            break

    return rows_out


# ── Adapter ───────────────────────────────────────────────────────────────────


@dataclass
class HtmlTableAdapter:
    """SourceAdapter for public HTML pages with tabular data.

    Fetches the target URL, parses the table with selectolax, and maps
    columns to the normalized signal-draft field set (D-06).

    SSRF guard (T-04-19): is_safe_url() is called before any fetch.
    Live in Phase 4 (D-04): Test returns real rows; enable-on-pass works.
    """

    type_name: str = "html_table"
    config_schema: type[BaseModel] = HtmlTableConfig

    async def fetch(self, source: Source) -> list[RawItemDraft]:
        """Fetch the HTML table and return row drafts."""
        cfg: dict[str, object] = dict(source.config or {})
        url = str(cfg.get("url") or "")
        if not url:
            return []

        if not is_safe_url(url):
            logger.warning("html_table.fetch_ssrf_reject", extra={"url": url})
            return []

        try:
            response = await fetch_url(url)
            rows = _parse_html_table(response.text, cfg, max_rows=_FETCH_MAX_ROWS)
        except Exception as exc:
            logger.error("html_table.fetch_error", extra={"url": url, "error": str(exc)})
            return []

        drafts: list[RawItemDraft] = []
        for idx, row in enumerate(rows):
            # parse_raw_item matches products on payload['product_text']; the
            # column-mapped structured row has 'product'/'grade' instead, so derive
            # product_text here (product + grade) to drive rule-based matching.
            product = str(row.get("product") or "").strip()
            grade = str(row.get("grade") or "").strip()
            product_text = " ".join(p for p in (product, grade) if p)
            payload = {**row, "product_text": product_text}
            drafts.append(
                RawItemDraft(
                    external_id=f"html_table_row_{idx}",
                    content="; ".join(f"{k}:{v}" for k, v in row.items() if v),
                    payload=payload,
                    event_at=None,
                )
            )

        logger.info(
            "html_table.fetch_done",
            extra={"url": url, "drafts": len(drafts)},
        )
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
            rows = _parse_html_table(response.text, config)

            if not rows:
                return TestResult(
                    ok=False,
                    error="No table rows found. Check the URL and table_selector.",
                )

            return TestResult(ok=True, sample_rows=rows[:10])

        except Exception as exc:
            logger.error("html_table.test_error", extra={"url": url, "error": str(exc)})
            return TestResult(ok=False, error=str(exc))


# ── Self-register on import ────────────────────────────────────────────────────
# HtmlTableAdapter registers when this module is imported.
# main.py imports app.ingest.html_table so this happens at startup.
_html_table_adapter = HtmlTableAdapter()
register_adapter(_html_table_adapter)
