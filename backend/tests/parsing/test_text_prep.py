"""
Tests for parsing.text_prep — prepare_message_text().

Test coverage:
  4. prepare_message_text("") → ""; prepare_message_text("  \\n ") → ""
     A 12000-char input → ends with "[TRUNCATED]" and len ≤ 2000*4 + len("\\n[TRUNCATED]")
  5. prepare_message_text leaves a short normal message unchanged (stripped)
"""

from __future__ import annotations


class TestPrepareMessageText:
    """Tests for text_prep.prepare_message_text."""

    def test_empty_string_returns_empty(self) -> None:
        """Empty string returns empty string (G6 cost guard — skip LLM call)."""
        from parsing.text_prep import prepare_message_text

        assert prepare_message_text("") == ""

    def test_whitespace_only_returns_empty(self) -> None:
        """Whitespace-only string returns empty (G6 cost guard)."""
        from parsing.text_prep import prepare_message_text

        assert prepare_message_text("  \n ") == ""
        assert prepare_message_text("\t\t  \n\n") == ""
        assert prepare_message_text("   ") == ""

    def test_oversized_input_truncated_with_sentinel(self) -> None:
        """A >2000-token input is truncated to max_tokens*4 chars + [TRUNCATED] sentinel."""
        from parsing.text_prep import prepare_message_text

        # 12000 characters is 3× the 4000-char limit (default max_tokens=2000)
        long_text = "A" * 12000
        result = prepare_message_text(long_text)

        # Must end with [TRUNCATED]
        assert result.endswith("[TRUNCATED]"), (
            f"Oversized text must end with [TRUNCATED], got: ...{result[-30:]!r}"
        )

        # Length must not exceed max_tokens*4 + len("\\n[TRUNCATED]")
        max_allowed = 2000 * 4 + len("\n[TRUNCATED]")
        assert len(result) <= max_allowed, (
            f"Truncated text too long: {len(result)} > {max_allowed}"
        )

    def test_oversized_input_custom_max_tokens(self) -> None:
        """Truncation respects a custom max_tokens parameter."""
        from parsing.text_prep import prepare_message_text

        # 3000 chars with max_tokens=500 → limit is 500*4=2000 chars
        text = "B" * 3000
        result = prepare_message_text(text, max_tokens=500)

        assert result.endswith("[TRUNCATED]")
        max_allowed = 500 * 4 + len("\n[TRUNCATED]")
        assert len(result) <= max_allowed

    def test_short_message_unchanged(self) -> None:
        """A short message (< 2000 tokens) is returned stripped but otherwise unchanged."""
        from parsing.text_prep import prepare_message_text

        short_msg = "Продам ПП T30S 50 тонн по 950 у.е."
        result = prepare_message_text(short_msg)

        assert result == short_msg.strip()
        assert "[TRUNCATED]" not in result

    def test_short_message_with_leading_trailing_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped from short messages."""
        from parsing.text_prep import prepare_message_text

        msg = "  Hello polymer market  "
        result = prepare_message_text(msg)
        assert result == "Hello polymer market"

    def test_exactly_at_limit_not_truncated(self) -> None:
        """A message exactly at the character limit (max_tokens*4) is NOT truncated."""
        from parsing.text_prep import prepare_message_text

        exact_limit = "X" * (2000 * 4)
        result = prepare_message_text(exact_limit)

        # Exactly at limit — should not be truncated
        assert "[TRUNCATED]" not in result
        assert result == exact_limit

    def test_one_over_limit_is_truncated(self) -> None:
        """One character over the limit triggers truncation."""
        from parsing.text_prep import prepare_message_text

        one_over = "X" * (2000 * 4 + 1)
        result = prepare_message_text(one_over)
        assert result.endswith("[TRUNCATED]")
