"""Test bootstrap: make ``uzex_backfill`` importable regardless of cwd."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# workers/  (parent of the uzex_backfill package) must be importable.
_WORKERS_DIR = Path(__file__).resolve().parents[2]
if str(_WORKERS_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKERS_DIR))

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_html():
    def _load(name: str) -> str:
        return (_FIXTURES / name).read_text(encoding="utf-8")

    return _load
