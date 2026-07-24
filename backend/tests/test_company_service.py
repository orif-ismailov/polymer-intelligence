"""Pure unit tests for company_service (R1 W4 — T4.1).

DB-free: the company status machine, tax-id/MFO validation, and the bank-account
encryption round-trip (mock session). Membership isolation, uniqueness, profile
gating, and the owner guard against real rows are in test_company_service_db.py.

App imports are lazy (parametrize over status *names*) so ``settings`` is only
built after conftest's patch_env fixture runs.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

_STATUS_NAMES = [
    "draft",
    "pending_verification",
    "verified",
    "rejected",
    "suspended",
    "liquidated",
]

# Legal transitions (mirror company_service._TRANSITIONS), by status name.
_LEGAL = {
    ("draft", "pending_verification"),
    ("pending_verification", "verified"),
    ("pending_verification", "rejected"),
    ("pending_verification", "draft"),
    ("verified", "suspended"),
    ("rejected", "draft"),
    ("suspended", "verified"),
}


def _company(status, company_id: int = 1):  # noqa: ANN001, ANN202
    from app.models.companies import Company  # noqa: PLC0415

    company = Company(jurisdiction="UZ", tax_id="123456789", status=status)
    company.id = company_id
    return company


@pytest.mark.parametrize("frm_name", _STATUS_NAMES)
@pytest.mark.parametrize("to_name", _STATUS_NAMES)
def test_transition_matrix(frm_name: str, to_name: str) -> None:
    from app.models.enums import CompanyStatus  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415

    frm, to = CompanyStatus[frm_name], CompanyStatus[to_name]
    company = _company(frm)
    if (frm_name, to_name) in _LEGAL:
        assert company_service.transition(MagicMock(), company, to).status == to
    else:
        with pytest.raises(company_service.InvalidCompanyTransition):
            company_service.transition(MagicMock(), company, to)
        assert company.status == frm  # unchanged on illegal transition


# ── tax id + MFO validation ───────────────────────────────────────────────────


@pytest.mark.parametrize("tax_id", ["123456789", " 123456789 "])
def test_create_company_accepts_valid_uz_tax_id(tax_id: str) -> None:
    from app.models.accounts import UserAccount  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415

    account = UserAccount(phone="+998901234567")
    account.id = 1
    company = company_service.create_company(MagicMock(), account, "uz", tax_id)
    assert company.jurisdiction == "UZ"
    assert company.tax_id == "123456789"
    assert company.status == CompanyStatus.draft


@pytest.mark.parametrize("tax_id", ["12345", "1234567890", "abcdefghi", ""])
def test_create_company_rejects_bad_uz_tax_id(tax_id: str) -> None:
    from app.models.accounts import UserAccount  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415

    account = UserAccount(phone="+998901234567")
    account.id = 1
    with pytest.raises(company_service.InvalidTaxId):
        company_service.create_company(MagicMock(), account, "UZ", tax_id)


def test_create_company_makes_creator_an_owner_member() -> None:
    from app.models.accounts import UserAccount  # noqa: PLC0415
    from app.models.companies import CompanyMember  # noqa: PLC0415
    from app.models.enums import CompanyMemberRole  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415

    account = UserAccount(phone="+998901234567")
    account.id = 42
    db = MagicMock()
    company_service.create_company(db, account, "UZ", "123456789")

    members = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], CompanyMember)]
    assert len(members) == 1
    assert members[0].member_role == CompanyMemberRole.owner
    assert members[0].user_account_id == 42


# ── bank account (encryption round-trip) ──────────────────────────────────────


@pytest.mark.parametrize("mfo", ["1234", "123456", "abcde", ""])
def test_add_bank_account_rejects_bad_mfo(mfo: str) -> None:
    from app.models.enums import CompanyStatus  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415

    with pytest.raises(company_service.InvalidBankMfo):
        company_service.add_bank_account(
            MagicMock(), _company(CompanyStatus.draft), mfo, "12345678901234567890"
        )


def test_add_bank_account_encrypts_number_and_keeps_last4() -> None:
    from app.core.crypto import decrypt_pii  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415

    row = company_service.add_bank_account(
        MagicMock(), _company(CompanyStatus.draft), "00014", "2020 8000 9000 4004 1234"
    )
    assert row.account_last4 == "1234"
    assert row.bank_mfo == "00014"
    # The clear number never persists — only the ciphertext, which round-trips.
    assert isinstance(row.account_number_enc, bytes)
    assert decrypt_pii(row.account_number_enc) == "20208000900040041234"
    assert b"20208000900040041234" not in row.account_number_enc
