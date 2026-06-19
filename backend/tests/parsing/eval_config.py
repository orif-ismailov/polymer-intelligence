"""
Eval configuration constants for the TZ §6.1.3 acceptance gate.

These are the two trader-sign-off knobs (AI-SPEC §5.3 note):
  1. PRICE_TOLERANCE_PCT — the ±% band for price matching (default ±0.5%).
  2. Synonym-aware grade matching counts toward the ≥85% gate.

Both defaults are defensible per AI-SPEC §1b domain context.  The senior
polymer trader confirms or overrides them at acceptance sign-off (their role
per AI-SPEC §1b expert table).  A change is one line in this file.

Usage:
    from tests.parsing.eval_config import RECALL_GATE, PRECISION_GATE, GATE_FIELDS
"""

# ---------------------------------------------------------------------------
# Gate thresholds (TZ §6.1.3)
# ---------------------------------------------------------------------------

RECALL_GATE: float = 0.80
"""Minimum recall over is_relevant=True gold rows (D1 — blocks CI)."""

PRECISION_GATE: float = 0.85
"""Minimum aggregate field precision over true-positive rows (D3-D9 — blocks CI)."""

# ---------------------------------------------------------------------------
# Per-field match knobs (trader-sign-off defaults — AI-SPEC §5.3)
# ---------------------------------------------------------------------------

PRICE_TOLERANCE_PCT: float = 0.5
"""Price tolerance band ±%. Default 0.5% covers rounding/format only, not magnitude.
Trader sign-off required to tighten (e.g. 0.1%) or loosen (e.g. 1.0%)."""

# Grade synonym-aware matching is always enabled (reading GATE_FIELDS in eval_metrics).
# The synonym map is loaded from synonyms.json (customer input) or synonyms.example.json
# (fallback).  This flag documents the design intent; code in eval_metrics always uses
# synonym matching for grade_text.

# ---------------------------------------------------------------------------
# Gate fields (D3–D9 in AI-SPEC §5.2)
# ---------------------------------------------------------------------------

GATE_FIELDS: list[str] = [
    "product",
    "grade_text",
    "kind",
    "price",
    "currency",
    "volume",
    "counterparty_text",
]
"""The seven fields whose per-field precision is aggregated into the ≥85% gate.
Macro-averaged across rows where the gold label has a non-null value for that field."""
