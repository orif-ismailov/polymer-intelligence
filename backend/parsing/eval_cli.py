"""
Eval CLI for the TZ §6.1.3 acceptance review.

Usage:
    python -m parsing.eval_cli [--golden PATH] [--predictions VERSION] [--synonyms PATH]

Prints:
    - Full per-field + per-failure-mode breakdown table
    - PASS/FAIL verdict against RECALL_GATE and PRECISION_GATE

This is the tool the developer/trader runs at acceptance review time
(AI-SPEC §5 expert roles) and after every prompt-version bump before
promoting the new version to production.

Exit codes:
    0 — both recall and precision gates pass
    1 — one or both gates fail
"""

from __future__ import annotations

import argparse
import sys
from typing import Any


def _print_report(
    recall: float,
    precision: float,
    tp: int,
    n_rows: int,
    per_field: dict[str, dict[str, Any]],
    failure_modes: dict[str, int],
    *,
    recall_gate: float,
    precision_gate: float,
    gate_fields: list[str],
) -> None:
    """Print the full eval report to stdout."""
    n_fields = len(gate_fields)
    recall_status = "PASS" if recall >= recall_gate else "FAIL"
    precision_status = "PASS" if precision >= precision_gate else "FAIL"

    print(f"\n{'='*70}")
    print("Telegram AI Extraction — Acceptance Review")
    print(f"{'='*70}")
    print(f"  {'Rows evaluated':35s}: {n_rows}")
    print(f"  {'True positives':35s}: {tp}")
    print(f"  {'Gate fields':35s}: {n_fields}")
    print(f"{'─'*70}")
    print(f"  {f'D1 Recall (gate ≥{recall_gate:.0%}):':35s}  {recall:.1%}  [{recall_status}]")
    print(f"  {f'Field Precision (gate ≥{precision_gate:.0%}):':35s}  {precision:.1%}  [{precision_status}]")
    print(f"{'─'*70}")
    print("  Per-field precision breakdown:")
    for field in gate_fields:
        counts = per_field.get(field, {})
        correct = counts.get("correct", 0)
        total = counts.get("total", 0)
        if total > 0:
            pct = 100.0 * correct / total
            status = "OK" if pct >= precision_gate * 100 else "BELOW"
        else:
            pct = float("nan")
            status = "N/A"
        print(f"    {field:22s}: {correct:4d}/{total:4d} = {pct:6.1f}%  [{status}]")
    print(f"{'─'*70}")
    print("  Failure modes:")
    for mode, count in failure_modes.items():
        print(f"    {mode:30s}: {count}")
    print(f"{'='*70}")

    # Final verdict
    all_pass = recall >= recall_gate and precision >= precision_gate
    verdict = "PASS" if all_pass else "FAIL"
    print(f"\n  VERDICT: {verdict}")
    if not all_pass:
        print("  !! Gate(s) failed — do NOT promote this prompt version to production.")
        if recall < recall_gate:
            print(f"     Recall {recall:.1%} < {recall_gate:.0%}: too many missed market signals.")
        if precision < precision_gate:
            print(f"     Precision {precision:.1%} < {precision_gate:.0%}: too many field extraction errors.")
        print("  Next steps: review per-field breakdown, fix prompt, regenerate predictions, re-run.")
    else:
        print("  All gates pass. Proceed with trader sign-off on the two §5.3 defaults:")
        print("    1. Price tolerance ±0.5% (PRICE_TOLERANCE_PCT in eval_config.py)")
        print("    2. Synonym-aware grade matching counts toward the 85% gate")
    print()


def main(argv: list[str] | None = None) -> int:
    """Run the eval CLI. Returns exit code (0=pass, 1=fail)."""
    parser = argparse.ArgumentParser(
        description="Telegram AI extraction acceptance review tool (TZ §6.1.3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m parsing.eval_cli                    # default fixtures\n"
            "  python -m parsing.eval_cli --golden /path/to/control_sample_100.json\n"
            "  python -m parsing.eval_cli --predictions v2   # after a prompt-version bump\n"
        ),
    )
    parser.add_argument(
        "--golden",
        metavar="PATH",
        default=None,
        help=(
            "Path to the golden set JSON file. "
            "Default: GOLDEN_SET_PATH env var → control_sample_100.example.json"
        ),
    )
    parser.add_argument(
        "--predictions",
        metavar="VERSION",
        default="v1",
        help="Frozen prediction version to load (default: v1).",
    )
    parser.add_argument(
        "--synonyms",
        metavar="PATH",
        default=None,
        help=(
            "Path to the synonym map JSON file. "
            "Default: SYNONYMS_PATH env var → synonyms.example.json"
        ),
    )
    args = parser.parse_args(argv)

    # Import here so the CLI works without the tests/ package on sys.path
    # (the CLI lives in parsing/; the eval infra lives in tests/parsing/)
    try:
        import tests.parsing.eval_config as eval_config
        from tests.parsing.eval_metrics import per_field_breakdown
        from tests.parsing.golden_loader import (
            load_golden_set,
            load_predictions,
            load_synonyms,
        )
    except ImportError as exc:
        print(
            f"ERROR: Could not import eval infrastructure: {exc}\n"
            "Ensure you are running from the backend/ directory:\n"
            "  cd backend && python -m parsing.eval_cli",
            file=sys.stderr,
        )
        return 1

    # Load data
    try:
        gold = load_golden_set(args.golden)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR loading golden set: {exc}", file=sys.stderr)
        return 1

    try:
        predictions = load_predictions(args.predictions)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR loading predictions (version={args.predictions!r}): {exc}", file=sys.stderr)
        print(
            "Tip: regenerate with:\n"
            "  pytest tests/parsing/test_telegram_accuracy.py -m refresh --runlive",
            file=sys.stderr,
        )
        return 1

    try:
        synonyms = load_synonyms(args.synonyms)
    except (FileNotFoundError, ValueError) as exc:
        print(f"WARNING: Could not load synonyms ({exc}); using empty map.", file=sys.stderr)
        synonyms = {}

    # Compute breakdown
    breakdown = per_field_breakdown(gold, predictions, synonyms)
    recall = breakdown["recall"]
    precision = breakdown["precision"]
    tp = breakdown["tp_count"]
    per_field = breakdown["per_field"]
    failure_modes = breakdown["failure_modes"]

    _print_report(
        recall=recall,
        precision=precision,
        tp=tp,
        n_rows=len(gold),
        per_field=per_field,
        failure_modes=failure_modes,
        recall_gate=eval_config.RECALL_GATE,
        precision_gate=eval_config.PRECISION_GATE,
        gate_fields=eval_config.GATE_FIELDS,
    )

    all_pass = recall >= eval_config.RECALL_GATE and precision >= eval_config.PRECISION_GATE
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
