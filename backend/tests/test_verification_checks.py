"""Pure unit tests for verification_checks (R1 W4 — T4.2).

DB-free. The docs-complete matrix by role, bank-requisite rules (incl. the
decrypt-to-check-length path), tax-id format, and manual-KYB-always-pending.
"""

from __future__ import annotations

import pytest


def _company(jurisdiction: str = "UZ", tax_id: str = "123456789"):  # noqa: ANN202
    from app.domains.companies.models import Company  # noqa: PLC0415

    return Company(jurisdiction=jurisdiction, tax_id=tax_id)


def _bank(mfo: str = "00014", number: str = "20208000900040041234"):  # noqa: ANN202
    from app.core.crypto import encrypt_pii  # noqa: PLC0415
    from app.domains.companies.models import CompanyBankAccount  # noqa: PLC0415

    return CompanyBankAccount(
        bank_mfo=mfo,
        account_number_enc=encrypt_pii(number),
        account_last4=number[-4:],
    )


def _doc(kind, status=None):  # noqa: ANN001, ANN202
    from app.domains.verification.models import VerificationDocument  # noqa: PLC0415
    from app.models.enums import DocumentReviewStatus  # noqa: PLC0415

    return VerificationDocument(
        kind=kind,
        storage_path="x",
        sha256="y",
        status=status or DocumentReviewStatus.pending_review,
    )


# ── tax id ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("jurisdiction", "tax_id", "expected"),
    [
        ("UZ", "123456789", "passed"),
        ("UZ", "12345678", "failed"),
        ("UZ", "1234567890", "failed"),
        ("UZ", "12345678x", "failed"),
        ("KZ", "any-nonempty", "passed"),
        ("KZ", "", "failed"),
    ],
)
def test_check_tax_id_format(jurisdiction: str, tax_id: str, expected: str) -> None:
    from app.domains.verification.checks import check_tax_id_format  # noqa: PLC0415

    result = check_tax_id_format(_company(jurisdiction, tax_id))
    assert result.status.value == expected


# ── bank requisites ───────────────────────────────────────────────────────────


def test_bank_requisites_no_account_is_warning() -> None:
    from app.domains.verification.checks import check_bank_requisites  # noqa: PLC0415

    result = check_bank_requisites(_company(), [])
    assert result.status.value == "warning"
    assert result.result["reason"] == "no_bank_account"


def test_bank_requisites_valid_account_passes() -> None:
    from app.domains.verification.checks import check_bank_requisites  # noqa: PLC0415

    result = check_bank_requisites(_company(), [_bank()])
    assert result.status.value == "passed"
    assert result.result["problems"] == []


def test_bank_requisites_bad_mfo_and_length_fail_without_leaking_number() -> None:
    from app.domains.verification.checks import check_bank_requisites  # noqa: PLC0415

    result = check_bank_requisites(
        _company(), [_bank(mfo="123", number="123456789")]  # short MFO + short number
    )
    assert result.status.value == "failed"
    issues = {p["issue"] for p in result.result["problems"]}  # type: ignore[union-attr]
    assert issues == {"bad_mfo", "bad_account_length"}
    # Full number never leaks into the payload — only the masked last4.
    assert "123456789" not in str(result.result)


# ── documents complete (matrix by role + bank) ────────────────────────────────


def test_documents_registration_certificate_always_required() -> None:
    from app.domains.verification.checks import check_documents_complete  # noqa: PLC0415

    result = check_documents_complete(_company(), [], [], has_bank_account=False)
    assert result.status.value == "failed"
    assert "registration_certificate" in result.result["missing"]  # type: ignore[operator]


def test_documents_reg_cert_only_passes_without_bank() -> None:
    from app.domains.verification.checks import check_documents_complete  # noqa: PLC0415
    from app.models.enums import VerificationDocumentKind  # noqa: PLC0415

    docs = [_doc(VerificationDocumentKind.registration_certificate)]
    result = check_documents_complete(_company(), docs, [], has_bank_account=False)
    assert result.status.value == "passed"


def test_documents_eimzo_supersedes_registration_certificate() -> None:
    # R3 TA1.5: a passed E-IMZO signature drops the reg-cert requirement.
    from app.domains.verification.checks import check_documents_complete  # noqa: PLC0415

    result = check_documents_complete(
        _company(), [], [], has_bank_account=False, eimzo_passed=True
    )
    assert result.status.value == "passed"
    assert result.result["missing"] == []
    assert result.result["eimzo_passed"] is True


def test_documents_eimzo_does_not_relax_bank_letter() -> None:
    # bank_letter rule is unchanged by E-IMZO (TA1.5).
    from app.domains.verification.checks import check_documents_complete  # noqa: PLC0415

    result = check_documents_complete(
        _company(), [], [], has_bank_account=True, eimzo_passed=True
    )
    assert result.status.value == "failed"
    assert result.result["missing"] == ["bank_letter"]


def test_documents_bank_letter_required_when_bank_present() -> None:
    from app.domains.verification.checks import check_documents_complete  # noqa: PLC0415
    from app.models.enums import VerificationDocumentKind  # noqa: PLC0415

    docs = [_doc(VerificationDocumentKind.registration_certificate)]
    result = check_documents_complete(_company(), docs, [], has_bank_account=True)
    assert result.status.value == "failed"
    assert result.result["missing"] == ["bank_letter"]

    docs.append(_doc(VerificationDocumentKind.bank_letter))
    ok = check_documents_complete(_company(), docs, [], has_bank_account=True)
    assert ok.status.value == "passed"


def test_documents_role_specific_requirements() -> None:
    from app.domains.verification.checks import check_documents_complete  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole, VerificationDocumentKind  # noqa: PLC0415

    docs = [_doc(VerificationDocumentKind.registration_certificate)]
    # insurance_provider needs a license
    result = check_documents_complete(
        _company(), docs, [CompanyBusinessRole.insurance_provider], has_bank_account=False
    )
    assert result.status.value == "failed"
    assert result.result["missing"] == ["license"]

    # a plain trader needs nothing extra
    ok = check_documents_complete(
        _company(), docs, [CompanyBusinessRole.trader], has_bank_account=False
    )
    assert ok.status.value == "passed"


def test_documents_rejected_docs_do_not_count() -> None:
    from app.domains.verification.checks import check_documents_complete  # noqa: PLC0415
    from app.models.enums import DocumentReviewStatus, VerificationDocumentKind  # noqa: PLC0415

    docs = [_doc(VerificationDocumentKind.registration_certificate, DocumentReviewStatus.rejected)]
    result = check_documents_complete(_company(), docs, [], has_bank_account=False)
    assert result.status.value == "failed"  # the only cert was rejected → still missing


def test_manual_kyb_is_pending() -> None:
    from app.domains.verification.checks import check_manual_kyb  # noqa: PLC0415

    assert check_manual_kyb().status.value == "pending"
