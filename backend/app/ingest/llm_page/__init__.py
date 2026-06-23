"""
llm_page adapter package.

Importing this package self-registers the LlmPageAdapter (llm_page)
into the global adapter registry.

Usage:
    import app.ingest.llm_page  # registers LlmPageAdapter as side-effect
"""

from app.ingest.llm_page import adapter  # noqa: F401

__all__ = ["adapter"]
