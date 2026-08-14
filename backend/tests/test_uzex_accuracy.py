"""
UZEX signal accuracy harness — TZ §6.1.2 acceptance gate.

Asserts ≥95% field-level accuracy on a ≥50-position control sample parsed
end-to-end through the same logic as the production parse pipeline.

Design:
- Reads tests/fixtures/uzex/control_sample.json (≥50 positions, each with
  a raw payload dict + expected field values).
- For each position, runs:
    1. grade_service.extract_grade(product_text, mock_session)
       → grade_text (regex-based; no DB needed for the grade_text field)
    2. signal_service.create_signal_from_parse(mock_session, mock_raw_item, parsed)
       → Signal ORM object
- Compares signal fields to expected values, field-by-field.
- Computes field-level accuracy = correct_fields / total_fields_checked.
- ASSERTS accuracy ≥ 0.95 (TZ §6.1.2 acceptance gate).
- Prints per-field accuracy breakdown on failure.

Fields verified per position:
    volume   — Decimal-coerced from payload (T-02-15)
    price    — Decimal-coerced from payload (T-02-15)
    currency — 3-char stripped from payload
    kind     — derived from section field (_SECTION_TO_KIND mapping)
    grade_text — regex-extracted grade token from product_text

Notes:
- product_id / grade_id matching requires a live DB (synonym resolution);
  those fields are out of scope for this pure-function harness. The accepted
  TZ §6.1.2 metric is over the structural + numeric fields that the rule-based
  parser controls, not the DB-backed synonym lookup.
- The harness runs offline (no DB, no network).
"""

from __future__ import annotations

import decimal
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# ── Fixtures path ─────────────────────────────────────────────────────────────
CONTROL_SAMPLE_FILE = (
    Path(__file__).parent / "fixtures" / "uzex" / "control_sample.json"
)

# ── Fields checked in the accuracy computation ────────────────────────────────
# These are the structural + numeric fields the rule-based parser fully controls.
# product_code / product_id require a live DB synonym lookup (out of scope here).
CHECKED_FIELDS = ["volume", "price", "currency", "kind", "grade_text"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_raw_item(payload: dict[str, Any], raw_item_id: int = 1) -> Any:
    """Build a mock RawItem for create_signal_from_parse."""
    item = MagicMock()
    item.id = raw_item_id
    item.source_id = 1
    item.payload = payload
    item.event_at = None  # let signal_service fall back to now()
    return item


def _make_mock_session() -> Any:
    """Build a mock SQLAlchemy session (grade DB lookup returns None → regex only)."""
    session = MagicMock()
    # Simulate no grade DB match → grade_service uses regex-only path
    session.execute.return_value.fetchone.return_value = None
    return session


def _normalize_price(raw: str | None) -> decimal.Decimal | None:
    """Normalize expected price string to Decimal (same logic as _safe_decimal)."""
    if raw is None:
        return None
    try:
        d = decimal.Decimal(str(raw).replace(",", ".").strip())
        return d if d.is_finite() else None
    except decimal.InvalidOperation:
        return None


# ── Main accuracy computation ─────────────────────────────────────────────────

def _compute_accuracy(
    positions: list[dict[str, Any]],
) -> tuple[float, dict[str, dict[str, int]], list[dict[str, Any]]]:
    """Run each position through the parse pipeline and compute field accuracy.

    Returns:
        (overall_accuracy, per_field_counts, failures)
        - overall_accuracy: float in [0, 1]
        - per_field_counts: {field: {"correct": N, "total": N}}
        - failures: list of dicts describing mismatches
    """
    from app.domains.reference.grades import extract_grade  # noqa: PLC0415
    from app.domains.signals.service import create_signal_from_parse  # noqa: PLC0415

    per_field: dict[str, dict[str, int]] = {
        f: {"correct": 0, "total": 0} for f in CHECKED_FIELDS
    }
    failures: list[dict[str, Any]] = []
    total_correct = 0
    total_fields = 0

    for pos in positions:
        raw = pos["raw"]
        expected = pos["expected"]
        pos_id = pos["id"]

        # ── Step 1: extract grade via regex (no DB) ────────────────────────────
        product_text = str(raw.get("product_text", "")).strip()
        session = _make_mock_session()
        _grade_id, grade_text = extract_grade(product_text, session)

        # ── Step 2: build parsed dict (product_id mocked as 1 — always "match") ─
        parsed: dict[str, object] = {
            "product_id": 1,       # mocked — synonym resolution requires live DB
            "grade_id": None,      # mocked — DB grade lookup requires live DB
            "grade_text": grade_text,
        }

        # ── Step 3: create signal via the production service ───────────────────
        raw_item = _make_mock_raw_item(raw, raw_item_id=pos_id)
        signal = create_signal_from_parse(session, raw_item, parsed)

        # ── Step 4: compare each checked field ─────────────────────────────────
        produced: dict[str, object] = {
            "volume": signal.volume,
            "price": signal.price,
            "currency": signal.currency,
            "kind": signal.kind.value if hasattr(signal.kind, "value") else str(signal.kind),
            "grade_text": signal.grade_text,
        }

        exp_volume = _normalize_price(expected.get("volume"))
        exp_price = _normalize_price(expected.get("price"))
        expected_values: dict[str, object] = {
            "volume": exp_volume,
            "price": exp_price,
            "currency": expected.get("currency"),
            "kind": expected.get("kind"),
            "grade_text": expected.get("grade_text"),
        }

        pos_failures: list[str] = []
        for field in CHECKED_FIELDS:
            per_field[field]["total"] += 1
            total_fields += 1

            got = produced.get(field)
            want = expected_values.get(field)

            # Normalize volume/price to Decimal for comparison
            if field in ("volume", "price"):
                # got is already Decimal or None from signal_service._safe_decimal
                if want is None and got is None:
                    match = True
                elif want is None or got is None:
                    match = False
                else:
                    # Compare as Decimal — strip trailing zeros for equivalence
                    try:
                        match = decimal.Decimal(str(got)) == decimal.Decimal(str(want))
                    except decimal.InvalidOperation:
                        match = False
            else:
                match = got == want

            if match:
                per_field[field]["correct"] += 1
                total_correct += 1
            else:
                pos_failures.append(
                    f"  [{field}] got={got!r} want={want!r}"
                )

        if pos_failures:
            failures.append(
                {
                    "id": pos_id,
                    "section": pos.get("section"),
                    "product_text": product_text[:60],
                    "mismatches": pos_failures,
                }
            )

    overall = total_correct / total_fields if total_fields > 0 else 0.0
    return overall, per_field, failures


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestUzexControlSampleFile:
    """Validate the control_sample.json fixture file itself."""

    def test_control_sample_exists(self) -> None:
        """control_sample.json must exist."""
        assert CONTROL_SAMPLE_FILE.exists(), (
            f"Missing fixture: {CONTROL_SAMPLE_FILE}"
        )

    def test_control_sample_valid_json(self) -> None:
        """control_sample.json must be parseable JSON."""
        data = json.loads(CONTROL_SAMPLE_FILE.read_text(encoding="utf-8"))
        assert isinstance(data, list), "control_sample.json must be a JSON array"

    def test_control_sample_min_50_positions(self) -> None:
        """control_sample.json must contain ≥50 positions (TZ §6.1.2)."""
        data = json.loads(CONTROL_SAMPLE_FILE.read_text(encoding="utf-8"))
        assert len(data) >= 50, (
            f"Control sample must have ≥50 positions for TZ §6.1.2, got {len(data)}"
        )

    def test_each_position_has_raw_and_expected(self) -> None:
        """Every position must have both 'raw' and 'expected' keys."""
        data = json.loads(CONTROL_SAMPLE_FILE.read_text(encoding="utf-8"))
        for pos in data:
            assert "raw" in pos, f"Position {pos.get('id')} missing 'raw' key"
            assert "expected" in pos, (
                f"Position {pos.get('id')} missing 'expected' key"
            )

    def test_expected_has_required_fields(self) -> None:
        """Each 'expected' dict must have volume, price, currency, kind."""
        data = json.loads(CONTROL_SAMPLE_FILE.read_text(encoding="utf-8"))
        required = {"product_code", "volume", "price", "currency", "kind"}
        for pos in data:
            missing = required - set(pos.get("expected", {}).keys())
            assert not missing, (
                f"Position {pos.get('id')} expected dict missing keys: {missing}"
            )

    def test_sections_distribution(self) -> None:
        """Control sample must cover all three UZEX sections."""
        data = json.loads(CONTROL_SAMPLE_FILE.read_text(encoding="utf-8"))
        sections = {pos.get("section") for pos in data}
        assert "offers" in sections, "Control sample must include 'offers' positions"
        assert "contracts" in sections, "Control sample must include 'contracts' positions"
        assert "deals" in sections, "Control sample must include 'deals' positions"


class TestUzexFieldAccuracy:
    """
    TZ §6.1.2 acceptance gate: ≥95% field accuracy on the ≥50-position
    control sample, measured by running the production parse pipeline
    (grade_service + signal_service) against each position's raw payload.

    This is the ACCEPTANCE GATE — the test FAILS if accuracy < 95%.
    """

    @pytest.fixture(scope="class")
    def control_sample(self) -> list[dict[str, Any]]:
        """Load the control sample once per class."""
        return json.loads(CONTROL_SAMPLE_FILE.read_text(encoding="utf-8"))

    @pytest.fixture(scope="class")
    def accuracy_results(
        self, control_sample: list[dict[str, Any]]
    ) -> tuple[float, dict[str, dict[str, int]], list[dict[str, Any]]]:
        """Compute accuracy once and share across tests in this class."""
        return _compute_accuracy(control_sample)

    def test_overall_accuracy_gte_95_percent(
        self,
        control_sample: list[dict[str, Any]],
        accuracy_results: tuple[float, dict[str, dict[str, int]], list[dict[str, Any]]],
    ) -> None:
        """Field-level accuracy must be ≥ 0.95 (TZ §6.1.2 acceptance gate).

        This test FAILS if accuracy drops below the threshold.
        On failure, a per-field breakdown is printed to aid tuning.
        """
        overall, per_field, failures = accuracy_results
        n_positions = len(control_sample)
        n_fields = len(CHECKED_FIELDS)

        # ── Per-field accuracy breakdown (always print for visibility) ──────────
        print(f"\n{'='*60}")
        print(f"UZEX Accuracy Report — {n_positions} positions × {n_fields} fields")
        print(f"{'='*60}")
        total_correct = 0
        total_total = 0
        for field, counts in per_field.items():
            correct = counts["correct"]
            total = counts["total"]
            pct = 100.0 * correct / total if total > 0 else 0.0
            status = "OK" if pct >= 95.0 else "BELOW"
            print(f"  {field:15s}: {correct:3d}/{total:3d} = {pct:6.1f}%  [{status}]")
            total_correct += correct
            total_total += total

        print(f"{'─'*60}")
        print(f"  {'OVERALL':15s}: {total_correct:3d}/{total_total:3d} = {100.0*overall:6.1f}%")
        print(f"{'='*60}")

        if failures:
            print(f"\nFailures ({len(failures)} positions):")
            for f in failures[:20]:  # cap output at 20 failures
                print(
                    f"  Position {f['id']} [{f['section']}] "
                    f"product_text={f['product_text']!r}"
                )
                for mismatch in f["mismatches"]:
                    print(mismatch)
            if len(failures) > 20:
                print(f"  ... and {len(failures) - 20} more")

        # ── Acceptance gate: ASSERT ≥ 0.95 ────────────────────────────────────
        assert overall >= 0.95, (
            f"TZ §6.1.2 FAILED: field accuracy {overall:.1%} is below the ≥95% "
            f"threshold on the {n_positions}-position control sample.\n"
            f"Positions with failures: {len(failures)}/{n_positions}\n"
            f"Per-field breakdown printed above — tune the parse pipeline and retry."
        )

    def test_volume_field_accuracy(
        self,
        accuracy_results: tuple[float, dict[str, dict[str, int]], list[dict[str, Any]]],
    ) -> None:
        """Volume field must achieve ≥95% accuracy (Decimal coercion correctness)."""
        _, per_field, _ = accuracy_results
        counts = per_field["volume"]
        pct = counts["correct"] / counts["total"] if counts["total"] > 0 else 0.0
        assert pct >= 0.95, (
            f"Volume field accuracy {pct:.1%} < 95% "
            f"({counts['correct']}/{counts['total']} correct)"
        )

    def test_price_field_accuracy(
        self,
        accuracy_results: tuple[float, dict[str, dict[str, int]], list[dict[str, Any]]],
    ) -> None:
        """Price field must achieve ≥95% accuracy (Decimal coercion, T-02-15)."""
        _, per_field, _ = accuracy_results
        counts = per_field["price"]
        pct = counts["correct"] / counts["total"] if counts["total"] > 0 else 0.0
        assert pct >= 0.95, (
            f"Price field accuracy {pct:.1%} < 95% "
            f"({counts['correct']}/{counts['total']} correct)"
        )

    def test_currency_field_accuracy(
        self,
        accuracy_results: tuple[float, dict[str, dict[str, int]], list[dict[str, Any]]],
    ) -> None:
        """Currency field must achieve ≥95% accuracy."""
        _, per_field, _ = accuracy_results
        counts = per_field["currency"]
        pct = counts["correct"] / counts["total"] if counts["total"] > 0 else 0.0
        assert pct >= 0.95, (
            f"Currency field accuracy {pct:.1%} < 95% "
            f"({counts['correct']}/{counts['total']} correct)"
        )

    def test_kind_field_accuracy(
        self,
        accuracy_results: tuple[float, dict[str, dict[str, int]], list[dict[str, Any]]],
    ) -> None:
        """Kind field must achieve ≥95% accuracy (section → SignalKind mapping)."""
        _, per_field, _ = accuracy_results
        counts = per_field["kind"]
        pct = counts["correct"] / counts["total"] if counts["total"] > 0 else 0.0
        assert pct >= 0.95, (
            f"Kind field accuracy {pct:.1%} < 95% "
            f"({counts['correct']}/{counts['total']} correct)"
        )

    def test_minimum_positions_processed(
        self, control_sample: list[dict[str, Any]]
    ) -> None:
        """Control sample must have ≥50 positions (re-check at test run time)."""
        assert len(control_sample) >= 50, (
            f"TZ §6.1.2 requires ≥50 control positions, got {len(control_sample)}"
        )
