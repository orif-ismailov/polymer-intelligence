"""
selectolax-based UZEX HTML table parser.

Reads selectors and column mapping from the source's config dict — never
hardcoded — so that UZEX layout changes can be absorbed by updating
sources.config without touching code (SPEC §10.1 top external risk, T-02-14).

Security mitigations applied here:
  T-02-11: Row count is capped at MAX_ROWS_PER_PAGE; per-cell string length
            is capped at MAX_CELL_CHARS to limit DoS from oversized tables.
  T-02-12: Cell text is returned as raw strings; no SQL interpolation here.
  T-02-13: selectolax (lexbor engine) does not expand external XML entities;
            HTML body size is already capped upstream by http_client.
  T-02-14: Selectors come from config, not code; fixture tests catch layout drift.

Column mapping:
  config["columns"] is a list of field-name strings, one per table column (0-indexed).
  Use None or empty string for columns to skip.
  Field names correspond to RawItemDraft.payload keys:
    lot, product_text, grade_text, volume, price, currency, section,
    counterparty_text, region, event_at, external_id, contract_no
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# DoS mitigation constants (T-02-11)
MAX_ROWS_PER_PAGE: int = 500
MAX_CELL_CHARS: int = 1024

# Control-character strip pattern for content normalization (T-02-12)
# Strips ASCII control chars except tab/newline/CR
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _strip_control(text: str) -> str:
    """Strip control characters from a string (T-02-12 content normalisation)."""
    return _CTRL_RE.sub("", text)


def parse_table_rows(html: str, config: dict[str, object]) -> list[dict[str, object]]:
    """Parse an UZEX HTML page into a list of row dicts using selectolax.

    Uses ``config["table_selector"]`` to locate the table and
    ``config["columns"]`` (list of field names, 0-indexed) to map cell text
    to field names.  Columns whose field name is ``None``, ``""``, or not
    present in the list are skipped.

    Args:
        html: Raw HTML response body from an UZEX page.
        config: Source config dict.  Must contain:
            - ``table_selector`` (str): CSS selector for the table element.
            - ``columns`` (list[str | None]): Field name per column index.

    Returns:
        A list of dicts, one per ``<tr>`` in ``<tbody>``.  Each dict maps
        field name → raw text string (no type coercion — that is 02-05's job).
        Returns an empty list if the table is not found or tbody is empty.

    Raises:
        ImportError: If selectolax is not installed.
    """
    from selectolax.parser import HTMLParser  # noqa: PLC0415 (deferred import)

    table_selector: str = str(config.get("table_selector", "table.custom-table-dark"))
    raw_columns = config.get("columns")
    columns: list[str | None] = [
        (str(c) if c else None) for c in (raw_columns if isinstance(raw_columns, list) else [])
    ]

    tree = HTMLParser(html)
    table_node = tree.css_first(table_selector)
    if table_node is None:
        logger.warning(
            "parse_table_rows.table_not_found",
            extra={"selector": table_selector},
        )
        return []

    rows = table_node.css("tbody tr")
    if not rows:
        logger.info(
            "parse_table_rows.empty_tbody",
            extra={"selector": table_selector},
        )
        return []

    # DoS guard: cap at MAX_ROWS_PER_PAGE (T-02-11)
    if len(rows) > MAX_ROWS_PER_PAGE:
        logger.warning(
            "parse_table_rows.row_cap_applied",
            extra={"found": len(rows), "cap": MAX_ROWS_PER_PAGE},
        )
        rows = rows[:MAX_ROWS_PER_PAGE]

    result: list[dict[str, object]] = []
    for row in rows:
        cells = row.css("td")
        row_dict: dict[str, object] = {}

        for idx, cell in enumerate(cells):
            if idx >= len(columns):
                break

            field_name = columns[idx]
            if not field_name:
                continue  # skip column

            # Extract inner text, strip whitespace and control chars
            raw_text = cell.text(strip=True, deep=True, separator=" ")
            raw_text = " ".join(raw_text.split())  # collapse all whitespace
            raw_text = _strip_control(raw_text)

            # DoS guard: cap cell content length (T-02-11)
            if len(raw_text) > MAX_CELL_CHARS:
                logger.warning(
                    "parse_table_rows.cell_truncated",
                    extra={"field": field_name, "original_len": len(raw_text)},
                )
                raw_text = raw_text[:MAX_CELL_CHARS]

            row_dict[field_name] = raw_text

        if row_dict:
            result.append(row_dict)

    logger.debug(
        "parse_table_rows.done",
        extra={"selector": table_selector, "rows": len(result)},
    )
    return result
