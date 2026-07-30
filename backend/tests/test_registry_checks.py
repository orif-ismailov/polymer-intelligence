"""Registry verification checks (R6 / P7.c — T5.1). Pure functions, no DB.

Two checks read the newest `registry_snapshots` row and turn it into a verdict.
They are pure so that the SAME code judges a ПЦД answer and an operator's
transcription of my.soliq.uz — the only difference between those lives in the
snapshot's `source` column, which is where it belongs.

The verdicts encode three judgements that are easy to get wrong:

  * **No snapshot is `unavailable`, never `failed`.** We have no registry channel
    yet; that is a fact about us, not about the company (the R1 degradation
    invariant).
  * **Not being a VAT payer is a `warning`, not a `failure`.** Not every Uzbek
    company is obliged to register for VAT, so refusing verification on that
    ground would be legally wrong.
  * **A name that does not match is a `warning`; a liquidated company is a
    `failure`.** Legal names carry quotes, legal-form prefixes and
    transliterations that differ harmlessly between sources — a mismatch is
    something to look at. Liquidation is not.
"""

from __future__ import annotations

import pytest


class _Company:
    """Just the two fields the checks read."""

    def __init__(self, tax_id: str = "301234567", legal_name: str | None = None) -> None:
        self.tax_id = tax_id
        self.legal_name = legal_name


class _Snapshot:
    """Stand-in for a `RegistrySnapshot` row (the checks only read `payload`)."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload


# ── gov_registry ──────────────────────────────────────────────────────────────


def test_no_snapshot_is_unavailable_not_a_failure() -> None:
    """Missing our integration must never look like a finding about the company."""
    from app.models.enums import VerificationCheckStatus
    from app.services import verification_checks

    result = verification_checks.check_gov_registry(_Company(), None)

    assert result.status == VerificationCheckStatus.unavailable
    assert result.result["reason"] == "no_snapshot"


def test_an_active_company_with_a_matching_name_passes() -> None:
    from app.models.enums import VerificationCheckStatus
    from app.services import verification_checks

    company = _Company(legal_name='ООО "ПОЛИМЕР ТРЕЙД"')
    snapshot = _Snapshot(
        {"inn": "301234567", "name": 'ООО "Полимер Трейд"', "status": "active"}
    )

    result = verification_checks.check_gov_registry(company, snapshot)

    assert result.status == VerificationCheckStatus.passed
    assert result.result["registry_status"] == "active"


@pytest.mark.parametrize(
    ("ours", "theirs"),
    [
        ('ООО "ПОЛИМЕР ТРЕЙД"', "OOO Polimer Trade"),   # transliteration is NOT equal
        ('ООО "ПОЛИМЕР ТРЕЙД"', 'ООО «ПОЛИМЕР ТРЕЙД»'),  # only the quotes differ
        ("MCHJ POLIMER TRADE", 'ООО "POLIMER TRADE"'),   # legal form differs
        ("Polimer   Trade", "Polimer Trade"),            # whitespace
    ],
)
def test_harmless_name_differences_are_not_flagged(ours: str, theirs: str) -> None:
    """A legal name is written differently by every source. Only a real
    difference is worth an operator's attention."""
    from app.models.enums import VerificationCheckStatus
    from app.services import verification_checks

    result = verification_checks.check_gov_registry(
        _Company(legal_name=ours),
        _Snapshot({"inn": "301234567", "name": theirs, "status": "active"}),
    )

    if ours.startswith('ООО "ПОЛИМЕР') and theirs.startswith("OOO Polimer"):
        # Cyrillic vs Latin IS a real difference — we do not transliterate.
        assert result.status == VerificationCheckStatus.warning
    else:
        assert result.status == VerificationCheckStatus.passed, result.result


def test_a_genuinely_different_name_is_a_warning() -> None:
    """The registry is authoritative, but our record may be a trading name —
    a human compares, we do not reject."""
    from app.models.enums import VerificationCheckStatus
    from app.services import verification_checks

    result = verification_checks.check_gov_registry(
        _Company(legal_name='ООО "ПОЛИМЕР ТРЕЙД"'),
        _Snapshot({"inn": "301234567", "name": 'ООО "ХИМСНАБ"', "status": "active"}),
    )

    assert result.status == VerificationCheckStatus.warning
    assert result.result["name_matches"] is False
    assert result.result["registry_name"] == 'ООО "ХИМСНАБ"'


def test_a_registry_with_no_name_still_passes() -> None:
    """Nothing to compare is not a mismatch."""
    from app.models.enums import VerificationCheckStatus
    from app.services import verification_checks

    result = verification_checks.check_gov_registry(
        _Company(legal_name='ООО "ПОЛИМЕР ТРЕЙД"'),
        _Snapshot({"inn": "301234567", "status": "active"}),
    )
    assert result.status == VerificationCheckStatus.passed


def test_a_company_we_have_no_name_for_still_passes() -> None:
    from app.models.enums import VerificationCheckStatus
    from app.services import verification_checks

    result = verification_checks.check_gov_registry(
        _Company(legal_name=None),
        _Snapshot({"inn": "301234567", "name": "OOO ANYTHING", "status": "active"}),
    )
    assert result.status == VerificationCheckStatus.passed


@pytest.mark.parametrize("status", ["liquidated", "suspended"])
def test_a_liquidated_or_suspended_company_fails(status: str) -> None:
    """Neither is a company we may verify without an explicit human override,
    which is what `waive_check` exists for. `warning` would let
    `verification_auto_approve` wave one through."""
    from app.models.enums import VerificationCheckStatus
    from app.services import verification_checks

    result = verification_checks.check_gov_registry(
        _Company(), _Snapshot({"inn": "301234567", "status": status})
    )

    assert result.status == VerificationCheckStatus.failed
    assert result.result["registry_status"] == status


def test_an_unstated_registry_status_is_a_warning() -> None:
    """The registry answered but said nothing about the state — not a pass."""
    from app.models.enums import VerificationCheckStatus
    from app.services import verification_checks

    result = verification_checks.check_gov_registry(
        _Company(), _Snapshot({"inn": "301234567"})
    )
    assert result.status == VerificationCheckStatus.warning


def test_a_snapshot_about_a_different_company_fails() -> None:
    """Either the wrong company was looked up or the registry disagrees about the
    tax id. Both are hard stops, not warnings."""
    from app.models.enums import VerificationCheckStatus
    from app.services import verification_checks

    result = verification_checks.check_gov_registry(
        _Company(tax_id="301234567"),
        _Snapshot({"inn": "309999999", "status": "active"}),
    )

    assert result.status == VerificationCheckStatus.failed
    assert result.result["reason"] == "inn_mismatch"


def test_the_raw_registry_wording_is_carried_into_the_result() -> None:
    """An auditor asks what the registry actually said, not what we mapped it to."""
    from app.services import verification_checks

    result = verification_checks.check_gov_registry(
        _Company(),
        _Snapshot(
            {"inn": "301234567", "status": "active", "raw_status": "ДЕЙСТВУЮЩЕЕ"}
        ),
    )
    assert result.result["raw_status"] == "ДЕЙСТВУЮЩЕЕ"


# ── vat_status ────────────────────────────────────────────────────────────────


def test_no_vat_snapshot_is_unavailable() -> None:
    from app.models.enums import VerificationCheckStatus
    from app.services import verification_checks

    result = verification_checks.check_vat_status(_Company(), None)
    assert result.status == VerificationCheckStatus.unavailable


def test_a_registered_vat_payer_passes() -> None:
    from app.models.enums import VerificationCheckStatus
    from app.services import verification_checks

    result = verification_checks.check_vat_status(
        _Company(),
        _Snapshot({"registered": True, "certificate_no": "3012345670001"}),
    )

    assert result.status == VerificationCheckStatus.passed
    assert result.result["registered"] is True


def test_not_being_a_vat_payer_is_a_warning_not_a_failure() -> None:
    """Not every Uzbek company is obliged to register for VAT. Failing here
    would refuse verification on a legally wrong ground."""
    from app.models.enums import VerificationCheckStatus
    from app.services import verification_checks

    result = verification_checks.check_vat_status(
        _Company(), _Snapshot({"registered": False})
    )

    assert result.status == VerificationCheckStatus.warning
    assert result.result["registered"] is False


def test_the_vat_certificate_number_is_never_invented() -> None:
    from app.services import verification_checks

    result = verification_checks.check_vat_status(
        _Company(), _Snapshot({"registered": True})
    )
    assert result.result["certificate_no"] is None
