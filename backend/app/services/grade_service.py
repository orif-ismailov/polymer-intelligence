"""
Grade extraction service for UZEX polymer grades.

Implements extract_grade(text, session) which returns (grade_id|None, grade_text|None):
1. Try exact case-insensitive match against product_grades.code (DB lookup)
2. If no DB match, apply regex [A-Z]{1,3}\\d{2,4}[A-Z]{0,3} to extract grade token
3. Return (grade_id, grade_text) where grade_text is filled, grade_id may be None

Placed in services/ (NOT the uzex package) to keep this plan file-disjoint from
02-04 in the same wave (no overlap in modified files).

Security:
  T-02-16: DB lookup uses bound parameters (no f-string SQL).
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Polymer grade code regex:
# Matches common polymer grade formats, including:
# - Letter-digit-letter:  T30S, H030, B430F, TR570M  ([A-Z]{1,3}\d{2,4}[A-Z]{0,3})
# - Digit-digit-letter:   2420D, 5030L, 6200N        (\d{2,4}[A-Z]{1,3})
# Combined pattern to handle both forms:
_GRADE_REGEX = re.compile(r"\b([A-Z]{1,3}\d{2,4}[A-Z]{0,3}|\d{2,4}[A-Z]{1,3})\b")


def extract_grade(
    text_: str,
    session: Session,
) -> tuple[int | None, str | None]:
    """Extract a polymer grade code from a text string.

    Algorithm:
    1. Apply regex to find a grade token in the text.
    2. If found, try an exact case-insensitive DB lookup in product_grades.code.
    3. Return (grade_id, grade_text):
       - grade_id is the DB pk if found, else None
       - grade_text is the extracted token string (for grade_text fallback in signals)
       - (None, None) if no grade found at all

    Args:
        text_: Raw text to search for a grade token (e.g. payload grade_text field,
               or a combined product description string).
        session: Active SQLAlchemy session (read-only usage).

    Returns:
        (grade_id, grade_text): grade_id=None if no DB match; grade_text=None if no
        regex match either.

    Security (T-02-16):
        DB lookup uses bound parameters (:code) — no f-string SQL.
    """
    if not text_:
        return None, None

    # Try regex match on the input text
    match = _GRADE_REGEX.search(text_)
    if not match:
        logger.debug("grade_service.no_regex_match", extra={"text": text_[:50]})
        return None, None

    grade_token = match.group(1)

    # Try DB lookup (case-insensitive match on product_grades.code)
    row = session.execute(
        text(
            """
            SELECT id
            FROM product_grades
            WHERE UPPER(code) = UPPER(:code)
            LIMIT 1
            """
        ),
        {"code": grade_token},
    ).fetchone()

    if row is not None:
        grade_id: int = row[0]
        logger.debug(
            "grade_service.db_match",
            extra={"grade_token": grade_token, "grade_id": grade_id},
        )
        return grade_id, grade_token
    else:
        logger.debug(
            "grade_service.regex_only",
            extra={"grade_token": grade_token},
        )
        return None, grade_token
