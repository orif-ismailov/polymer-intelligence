"""
parsing — Phase 5 AI extraction contract package.

Provides the fixed Pydantic extraction schema (ExtractionResult), the versioned
prompt convention (parsing.prompts.loader.load_prompt), and supporting types.

Import the public API:
    from parsing.schemas import ExtractionResult, SignalKind, UrgencyLevel
    from parsing.prompts.loader import load_prompt

Downstream plans (05-02 through 05-05) depend on this package's interface.
"""
