"""
Relevance service: maps raw product text to a product_id via the synonym dictionary.

Implements the Phase-2 relevance routing described in REQ-uzex-parser:
- Polymer-relevant text → returns product_id (→ signal creation in 02-05)
- Unknown goods → None (→ queue_for_classification, NOT a source_failure)

Security:
  T-02-04: All DB access uses bound parameters (SQLAlchemy text().bindparams or ORM).
           normalize_term does NOT eval/format SQL — no injection surface.
  T-02-05: product_text truncated to 512 chars before queueing (DoS hardening).
  T-02-06: UNIQUE(synonym_norm) + ON CONFLICT DO NOTHING guarantees idempotent seeding.

SC#4 Admin-top-up-able: No module-level cache — every match_product call queries the DB
so admin-added rows are visible immediately without a restart.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Maximum length for queued product_text (T-02-05: DoS hardening)
_MAX_PRODUCT_TEXT_LEN = 512

# Internal whitespace normalizer: collapse one-or-more whitespace chars to single space
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_term(text_: str) -> str:
    """Normalize a synonym or lookup term for case/space-insensitive matching.

    Steps (deterministic):
    1. Strip leading/trailing whitespace
    2. Lowercase
    3. Collapse internal whitespace runs to a single space

    Used for both seed normalization (synonym_norm column) and lookup normalization
    in match_product, so the normalization is symmetric.

    Args:
        text_: Raw input string (may have mixed case, extra spaces, tabs, etc.)

    Returns:
        Normalized string suitable for storage in synonym_norm or direct comparison.

    Security:
        Does not evaluate/format SQL — safe to pass untrusted UZEX product text.
    """
    return _WHITESPACE_RE.sub(" ", text_.strip().lower())


def match_product(session: Session, text_: str) -> int | None:
    """Map raw product text to a product_id via the synonym dictionary.

    Normalizes the input and does a direct lookup against product_synonyms.synonym_norm.
    Returns the associated product_id if found, or None if the text is not recognized.

    Called per UZEX row during parse. No module-level cache — every call queries the DB
    so admin-added rows (source='admin') take effect immediately (SC#4).

    Args:
        session: Active SQLAlchemy session.
        text_: Raw product text from the UZEX feed (untrusted, may be empty).

    Returns:
        product_id (int) if matched, None if unrecognized.

    Security (T-02-04):
        Uses SQLAlchemy bound parameter (:norm) — no f-string or format-based SQL.
    """
    norm = normalize_term(text_)
    if not norm:
        return None

    row = session.execute(
        text(
            """
            SELECT product_id
            FROM product_synonyms
            WHERE synonym_norm = :norm
            LIMIT 1
            """
        ),
        {"norm": norm},
    ).fetchone()

    if row is None:
        logger.debug("relevance.no_match", extra={"norm": norm})
        return None

    product_id: int = row[0]
    logger.debug("relevance.match", extra={"norm": norm, "product_id": product_id})
    return product_id


def queue_for_classification(
    session: Session,
    raw_item_id: int,
    product_text: str,
) -> None:
    """Queue an unrecognized raw_item for manual product classification.

    Inserts a row into manual_classification_queue with ON CONFLICT(raw_item_id)
    DO NOTHING — so calling this twice for the same item is safe.

    This path is explicitly NOT a source_failure (REQ-uzex-parser): unrecognized goods
    are an expected case (new products, typos) and must not increment
    sources.consecutive_failures or emit a source_failure alert.

    Args:
        session: Active SQLAlchemy session.
        raw_item_id: The raw_items.id to queue (FK constraint enforced by DB).
        product_text: The original product text from the raw item, truncated to 512
                      chars before storage (T-02-05: DoS hardening via oversized rows).

    Security (T-02-04):
        Uses SQLAlchemy bound parameters — no f-string SQL.
    Security (T-02-05):
        Truncates product_text to _MAX_PRODUCT_TEXT_LEN (512) before queueing.
    """
    truncated_text = product_text[:_MAX_PRODUCT_TEXT_LEN]

    session.execute(
        text(
            """
            INSERT INTO manual_classification_queue (raw_item_id, product_text)
            VALUES (:raw_item_id, :product_text)
            ON CONFLICT (raw_item_id) DO NOTHING
            """
        ),
        {"raw_item_id": raw_item_id, "product_text": truncated_text},
    )

    logger.info(
        "relevance.queued_for_classification",
        extra={
            "raw_item_id": raw_item_id,
            "product_text_len": len(truncated_text),
        },
    )
