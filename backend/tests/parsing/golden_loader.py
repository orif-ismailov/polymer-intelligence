"""
Golden-set and frozen-prediction loader for the TZ §6.1.3 eval harness.

Design:
- Customer-path-or-example-fixture resolution: the 100-message control sample
  and the synonym map are gated customer inputs (not committed). This loader
  falls back to the committed *.example.json fixtures when the customer set is
  absent, so the harness runs in CI without the gated inputs (§5.5 / plan
  constraint #1).
- load_golden_set(path=None): resolves GOLDEN_SET_PATH env → arg → example fallback.
- load_predictions(version): reads golden/predictions/extract_{version}.json.
- load_synonyms(path=None): resolves SYNONYMS_PATH env → arg → example fallback.
- refresh_predictions(version): calls extract_signal over each gold row and
  rewrites the frozen file — local only (guarded by --runlive; never in CI).

Row shape for golden sets:
  {id, raw_text, fwd_from (nullable), is_relevant, expected: {field: value | None}}

Prediction shape (one dict per row_id):
  {id, is_relevant, kind, product, grade_text, volume, price, currency,
   counterparty_text, urgency, prompt_version}
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).parent
_GOLDEN_DIR = _THIS_DIR / "golden"
_PREDICTIONS_DIR = _GOLDEN_DIR / "predictions"

_DEFAULT_CONTROL_SAMPLE = _GOLDEN_DIR / "control_sample_100.example.json"
_DEFAULT_SYNONYMS = _THIS_DIR / "synonyms.example.json"


def _resolve_path(
    arg: str | None,
    env_var: str,
    default: Path,
) -> Path:
    """Resolve a file path from: argument → env var → default fallback."""
    if arg:
        p = Path(arg)
        if p.exists():
            return p
    env_val = os.environ.get(env_var, "")
    if env_val:
        p = Path(env_val)
        if p.exists():
            return p
    return default


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_golden_set(path: str | None = None) -> list[dict[str, Any]]:
    """Load the golden set from disk.

    Resolution order:
    1. `path` argument (if provided and exists).
    2. `GOLDEN_SET_PATH` environment variable (if set and file exists).
    3. Fallback: control_sample_100.example.json (committed CI fixture).

    The fallback ensures the harness runs without the gated customer input.

    Args:
        path: Optional explicit path to a golden-set JSON file.

    Returns:
        List of gold rows.  Each row has {id, raw_text, is_relevant, expected, ...}.

    Raises:
        FileNotFoundError: If the resolved path does not exist.
        ValueError: If the loaded JSON is not a list.
    """
    resolved = _resolve_path(path, "GOLDEN_SET_PATH", _DEFAULT_CONTROL_SAMPLE)
    if not resolved.exists():
        raise FileNotFoundError(
            f"Golden set not found at {resolved}. "
            "Either commit the example fixture or set GOLDEN_SET_PATH."
        )
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(
            f"Golden set at {resolved} must be a JSON array, got {type(data)}"
        )
    # Coerce numeric fields in expected to Decimal for consistent comparison
    for row in data:
        expected = row.get("expected") or {}
        for field in ("price", "volume"):
            v = expected.get(field)
            if v is not None:
                try:
                    expected[field] = Decimal(str(v))
                except Exception:
                    pass
    return data


def load_predictions(version: str) -> dict[int, dict[str, Any]]:
    """Load frozen predictions for a given prompt version.

    Reads golden/predictions/extract_{version}.json.

    The frozen file is keyed by row_id (int).  Each value is a prediction
    dict with at least {id, is_relevant} and the gate fields.

    Args:
        version: Prompt version string, e.g. "v1".

    Returns:
        Dict mapping row_id (int) → prediction row dict.

    Raises:
        FileNotFoundError: If the predictions file does not exist.
    """
    predictions_file = _PREDICTIONS_DIR / f"extract_{version}.json"
    if not predictions_file.exists():
        raise FileNotFoundError(
            f"Frozen predictions not found: {predictions_file}. "
            "Run `pytest tests/parsing/test_telegram_accuracy.py -m refresh --runlive` "
            "to regenerate."
        )
    data = json.loads(predictions_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(
            f"Predictions file {predictions_file} must be a JSON object keyed by row_id."
        )
    # Keyed by str in JSON; convert to int
    result: dict[int, dict[str, Any]] = {}
    for key, val in data.items():
        row_id = int(key)
        # Coerce numeric fields
        for field in ("price", "volume"):
            v = val.get(field)
            if v is not None:
                try:
                    val[field] = Decimal(str(v))
                except Exception:
                    pass
        result[row_id] = val
    return result


def load_synonyms(path: str | None = None) -> dict[str, str]:
    """Load the grade/trade-name synonym map.

    Resolution order:
    1. `path` argument (if provided and exists).
    2. `SYNONYMS_PATH` environment variable (if set and file exists).
    3. Fallback: synonyms.example.json (committed CI fixture).

    Args:
        path: Optional explicit path to a synonyms JSON file.

    Returns:
        Dict mapping grade string → canonical key.
    """
    resolved = _resolve_path(path, "SYNONYMS_PATH", _DEFAULT_SYNONYMS)
    if not resolved.exists():
        # Synonyms are optional — return empty dict if not available
        return {}
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(
            f"Synonyms at {resolved} must be a JSON object, got {type(data)}"
        )
    # Filter out comment keys
    return {k: v for k, v in data.items() if not k.startswith("_")}


def refresh_predictions(
    version: str,
    golden_path: str | None = None,
    *,
    runlive: bool = False,
) -> dict[int, dict[str, Any]]:
    """Regenerate frozen predictions by calling the live extractor.

    LOCAL ONLY — never called in CI.  Requires a real ANTHROPIC_API_KEY.
    Guarded by `runlive=True`; pytest calls this with --runlive flag only.

    Writes the new predictions to golden/predictions/extract_{version}.json
    and returns the prediction dict (same shape as load_predictions returns).

    Args:
        version: Prompt version to use (must match a file in parsing/prompts/).
        golden_path: Optional path to the golden set (default: load_golden_set()).
        runlive: Must be True to actually call the LLM.

    Returns:
        Dict mapping row_id → prediction dict.

    Raises:
        RuntimeError: If runlive=False (safety guard).
    """
    if not runlive:
        raise RuntimeError(
            "refresh_predictions requires runlive=True. "
            "This function makes live Anthropic API calls — never call it in CI."
        )

    from parsing.extractor import extract_signal  # noqa: PLC0415

    gold = load_golden_set(golden_path)
    predictions: dict[str, dict[str, Any]] = {}

    for row in gold:
        row_id = row["id"]
        raw_text = row.get("raw_text", "")
        fwd_from = row.get("fwd_from")

        try:
            result, _journal = extract_signal(
                raw_text,
                prompt_version=version,
            )
            pred: dict[str, Any] = {
                "id": row_id,
                "is_relevant": result.is_relevant,
                "kind": result.kind.value if result.kind else None,
                "product": result.product,
                "grade_text": result.grade_text,
                "volume": float(result.volume) if result.volume is not None else None,
                "price": float(result.price) if result.price is not None else None,
                "currency": result.currency,
                "counterparty_text": result.counterparty_text,
                "urgency": result.urgency.value if result.urgency else None,
                "prompt_version": version,
                "fwd_from": fwd_from,
            }
        except Exception as exc:
            # Failed extraction — mark as irrelevant (dead-letter in the harness)
            pred = {
                "id": row_id,
                "is_relevant": False,
                "kind": None,
                "product": None,
                "grade_text": None,
                "volume": None,
                "price": None,
                "currency": None,
                "counterparty_text": None,
                "urgency": None,
                "prompt_version": version,
                "error": str(exc),
                "fwd_from": fwd_from,
            }

        predictions[str(row_id)] = pred

    # Write to disk
    _PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    predictions_file = _PREDICTIONS_DIR / f"extract_{version}.json"
    predictions_file.write_text(
        json.dumps(predictions, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Return as int-keyed dict
    return {int(k): v for k, v in predictions.items()}
