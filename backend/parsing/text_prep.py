"""
Message text preparation for Phase 5 AI extraction.

Implements the G6 cost guard described in AI-SPEC §4b.4 and §6:
- Blank / media-only messages (empty caption) are returned as "" so the caller
  can mark raw_items.parse_status = 'irrelevant' without making an LLM call.
- Oversized forwarded messages (> max_tokens * 4 chars) are truncated to
  max_tokens * 4 chars with a trailing "[TRUNCATED]" sentinel so the caller
  knows the signal may be in the head of the message and the LLM saw a subset.

Rough token estimate: 1 token ≈ 4 characters for Russian/English mixed text.
This is a conservative estimate; Cyrillic text may have a higher char-per-token
ratio, but the estimate errs toward sending fewer chars rather than more.

Usage:
    from parsing.text_prep import prepare_message_text

    text = prepare_message_text(raw_message.text)
    if not text:
        # G6: blank or media-only — skip LLM call
        mark_irrelevant(raw_item_id)
        return
    result, journal = extract_signal(text)
"""

from __future__ import annotations

# The truncation sentinel is appended when the input exceeds max_tokens * 4 chars.
_TRUNCATION_SENTINEL = "\n[TRUNCATED]"


def prepare_message_text(raw: str, max_tokens: int = 2000) -> str:
    """Prepare raw Telegram message text before the LLM extraction call.

    Steps:
    1. Strip leading/trailing whitespace.
    2. Return "" if blank (caller should mark irrelevant, skip LLM — G6 cost guard).
    3. If len(text) > max_tokens * 4, truncate to max_tokens * 4 chars and append
       "\\n[TRUNCATED]" sentinel.

    The caller uses "" as a signal to skip the LLM call entirely (G6).
    The [TRUNCATED] sentinel is informational — the extractor can still produce a valid
    result from the truncated head; the sentinel is NOT placed in the user turn that
    goes to the LLM (it is stripped by the caller if needed).

    Args:
        raw: Raw Telegram message text (may include forwarded-message headers,
             media captions, etc.).
        max_tokens: Maximum token budget for the message. Default 2000 (AI-SPEC §4b.4).
                    The char limit is max_tokens * 4 (rough 1 token ≈ 4 chars heuristic).

    Returns:
        str: Prepared message text:
             - "" for blank/media-only input (G6 skip signal)
             - Stripped text for short messages
             - Stripped + truncated text ending with "\\n[TRUNCATED]" for oversized forwards

    Security (T-05-14):
        This function is the oversized-input gate (AI-SPEC §6 G6).
        It prevents a DoS via an extremely long forwarded message flooding the
        LLM context and running up token costs.
    """
    text = raw.strip()
    if not text:
        return ""

    char_limit = max_tokens * 4
    if len(text) > char_limit:
        text = text[:char_limit] + _TRUNCATION_SENTINEL

    return text
