"""
Eval metrics for the TZ §6.1.3 acceptance gate.

Implements the AI-SPEC §5.3 per-field match rules as pure, deterministic
functions with no I/O.  Unit-tested independently in test_eval_metrics.py
so the metric math cannot silently drift (§5.6 invariant).

Public API:
    match_field(field, gold_val, sys_val, synonyms) -> bool
    compute_recall(gold, pred) -> float
    compute_field_precision(gold, pred, synonyms) -> float
    per_field_breakdown(gold, pred, synonyms) -> dict

All functions accept the gold/pred row shapes defined in golden_loader.py:
  gold row:  {id, is_relevant, expected: {field: value | None}}
  pred row:  {id, is_relevant, field: value | None, ...}
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from tests.parsing.eval_config import GATE_FIELDS, PRICE_TOLERANCE_PCT

# ---------------------------------------------------------------------------
# Cyrillic → Latin transliteration table for grade matching
# Covers the most common Cyrillic letters in Russian polymer grade codes.
# ---------------------------------------------------------------------------

_CYR_TO_LAT: dict[str, str] = {
    "А": "A", "а": "a",
    "Б": "B", "б": "b",
    "В": "V", "в": "v",
    "Г": "G", "г": "g",
    "Д": "D", "д": "d",
    "Е": "E", "е": "e",
    "Ж": "ZH", "ж": "zh",
    "З": "Z", "з": "z",
    "И": "I", "и": "i",
    "Й": "Y", "й": "y",
    "К": "K", "к": "k",
    "Л": "L", "л": "l",
    "М": "M", "м": "m",
    "Н": "N", "н": "n",
    "О": "O", "о": "o",
    "П": "P", "п": "p",
    "Р": "R", "р": "r",
    "С": "S", "с": "s",
    "Т": "T", "т": "t",
    "У": "U", "у": "u",
    "Ф": "F", "ф": "f",
    "Х": "KH", "х": "kh",
    "Ц": "TS", "ц": "ts",
    "Ч": "CH", "ч": "ch",
    "Ш": "SH", "ш": "sh",
    "Щ": "SHCH", "щ": "shch",
    "Ъ": "", "ъ": "",
    "Ы": "Y", "ы": "y",
    "Ь": "", "ь": "",
    "Э": "E", "э": "e",
    "Ю": "YU", "ю": "yu",
    "Я": "YA", "я": "ya",
}


def _normalise_grade(text: str) -> str:
    """Normalise a grade string for comparison.

    Steps (AI-SPEC §5.3 grade match rule):
    1. Strip leading/trailing whitespace.
    2. Casefold (unicode case folding).
    3. Transliterate Cyrillic → Latin.
    4. Collapse internal whitespace.
    5. Strip again.
    """
    if not text:
        return ""
    # Step 1: strip
    s = text.strip()
    # Step 2: casefold
    s = s.casefold()
    # Step 3: transliterate Cyrillic → Latin (casefolded Cyrillic already lowercased)
    result = []
    for ch in s:
        # Look up original char + upper version in table
        mapped = _CYR_TO_LAT.get(ch) or _CYR_TO_LAT.get(ch.upper())
        if mapped is not None:
            result.append(mapped.lower())
        else:
            result.append(ch)
    s = "".join(result)
    # Step 4: collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalise_counterparty(text: str) -> str:
    """Normalise counterparty text for comparison.

    AI-SPEC §5.3: strip, casefold, drop legal-form tokens (ООО, MCHJ, OOO, LLC, etc.).
    """
    if not text:
        return ""
    # Strip and casefold
    s = text.strip().casefold()
    # Remove common legal-form tokens (Russian + Uzbek + English)
    legal_tokens = {
        "ооо", "оао", "зао", "пао", "ао", "ип", "гк",  # Russian
        "mchj", "aj", "xk", "qk",  # Uzbek
        "llc", "ltd", "inc", "corp", "gmbh",  # English/German
        '"', "'", "«", "»",  # quotation marks common in Russian company names
    }
    # Remove legal tokens from the string
    for token in sorted(legal_tokens, key=len, reverse=True):
        s = s.replace(token, " ")
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _to_decimal(val: Any) -> Decimal | None:
    """Coerce val to Decimal; return None on failure."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Core: per-field match function (AI-SPEC §5.3)
# ---------------------------------------------------------------------------


def match_field(
    field: str,
    gold_val: Any,
    sys_val: Any,
    synonyms: dict[str, str],
) -> bool:
    """Determine if a system-extracted field value matches the gold value.

    Implements the AI-SPEC §5.3 rubric:
    - Both null: True (correct null — not a precision miss, not fabrication).
    - Gold null, sys non-null: False (fabrication miss, §5.1).
    - Gold non-null, sys null: False (extraction miss).
    - kind / currency / product: exact match after normalisation.
    - grade_text: synonym-aware, case/script-insensitive.
    - volume: exact Decimal match (both assumed already in MT).
    - price: Decimal within ±PRICE_TOLERANCE_PCT.
    - counterparty_text: normalised substring/equality.

    Args:
        field: One of GATE_FIELDS or 'is_relevant'.
        gold_val: Gold label value (or None if absent in the source).
        sys_val: System-extracted value (or None).
        synonyms: Customer synonym map {grade_string → canonical_key}.

    Returns:
        True if the values match under the field's rubric.
    """
    # --- Both null: correct null (not a miss) ---
    if gold_val is None and sys_val is None:
        return True
    # --- Gold null, sys provides value: fabrication miss ---
    if gold_val is None and sys_val is not None:
        return False
    # --- Gold present, sys null: extraction miss ---
    if gold_val is not None and sys_val is None:
        return False

    # --- Both non-null: apply field-specific rules ---
    if field == "grade_text":
        return _match_grade(gold_val, sys_val, synonyms)
    elif field == "price":
        return _match_price(gold_val, sys_val)
    elif field == "volume":
        return _match_volume(gold_val, sys_val)
    elif field == "counterparty_text":
        return _match_counterparty(gold_val, sys_val)
    elif field in ("currency", "kind", "product"):
        # Exact match, case-normalised
        return str(gold_val).strip().casefold() == str(sys_val).strip().casefold()
    else:
        # Unknown field: exact equality fallback
        return gold_val == sys_val


def _match_grade(gold_val: Any, sys_val: Any, synonyms: dict[str, str]) -> bool:
    """Grade match: synonym-aware + normalised string equality."""
    gold_norm = _normalise_grade(str(gold_val))
    sys_norm = _normalise_grade(str(sys_val))

    # Direct normalised match
    if gold_norm == sys_norm:
        return True

    # Synonym-map lookup: both should resolve to the same canonical key
    gold_key = synonyms.get(gold_norm) or synonyms.get(str(gold_val).strip().casefold())
    sys_key = synonyms.get(sys_norm) or synonyms.get(str(sys_val).strip().casefold())

    if gold_key is not None and sys_key is not None and gold_key == sys_key:
        return True

    return False


def _match_price(gold_val: Any, sys_val: Any) -> bool:
    """Price match: within ±PRICE_TOLERANCE_PCT."""
    gold_d = _to_decimal(gold_val)
    sys_d = _to_decimal(sys_val)
    if gold_d is None or sys_d is None:
        return gold_d is None and sys_d is None
    if gold_d == Decimal("0"):
        return sys_d == Decimal("0")
    tolerance = Decimal(str(PRICE_TOLERANCE_PCT)) / Decimal("100")
    ratio = abs(sys_d - gold_d) / abs(gold_d)
    return ratio <= tolerance


def _match_volume(gold_val: Any, sys_val: Any) -> bool:
    """Volume match: exact Decimal (both already in MT after normalisation)."""
    gold_d = _to_decimal(gold_val)
    sys_d = _to_decimal(sys_val)
    if gold_d is None or sys_d is None:
        return gold_d is None and sys_d is None
    # Strip trailing zeros for equivalence (Decimal("50.0") == Decimal("50"))
    return gold_d.normalize() == sys_d.normalize()


def _match_counterparty(gold_val: Any, sys_val: Any) -> bool:
    """Counterparty match: normalised substring/equality."""
    gold_norm = _normalise_counterparty(str(gold_val))
    sys_norm = _normalise_counterparty(str(sys_val))
    if not gold_norm and not sys_norm:
        return True
    if not gold_norm or not sys_norm:
        return False
    # Match if one contains the other, or they are equal
    return gold_norm == sys_norm or gold_norm in sys_norm or sys_norm in gold_norm


# ---------------------------------------------------------------------------
# Recall computation (D1 — AI-SPEC §5.1)
# ---------------------------------------------------------------------------


def compute_recall(
    gold: list[dict[str, Any]],
    pred: dict[int, dict[str, Any]],
) -> float:
    """Compute relevance recall: TP / (TP + FN) over gold rows where is_relevant=True.

    A false negative is a gold-relevant row that the system classifies as irrelevant.

    Args:
        gold: List of gold rows, each with {id, is_relevant, expected: {...}}.
        pred: Dict mapping row_id → prediction row with at least {is_relevant}.

    Returns:
        float: Recall in [0.0, 1.0].  Returns 1.0 if no relevant gold rows exist
               (vacuously no false negatives possible).
    """
    relevant_gold = [r for r in gold if r.get("is_relevant", False)]
    if not relevant_gold:
        return 1.0

    tp = 0
    for row in relevant_gold:
        row_id = row["id"]
        p = pred.get(row_id, {})
        if p.get("is_relevant", False):
            tp += 1

    fn = len(relevant_gold) - tp
    return tp / (tp + fn)


# ---------------------------------------------------------------------------
# Field precision computation (D3–D9 — AI-SPEC §5.1)
# ---------------------------------------------------------------------------


def compute_field_precision(
    gold: list[dict[str, Any]],
    pred: dict[int, dict[str, Any]],
    synonyms: dict[str, str],
) -> float:
    """Compute aggregate field precision over true-positive rows.

    Only rows where BOTH gold is_relevant=True AND pred is_relevant=True
    (true positives) contribute to the precision calculation.

    Macro-average across GATE_FIELDS.  Fields with no gold-non-null entries
    in the TP set are excluded from the average (avoid divide-by-zero and
    don't penalise for fields the gold set doesn't exercise).

    Args:
        gold: List of gold rows.
        pred: Dict mapping row_id → prediction row.
        synonyms: Customer grade/trade-name synonym map.

    Returns:
        float: Precision in [0.0, 1.0].  Returns 1.0 if no TP rows exist
               (no precision to measure).
    """
    # Find true-positive rows
    tp_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in gold:
        if not row.get("is_relevant", False):
            continue
        row_id = row["id"]
        p = pred.get(row_id, {})
        if p.get("is_relevant", False):
            tp_rows.append((row, p))

    if not tp_rows:
        return 1.0

    # Per-field counts
    field_correct: dict[str, int] = {f: 0 for f in GATE_FIELDS}
    field_total: dict[str, int] = {f: 0 for f in GATE_FIELDS}

    for gold_row, pred_row in tp_rows:
        expected = gold_row.get("expected", {})
        for field in GATE_FIELDS:
            gold_val = expected.get(field)
            sys_val = pred_row.get(field)
            # Only count denominator when gold has a non-null value
            # (gold-null fields are excluded from the precision denominator
            #  per AI-SPEC §5.1: "Denominator is fields the gold label says are present")
            if gold_val is not None:
                field_total[field] += 1
                if match_field(field, gold_val, sys_val, synonyms):
                    field_correct[field] += 1
            # If gold_val is None: check for fabrication separately (report-only D12)
            # For precision gate, null-null pairs are excluded from denominator

    # Macro-average across fields that have at least one gold-non-null entry
    active_fields = [f for f in GATE_FIELDS if field_total[f] > 0]
    if not active_fields:
        return 1.0

    per_field_precision = [
        field_correct[f] / field_total[f] for f in active_fields
    ]
    return sum(per_field_precision) / len(per_field_precision)


# ---------------------------------------------------------------------------
# Per-field + per-failure-mode breakdown (for CLI report)
# ---------------------------------------------------------------------------


def per_field_breakdown(
    gold: list[dict[str, Any]],
    pred: dict[int, dict[str, Any]],
    synonyms: dict[str, str],
) -> dict[str, Any]:
    """Compute a detailed per-field and per-failure-mode breakdown.

    Returns a dict with:
      - per_field: {field: {correct, total, precision}}
      - failure_modes: {mode_name: count}
      - tp_count: number of true-positive rows
      - recall: overall recall
      - precision: aggregate field precision
    """
    recall = compute_recall(gold, pred)
    precision = compute_field_precision(gold, pred, synonyms)

    # True-positive rows
    tp_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    fn_count = 0
    fp_count = 0
    fabrication_count = 0

    for row in gold:
        row_id = row["id"]
        p = pred.get(row_id, {})
        gold_rel = row.get("is_relevant", False)
        pred_rel = p.get("is_relevant", False)

        if gold_rel and pred_rel:
            tp_rows.append((row, p))
        elif gold_rel and not pred_rel:
            fn_count += 1
        elif not gold_rel and pred_rel:
            fp_count += 1

    # Per-field breakdown over TP rows
    field_correct: dict[str, int] = {f: 0 for f in GATE_FIELDS}
    field_total: dict[str, int] = {f: 0 for f in GATE_FIELDS}

    for gold_row, pred_row in tp_rows:
        expected = gold_row.get("expected", {})
        for field in GATE_FIELDS:
            gold_val = expected.get(field)
            sys_val = pred_row.get(field)
            if gold_val is not None:
                field_total[field] += 1
                if match_field(field, gold_val, sys_val, synonyms):
                    field_correct[field] += 1
            elif sys_val is not None:
                # Gold null, sys non-null = fabrication
                fabrication_count += 1

    per_field: dict[str, dict[str, Any]] = {}
    for f in GATE_FIELDS:
        total = field_total[f]
        correct = field_correct[f]
        per_field[f] = {
            "correct": correct,
            "total": total,
            "precision": correct / total if total > 0 else None,
        }

    return {
        "recall": recall,
        "precision": precision,
        "tp_count": len(tp_rows),
        "per_field": per_field,
        "failure_modes": {
            "false_negative": fn_count,
            "false_positive": fp_count,
            "fabrication": fabrication_count,
        },
    }
