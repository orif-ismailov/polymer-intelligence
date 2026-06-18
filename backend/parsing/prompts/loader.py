"""
Versioned prompt loader for Phase 5 AI extraction.

IMMUTABILITY RULE: Prompt files are append-only. Never edit an existing version
(extract_v1.md, extract_v2.md, etc.). To change the prompt, create a new version
file. The version string is stored verbatim in parse_runs.prompt_version so any
run can be replayed by loading the same version.

Usage:
    from parsing.prompts.loader import load_prompt

    system_prompt = load_prompt("v1")   # Returns extract_v1.md content (cached)
    system_prompt = load_prompt("v2")   # Raises FileNotFoundError if v2 doesn't exist
"""

from __future__ import annotations

import functools
from pathlib import Path

# Directory containing the prompt markdown files (same directory as this module).
PROMPTS_DIR: Path = Path(__file__).parent


@functools.lru_cache(maxsize=16)
def load_prompt(version: str) -> str:
    """Load the versioned extraction prompt from parsing/prompts/extract_{version}.md.

    The loaded text is cached in worker memory (lru_cache) so repeated calls
    within the same process pay no disk I/O after the first load. Cache size 16
    accommodates concurrent prompt versions without unbounded growth.

    Args:
        version: Prompt version identifier, e.g. "v1", "v2".
                 Stored verbatim in parse_runs.prompt_version for replay.

    Returns:
        str: Full content of the prompt markdown file (UTF-8).

    Raises:
        FileNotFoundError: If extract_{version}.md does not exist in PROMPTS_DIR.
                           Never create a partial/invented system prompt on failure —
                           let the caller handle the missing version explicitly.
    """
    path = PROMPTS_DIR / f"extract_{version}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt version {version!r} not found: {path}. "
            "Create a new prompt file rather than editing an existing version."
        )
    return path.read_text(encoding="utf-8")
