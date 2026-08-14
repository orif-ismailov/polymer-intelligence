"""
Immutable deduplicated raw-item pipeline.

This module provides two functions:

  compute_content_hash(source_id, external_id, content) -> bytes
      Deterministic SHA-256 digest of the normalized triple.
      Identical inputs always produce identical bytes.
      Used as the dedup key in raw_items.content_hash.

  save_raw_items(session, source, drafts) -> int
      Insert RawItemDraft rows into raw_items using
      INSERT ... ON CONFLICT (source_id, content_hash) DO NOTHING.
      Returns the count of newly inserted rows (0 on a duplicate run).

Design invariants (DB-architecture §2 + dev-spec §2 rule 1/2):
  - raw_items is immutable: this module NEVER issues mutations on existing rows' content or payload.
  - Dedup key = sha256(source_id + external_id + content_normalized)
  - parse_status defaults to 'pending' on insert.
  - On conflict (duplicate hash), the existing row is preserved unchanged.

Security:
  T-02-11: Row/cell content capped upstream in parse_table_rows.
  T-02-12: All DB writes go through ORM bound parameters (no f-string SQL).
           Content-normalized input strips control chars before hashing.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.domains.signals.source_models import Source
    from app.ingest.base import RawItemDraft

logger = logging.getLogger(__name__)

# Field separator (ASCII Unit Separator) — unlikely to appear in real data
_HASH_SEP = "\x1f"

# Whitespace normalization pattern (T-02-12: content normalization before hashing)
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_content(content: str | None) -> str:
    """Normalize whitespace for consistent hashing.

    Collapses all whitespace runs (including newlines, tabs) into a single space
    and strips leading/trailing whitespace.  This ensures that formatting
    differences in scraped HTML do not produce different hashes for identical data.
    """
    if not content:
        return ""
    return _WHITESPACE_RE.sub(" ", content).strip()


def compute_content_hash(
    source_id: int,
    external_id: str | None,
    content: str | None,
) -> bytes:
    """Compute the deterministic SHA-256 dedup hash for a raw item.

    The hash covers the normalized triple:
        "{source_id}{SEP}{external_id or ''}{SEP}{normalized_content}"

    where SEP = ASCII 0x1F (Unit Separator) and normalized_content has
    whitespace collapsed (multiple spaces/newlines → single space).

    Args:
        source_id: The sources.id integer.
        external_id: Source-side item identifier (UZEX lot#, deal#, etc.).
            None is treated as empty string.
        content: Plain-text content string.  None is treated as empty string.

    Returns:
        32-byte SHA-256 digest (bytes).
    """
    normalized = _normalize_content(content)
    ext = external_id or ""
    raw = f"{source_id}{_HASH_SEP}{ext}{_HASH_SEP}{normalized}".encode()
    return hashlib.sha256(raw).digest()


def save_raw_items(
    session: Session,
    source: Source,
    drafts: list[RawItemDraft],
) -> tuple[int, list[int]]:
    """Insert raw item drafts into raw_items with sha256 dedup.

    Uses INSERT ... ON CONFLICT (source_id, content_hash) DO NOTHING so that:
    - A first call with N drafts inserts N new rows.
    - An identical second call inserts 0 rows (no duplicates).
    - Existing rows are NEVER updated (immutability invariant — DB-arch §2).

    RETURNING id is used so callers receive the *exact* IDs of newly inserted
    rows rather than re-querying by recency heuristic (CR-04 / T-02-12).

    Args:
        session: Active SQLAlchemy session. Caller commits.
        source: The Source ORM object (provides source.id).
        drafts: List of RawItemDraft objects to persist.  May be empty.

    Returns:
        A (count, inserted_ids) tuple:
        - count: number of newly inserted rows (0 for a fully duplicate batch).
        - inserted_ids: list of raw_items.id values for the inserted rows,
          in insertion order. Empty list when count == 0.
    """
    if not drafts:
        return 0, []

    inserted_ids: list[int] = []

    for draft in drafts:
        content_hash = compute_content_hash(
            source_id=source.id,
            external_id=draft.external_id,
            content=draft.content,
        )

        # INSERT ... ON CONFLICT DO NOTHING with RETURNING id so we get the
        # exact row ID for newly inserted rows (no recency heuristic — CR-04).
        cursor = session.execute(
            sa.text(
                """
                INSERT INTO raw_items
                    (source_id, external_id, content, payload, content_hash,
                     event_at, parse_status, parse_attempts)
                VALUES
                    (:source_id, :external_id, :content, CAST(:payload AS JSONB),
                     :content_hash, :event_at, 'pending', 0)
                ON CONFLICT (source_id, content_hash)
                DO NOTHING
                RETURNING id
                """
            ),
            {
                "source_id": source.id,
                "external_id": draft.external_id,
                "content": draft.content,
                "payload": _payload_to_jsonb(draft.payload),
                "content_hash": content_hash,
                "event_at": draft.event_at,
            },
        )

        # RETURNING returns the row only when the INSERT actually happened;
        # DO NOTHING on conflict causes an empty result set for duplicates.
        row = cursor.fetchone()
        if row is not None:
            inserted_ids.append(int(row[0]))

    inserted = len(inserted_ids)
    logger.info(
        "raw_pipeline.save_done",
        extra={
            "source_id": source.id,
            "drafts": len(drafts),
            "inserted": inserted,
            "skipped": len(drafts) - inserted,
        },
    )
    return inserted, inserted_ids


def _payload_to_jsonb(payload: dict[str, object] | None) -> str | None:
    """Serialize the payload dict to a JSON string for the CAST(:payload AS JSONB) bind.

    Returns None if payload is None or empty.
    """
    if payload is None:
        return None
    import json  # noqa: PLC0415
    return json.dumps(payload, ensure_ascii=False)
