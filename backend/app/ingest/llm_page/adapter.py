"""
LlmPageAdapter — pending stub for LLM-based page extraction.

Phase-4 status (D-04/D-05): Config is saved; Test/enable are gated until
the LLM extraction engine is built in Phase 5.

- test() always returns TestResult(ok=False, error="Available after Phase 5")
- fetch() always returns [] (no LLM activity in Phase 4)
- is_enabled stays False because last_test_ok_at is never set

Admins can pre-stage page configuration now; the source goes live when
Phase 5 delivers the LLM extraction engine (D-05).

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


# ── Config schema ─────────────────────────────────────────────────────────────


class LlmPageConfig(BaseModel):
    """Configuration for the llm_page adapter.

    Saved at creation time; active after Phase 5 delivers the LLM extraction engine.
    """

    url: str = Field(
        ...,
        description="Public URL of the web page to extract data from via LLM",
    )
    extraction_prompt: str | None = Field(
        default=None,
        description=(
            "Optional custom extraction prompt. If blank, the default polymer-market "
            "extraction prompt is used."
        ),
    )
    model: str = Field(
        default="claude-haiku-4-5",
        description="LLM model identifier to use for extraction (Phase 5)",
    )
    selectors: list[str] = Field(
        default_factory=list,
        description=(
            "Optional CSS selectors to limit extraction scope to specific page sections "
            "(reduces token usage)"
        ),
    )


# ── Adapter ───────────────────────────────────────────────────────────────────


@dataclass
class LlmPageAdapter:
    """SourceAdapter stub for LLM-based page extraction.

    Phase 4 pending: config is saved but Test and fetch are not yet functional.
    The full Claude/LLM extraction implementation lands in Phase 5.
    """

    type_name: str = "llm_page"
    config_schema: type[BaseModel] = LlmPageConfig

    async def fetch(self, source: Source) -> list[RawItemDraft]:
        """Return empty list — LLM extraction engine not available until Phase 5."""
        logger.debug(
            "llm_page.fetch_pending",
            extra={"source_id": getattr(source, "id", None)},
        )
        return []

    async def test(self, config: dict[str, object]) -> TestResult:
        """Return ok=False — LLM extraction engine not available until Phase 5.

        The pending stub ensures:
        - last_test_ok_at is never set -> is_enabled stays False
        - Admins see a clear message about when this will be available
        """
        return TestResult(
            ok=False,
            error="Available after Phase 5",
        )


# ── Self-register on import ────────────────────────────────────────────────────
_llm_page_adapter = LlmPageAdapter()
register_adapter(_llm_page_adapter)
