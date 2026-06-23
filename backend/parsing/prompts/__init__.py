"""
Versioned prompt files for Phase 5 AI extraction.

Prompt files are treated as IMMUTABLE ARTIFACTS:
- extract_v1.md: Version 1 (Phase 5 baseline)
- extract_v2.md: When created, never edit v1

Use load_prompt(version) from loader.py to access prompt text.
Any parse_run row can be replayed by re-running the extractor
with the prompt_version stored in that row.
"""
