"""
TZ §6.1.3 accuracy gate — mirrors tests/test_uzex_accuracy.py for Telegram AI extraction.

Design (AI-SPEC §5.6):
- Loads golden/control_sample_100.json (or example fixture in CI) via golden_loader.
- Loads frozen predictions golden/predictions/extract_v1.json (no live Anthropic call).
- Computes recall (D1) and aggregate field precision (D3-D9) via eval_metrics.
- Asserts recall >= RECALL_GATE (0.80) and precision >= PRECISION_GATE (0.85) — BLOCKS CI.
- Report-only dimensions (D2/D10/D12/D14) print but never fail the build.
- A @pytest.mark.refresh test (--runlive flag only) regenerates frozen predictions locally.

CI integration:
  pytest tests/parsing/test_telegram_accuracy.py -q        # full run (includes gate)
  pytest tests/parsing/test_telegram_accuracy.py -m gate   # gate assertions only
  pytest tests/parsing/test_telegram_accuracy.py -m refresh --runlive  # local only

Key-free CI contract:
  The gate test NEVER makes a live Anthropic call — it reads frozen predictions.
  The test imports are safe under ANTHROPIC_API_KEY=sk-ant-ci-placeholder.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PREDICTIONS_VERSION = "v1"

# ---------------------------------------------------------------------------
# Fixture file validation tests
# ---------------------------------------------------------------------------


class TestControlSampleFile:
    """Validate the committed example control_sample fixture itself.

    Mirrors TestUzexControlSampleFile in test_uzex_accuracy.py.
    """

    @pytest.fixture(scope="class")
    def sample_path(self) -> Path:
        from tests.parsing.golden_loader import _DEFAULT_CONTROL_SAMPLE  # noqa: PLC0415
        return _DEFAULT_CONTROL_SAMPLE

    def test_control_sample_exists(self, sample_path: Path) -> None:
        """control_sample_100.example.json must exist."""
        assert sample_path.exists(), (
            f"Missing example fixture: {sample_path}"
        )

    def test_control_sample_valid_json(self, sample_path: Path) -> None:
        """control_sample_100.example.json must be parseable JSON."""
        data = json.loads(sample_path.read_text(encoding="utf-8"))
        assert isinstance(data, list), "control sample must be a JSON array"

    def test_control_sample_min_10_rows(self, sample_path: Path) -> None:
        """Example fixture must have ≥10 rows (CI smoke check)."""
        data = json.loads(sample_path.read_text(encoding="utf-8"))
        assert len(data) >= 10, (
            f"Example fixture must have ≥10 rows, got {len(data)}"
        )

    def test_each_row_has_expected_and_is_relevant(self, sample_path: Path) -> None:
        """Every row must have 'expected' and 'is_relevant' keys."""
        data = json.loads(sample_path.read_text(encoding="utf-8"))
        for row in data:
            assert "expected" in row, f"Row {row.get('id')} missing 'expected'"
            assert "is_relevant" in row, f"Row {row.get('id')} missing 'is_relevant'"

    def test_expected_has_gate_fields(self, sample_path: Path) -> None:
        """Each 'expected' dict must have the gate fields (can be null)."""
        from tests.parsing.eval_config import GATE_FIELDS  # noqa: PLC0415
        data = json.loads(sample_path.read_text(encoding="utf-8"))
        for row in data:
            expected = row.get("expected", {}) or {}
            for field in GATE_FIELDS:
                # Field may be null, but key must exist
                assert field in expected, (
                    f"Row {row.get('id')} expected dict missing key '{field}'"
                )

    def test_sample_covers_relevant_and_irrelevant(self, sample_path: Path) -> None:
        """Sample must have both relevant and irrelevant rows."""
        data = json.loads(sample_path.read_text(encoding="utf-8"))
        relevant = [r for r in data if r.get("is_relevant")]
        irrelevant = [r for r in data if not r.get("is_relevant")]
        assert len(relevant) > 0, "Sample must have relevant rows"
        assert len(irrelevant) > 0, "Sample must have irrelevant rows"


class TestFrozenPredictionsFile:
    """Validate the frozen predictions file shape."""

    def test_predictions_file_exists(self) -> None:
        """Frozen predictions file for v1 must exist."""
        from tests.parsing.golden_loader import _PREDICTIONS_DIR  # noqa: PLC0415
        pred_file = _PREDICTIONS_DIR / f"extract_{PREDICTIONS_VERSION}.json"
        assert pred_file.exists(), (
            f"Frozen predictions not found: {pred_file}. "
            "Commit the example predictions or run with --runlive to regenerate."
        )

    def test_predictions_is_dict_keyed_by_id(self) -> None:
        """Predictions file must be a JSON object keyed by row_id."""
        from tests.parsing.golden_loader import load_predictions  # noqa: PLC0415
        preds = load_predictions(PREDICTIONS_VERSION)
        assert isinstance(preds, dict)
        for row_id in preds:
            assert isinstance(row_id, int), f"Key {row_id!r} should be int"

    def test_each_prediction_has_is_relevant(self) -> None:
        """Each prediction row must have 'is_relevant'."""
        from tests.parsing.golden_loader import load_predictions  # noqa: PLC0415
        preds = load_predictions(PREDICTIONS_VERSION)
        for row_id, pred in preds.items():
            assert "is_relevant" in pred, f"Prediction {row_id} missing is_relevant"


# ---------------------------------------------------------------------------
# TZ §6.1.3 Gate Tests — BLOCK CI
# ---------------------------------------------------------------------------


class TestTelegramAccuracyGate:
    """
    TZ §6.1.3 gate: recall ≥80% and field precision ≥85% on the golden set.

    Scores FROZEN predictions — no live Anthropic call — so the gate is
    deterministic and safe under the CI placeholder ANTHROPIC_API_KEY.
    """

    @pytest.fixture(scope="class")
    def gold(self) -> list[dict[str, Any]]:
        """Load golden set (falls back to example fixture in CI)."""
        from tests.parsing.golden_loader import load_golden_set  # noqa: PLC0415
        return load_golden_set(None)

    @pytest.fixture(scope="class")
    def predictions(self) -> dict[int, dict[str, Any]]:
        """Load frozen predictions (pinned to prompt_version v1)."""
        from tests.parsing.golden_loader import load_predictions  # noqa: PLC0415
        return load_predictions(PREDICTIONS_VERSION)

    @pytest.fixture(scope="class")
    def synonyms(self) -> dict[str, str]:
        """Load synonym map."""
        from tests.parsing.golden_loader import load_synonyms  # noqa: PLC0415
        return load_synonyms(None)

    @pytest.fixture(scope="class")
    def breakdown(
        self,
        gold: list[dict[str, Any]],
        predictions: dict[int, dict[str, Any]],
        synonyms: dict[str, str],
    ) -> dict[str, Any]:
        """Compute full per-field + per-failure-mode breakdown (once per class)."""
        from tests.parsing.eval_metrics import per_field_breakdown  # noqa: PLC0415
        return per_field_breakdown(gold, predictions, synonyms)

    def _print_breakdown_report(
        self,
        breakdown: dict[str, Any],
        n_rows: int,
    ) -> None:
        """Print UZEX-harness-style breakdown table."""
        from tests.parsing.eval_config import (  # noqa: PLC0415
            GATE_FIELDS,
            PRECISION_GATE,
            RECALL_GATE,
        )

        recall = breakdown["recall"]
        precision = breakdown["precision"]
        tp = breakdown["tp_count"]
        per_field = breakdown["per_field"]
        failure_modes = breakdown["failure_modes"]
        n_fields = len(GATE_FIELDS)

        print(f"\n{'='*65}")
        print(f"Telegram AI Accuracy Report — {n_rows} rows × {n_fields} gate fields")
        print(f"{'='*65}")
        print(f"  {'D1 Recall':30s}: {recall:.1%}  [gate ≥{RECALL_GATE:.0%}]")
        print(f"  {'Field Precision (D3-D9)':30s}: {precision:.1%}  [gate ≥{PRECISION_GATE:.0%}]")
        print(f"  {'True positives':30s}: {tp}/{n_rows}")
        print(f"{'─'*65}")
        print("  Per-field precision breakdown:")
        for field in GATE_FIELDS:
            counts = per_field.get(field, {})
            correct = counts.get("correct", 0)
            total = counts.get("total", 0)
            pct = 100.0 * correct / total if total > 0 else float("nan")
            status = "OK" if pct >= PRECISION_GATE * 100 else ("N/A" if total == 0 else "BELOW")
            print(f"    {field:20s}: {correct:3d}/{total:3d} = {pct:6.1f}%  [{status}]")
        print(f"{'─'*65}")
        print("  Failure modes (report-only):")
        for mode, count in failure_modes.items():
            print(f"    {mode:25s}: {count}")
        print(f"{'='*65}")

    @pytest.mark.gate
    def test_recall_gte_80_percent(
        self,
        gold: list[dict[str, Any]],
        breakdown: dict[str, Any],
    ) -> None:
        """D1: Recall ≥ 80% over is_relevant=True gold rows (TZ §6.1.3 gate — BLOCKS CI).

        A false negative is a genuine market signal the system misses.
        Recall < 80% means the team never sees >20% of live buy/sell leads.
        """
        from tests.parsing.eval_config import RECALL_GATE  # noqa: PLC0415
        self._print_breakdown_report(breakdown, len(gold))
        recall = breakdown["recall"]
        assert recall >= RECALL_GATE, (
            f"TZ §6.1.3 FAILED: recall {recall:.1%} < {RECALL_GATE:.0%} gate.\n"
            f"  True positives: {breakdown['tp_count']}/{len(gold)} rows\n"
            f"  False negatives: {breakdown['failure_modes']['false_negative']}\n"
            "  Fix the prompt or add the failing rows to the golden set, "
            "regenerate frozen predictions, and re-run."
        )

    @pytest.mark.gate
    def test_field_precision_gte_85_percent(
        self,
        gold: list[dict[str, Any]],
        breakdown: dict[str, Any],
    ) -> None:
        """D3-D9: Aggregate field precision ≥ 85% over true-positive rows (TZ §6.1.3 gate — BLOCKS CI).

        Precision < 85% means extracted fields are incorrect in >15% of cases,
        leading to wrong prices, grades, or counterparties in the analyst feed.
        """
        from tests.parsing.eval_config import GATE_FIELDS, PRECISION_GATE  # noqa: PLC0415
        precision = breakdown["precision"]
        per_field = breakdown["per_field"]
        below_fields = [
            f for f in GATE_FIELDS
            if per_field.get(f, {}).get("total", 0) > 0
            and (per_field[f]["correct"] / per_field[f]["total"]) < PRECISION_GATE
        ]
        assert precision >= PRECISION_GATE, (
            f"TZ §6.1.3 FAILED: aggregate field precision {precision:.1%} < {PRECISION_GATE:.0%} gate.\n"
            f"  Fields below gate: {below_fields}\n"
            "  Fix the prompt or synonym map, regenerate frozen predictions, and re-run.\n"
            "  (Do NOT edit v1 prompt — create extract_v2.md and re-run.)"
        )


# ---------------------------------------------------------------------------
# Report-only dimensions (D2/D10/D12/D14) — NEVER fail the build
# ---------------------------------------------------------------------------


class TestReportOnlyDimensions:
    """
    D2/D10/D12/D14 report-only dimensions.

    These NEVER fail the build — they print a warning so a regression is
    visible without being a red gate (per AI-SPEC §5.4 / §6 gating policy).
    """

    @pytest.fixture(scope="class")
    def gold(self) -> list[dict[str, Any]]:
        from tests.parsing.golden_loader import load_golden_set  # noqa: PLC0415
        return load_golden_set(None)

    @pytest.fixture(scope="class")
    def predictions(self) -> dict[int, dict[str, Any]]:
        from tests.parsing.golden_loader import load_predictions  # noqa: PLC0415
        return load_predictions(PREDICTIONS_VERSION)

    def test_d2_relevance_precision_report_only(
        self,
        gold: list[dict[str, Any]],
        predictions: dict[int, dict[str, Any]],
    ) -> None:
        """D2: Relevance precision (anti-pollution) — report-only, never blocks CI.

        Prints false-positive rate (spam/ads classified as relevant).
        A rising false-positive rate means feed pollution and analyst trust loss.
        """
        irrelevant_gold = [r for r in gold if not r.get("is_relevant", False)]
        if not irrelevant_gold:
            print("\nD2: No irrelevant gold rows to compute precision on")
            return

        fp = sum(
            1 for r in irrelevant_gold
            if predictions.get(r["id"], {}).get("is_relevant", False)
        )
        len(irrelevant_gold) - fp
        relevance_precision_denom = sum(
            1 for pred in predictions.values() if pred.get("is_relevant", False)
        )
        tp_pred = sum(
            1 for r in gold
            if r.get("is_relevant") and predictions.get(r["id"], {}).get("is_relevant")
        )
        precision_d2 = tp_pred / relevance_precision_denom if relevance_precision_denom > 0 else 1.0
        fp_rate = fp / len(irrelevant_gold)
        print(
            f"\nD2 Relevance Precision (report-only): {precision_d2:.1%}  "
            f"| FP rate: {fp_rate:.1%} ({fp}/{len(irrelevant_gold)} irrelevant rows misclassified)"
        )
        # NEVER assert — report only
        if fp_rate > 0.10:
            print(
                f"WARNING D2: FP rate {fp_rate:.1%} > 10% — feed pollution risk. "
                "Investigate prompt or add adversarial irrelevant rows to golden set."
            )

    def test_d12_fabrication_rate_report_only(
        self,
        gold: list[dict[str, Any]],
        predictions: dict[int, dict[str, Any]],
    ) -> None:
        """D12: Fabricated-field (hallucination) rate — report-only, never blocks CI.

        Counts fields where gold=null but system provides a value (fabrication).
        Rising fabrication rate pages a human (§7 alarm threshold: >2%).
        """
        from tests.parsing.eval_config import GATE_FIELDS  # noqa: PLC0415

        fabrication_count = 0
        total_null_fields = 0

        for row in gold:
            if not row.get("is_relevant", False):
                continue
            row_id = row["id"]
            pred = predictions.get(row_id, {})
            if not pred.get("is_relevant", False):
                continue  # FN row — not a TP

            expected = row.get("expected", {}) or {}
            for field in GATE_FIELDS:
                gold_val = expected.get(field)
                if gold_val is None:
                    total_null_fields += 1
                    if pred.get(field) is not None:
                        fabrication_count += 1

        rate = fabrication_count / total_null_fields if total_null_fields > 0 else 0.0
        print(
            f"\nD12 Fabrication rate (report-only): {rate:.1%} "
            f"({fabrication_count}/{total_null_fields} gold-null fields with sys value)"
        )
        # NEVER assert — report only (§6 gating policy)
        if rate > 0.02:
            print(
                f"WARNING D12: Fabrication rate {rate:.1%} > 2% alarm threshold (AI-SPEC §7). "
                "Investigate: hallucinated fields are the headline FM#1 risk. "
                "Add null-rich rows to golden set and fix the null-semantics prompt instruction."
            )

    def test_d14_stale_repost_report_only(
        self,
        gold: list[dict[str, Any]],
        predictions: dict[int, dict[str, Any]],
    ) -> None:
        """D14: Stale/forwarded-repost detection — report-only, never blocks CI.

        Checks forwarded-message rows: if fwd_from is set and gold is_relevant=False
        (stale repost), and the system classifies as relevant, that is a miss.
        """
        fwd_rows = [r for r in gold if r.get("fwd_from") is not None]
        if not fwd_rows:
            print("\nD14: No forwarded rows in this golden set")
            return

        stale_misses = [
            r for r in fwd_rows
            if not r.get("is_relevant", False)
            and predictions.get(r["id"], {}).get("is_relevant", False)
        ]
        print(
            f"\nD14 Stale-repost detection (report-only): "
            f"{len(stale_misses)}/{len(fwd_rows)} forwarded rows misclassified as relevant"
        )
        if stale_misses:
            print(
                "WARNING D14: System classified stale reposts as relevant signals. "
                "Review fwd_from.date handling in the prompt and extractor."
            )


# ---------------------------------------------------------------------------
# --runlive refresh path (local only — skipped in CI)
# ---------------------------------------------------------------------------


def pytest_addoption(parser: Any) -> None:
    """Add --runlive option for the refresh path."""
    # Option may already be added by another conftest
    with contextlib.suppress(ValueError):
        parser.addoption(
            "--runlive",
            action="store_true",
            default=False,
            help="Enable live Anthropic API calls for prediction refresh (local only)",
        )


@pytest.fixture
def runlive(request: pytest.FixtureRequest) -> bool:
    """Return True if --runlive was passed."""
    return bool(request.config.getoption("--runlive", default=False))


@pytest.mark.refresh
def test_refresh_frozen_predictions(runlive: bool) -> None:
    """@pytest.mark.refresh — regenerate frozen predictions via live LLM.

    LOCAL ONLY.  Requires a real ANTHROPIC_API_KEY and --runlive flag.
    Skipped in CI (--runlive not passed).

    Usage:
        pytest tests/parsing/test_telegram_accuracy.py -m refresh --runlive
    """
    if not runlive:
        pytest.skip("Pass --runlive to regenerate frozen predictions (local only)")

    from tests.parsing.golden_loader import refresh_predictions  # noqa: PLC0415
    predictions = refresh_predictions(
        PREDICTIONS_VERSION,
        runlive=True,
    )
    assert isinstance(predictions, dict)
    assert len(predictions) > 0, "refresh_predictions returned empty dict"
    print(f"\nRefreshed {len(predictions)} frozen predictions for version {PREDICTIONS_VERSION!r}")
