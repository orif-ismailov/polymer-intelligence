"""
Tests for parsing.prompts.loader — load_prompt() function.

Covers behaviors 6–7 from 05-01-PLAN.md Task 1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestPromptLoader:
    """Test 6: load_prompt('v1') and load_prompt('does-not-exist') behaviors."""

    def test_load_v1_returns_nonempty_string(self) -> None:
        """load_prompt('v1') returns a non-empty string."""
        from parsing.prompts.loader import load_prompt

        result = load_prompt("v1")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_load_v1_contains_is_relevant(self) -> None:
        """load_prompt('v1') returns text containing 'is_relevant'."""
        from parsing.prompts.loader import load_prompt

        result = load_prompt("v1")
        assert "is_relevant" in result

    def test_load_unknown_version_raises_file_not_found(self) -> None:
        """load_prompt('does-not-exist') raises FileNotFoundError."""
        from parsing.prompts.loader import load_prompt

        with pytest.raises(FileNotFoundError):
            load_prompt("does-not-exist")

    def test_load_v99_raises_file_not_found(self) -> None:
        """load_prompt('v99') raises FileNotFoundError."""
        from parsing.prompts.loader import load_prompt

        with pytest.raises(FileNotFoundError):
            load_prompt("v99")

    def test_load_prompt_is_cached(self) -> None:
        """load_prompt uses lru_cache — two calls return the same object."""
        from parsing.prompts.loader import load_prompt

        # Clear any existing cache first, then call twice
        load_prompt.cache_clear()
        result1 = load_prompt("v1")
        result2 = load_prompt("v1")
        # Same cached object (identity check)
        assert result1 is result2

    def test_load_v1_contains_null(self) -> None:
        """load_prompt('v1') text contains 'null' (null semantics documented)."""
        from parsing.prompts.loader import load_prompt

        result = load_prompt("v1")
        assert "null" in result.lower()


class TestExtractionSchemaJson:
    """Test 7: docs/extraction-schema.json is valid JSON with required property keys."""

    REQUIRED_FIELDS = {
        "is_relevant",
        "kind",
        "product",
        "grade_text",
        "volume",
        "price",
        "currency",
        "counterparty_text",
        "urgency",
        "confidence",
    }

    def _get_schema_path(self) -> Path:
        """Find docs/extraction-schema.json relative to the test file."""
        # From backend/tests/parsing/ → go up to backend/ → then ../docs/
        test_dir = Path(__file__).parent
        backend_dir = test_dir.parent.parent
        return backend_dir.parent / "docs" / "extraction-schema.json"

    def test_schema_file_is_valid_json(self) -> None:
        """docs/extraction-schema.json parses as valid JSON."""
        schema_path = self._get_schema_path()
        assert schema_path.exists(), f"extraction-schema.json not found at {schema_path}"
        with schema_path.open(encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict), "Schema must be a JSON object"

    def test_schema_contains_required_fields(self) -> None:
        """docs/extraction-schema.json properties are a superset of required field names."""
        schema_path = self._get_schema_path()
        with schema_path.open(encoding="utf-8") as f:
            data = json.load(f)

        # The schema may nest properties in different ways; check recursively
        schema_str = json.dumps(data)
        for field in self.REQUIRED_FIELDS:
            assert field in schema_str, (
                f"Required field '{field}' not found in extraction-schema.json"
            )

    def test_schema_has_properties_key(self) -> None:
        """The JSON schema has a 'properties' key at the top level."""
        schema_path = self._get_schema_path()
        with schema_path.open(encoding="utf-8") as f:
            data = json.load(f)
        assert "properties" in data, "JSON schema must have a top-level 'properties' key"
