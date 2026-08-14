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
    from app.domains.companies.models import Company  # noqa: PLC0415

    company = Company(jurisdiction="UZ", tax_id="123456789", status=status)
    company.id = company_id
    return company


@pytest.mark.parametrize("frm_name", _STATUS_NAMES)
@pytest.mark.parametrize("to_name", _STATUS_NAMES)
def test_transition_matrix(frm_name: str, to_name: str) -> None:
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

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
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = UserAccount(phone="+998901234567")
    account.id = 1
    company = company_service.create_company(MagicMock(), account, "uz", tax_id)
    assert company.jurisdiction == "UZ"
    assert company.tax_id == "123456789"
    assert company.status == CompanyStatus.draft


@pytest.mark.parametrize("tax_id", ["12345", "1234567890", "abcdefghi", ""])
def test_create_company_rejects_bad_uz_tax_id(tax_id: str) -> None:
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415

    account = UserAccount(phone="+998901234567")
    account.id = 1
    with pytest.raises(company_service.InvalidTaxId):
        company_service.create_company(MagicMock(), account, "UZ", tax_id)


@pytest.mark.parametrize(
    "tax_id",
    [
        "١٢٣٤٥٦٧٨٩",  # Arabic-Indic digits
        "¹²³⁴⁵⁶⁷⁸⁹",  # superscript digits
        "１２３４５６７８９",  # fullwidth digits
        "12345678٩",  # ASCII + one Arabic-Indic digit
    ],
)
def test_create_company_rejects_non_ascii_digit_tax_id(tax_id: str) -> None:
    """`str.isdigit()` is True for these, so they used to register successfully.

    That is not cosmetic: `uq_company_jurisdiction_tax_id` compares bytes, so the
    homoglyph forms bypassed the duplicate guard and one legal entity could hold
    several company rows (and would never match its E-IMZO certificate INN).
    """
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415

    assert tax_id.isdigit() and len(tax_id) == 9, "fixture must defeat the old check"
    account = UserAccount(phone="+998901234567")
    account.id = 1
    with pytest.raises(company_service.InvalidTaxId):
        company_service.create_company(MagicMock(), account, "UZ", tax_id)


# NB: "" is absent on purpose — it defaults to "UZ" (see normalize_new_company).
@pytest.mark.parametrize("jurisdiction", ["other", "OTHER", "U", "USA", "12", "U1", "уз"])
def test_create_company_rejects_non_two_letter_jurisdiction(jurisdiction: str) -> None:
    """`companies.jurisdiction` is varchar(2); "other" reached PG and became a 500.

    The step-2 «Страна регистрации» select shipped an `other` option, so a
    first-class UI choice crashed the endpoint with StringDataRightTruncation.
    """
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415

    account = UserAccount(phone="+998901234567")
    account.id = 1
    with pytest.raises(company_service.InvalidJurisdiction):
        company_service.create_company(MagicMock(), account, jurisdiction, "123456789")


def test_normalize_new_company_is_db_free_and_normalizes() -> None:
    """The endpoint validates through this BEFORE spending the daily quota."""
    from app.domains.companies import service as company_service  # noqa: PLC0415

    assert company_service.normalize_new_company(" uz ", " 123456789 ") == ("UZ", "123456789")
    # An empty jurisdiction still defaults to UZ (unchanged behaviour).
    assert company_service.normalize_new_company("", "123456789") == ("UZ", "123456789")


def test_create_company_makes_creator_an_owner_member() -> None:
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.companies.models import CompanyMember  # noqa: PLC0415
    from app.models.accounts import UserAccount  # noqa: PLC0415
    from app.models.enums import CompanyMemberRole  # noqa: PLC0415

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
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    with pytest.raises(company_service.InvalidBankMfo):
        company_service.add_bank_account(
            MagicMock(), _company(CompanyStatus.draft), mfo, "12345678901234567890"
        )


def test_add_bank_account_encrypts_number_and_keeps_last4() -> None:
    from app.core.crypto import decrypt_pii  # noqa: PLC0415
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    row = company_service.add_bank_account(
        MagicMock(), _company(CompanyStatus.draft), "00014", "2020 8000 9000 4004 1234"
    )
    assert row.account_last4 == "1234"
    assert row.bank_mfo == "00014"
    # The clear number never persists — only the ciphertext, which round-trips.
    assert isinstance(row.account_number_enc, bytes)
    assert decrypt_pii(row.account_number_enc) == "20208000900040041234"
    assert b"20208000900040041234" not in row.account_number_enc


def test_update_profile_persists_registration_date() -> None:
    """«Дата регистрации компании» is a field the registration wizard collects.

    The `companies.registration_date` column has existed since 0017 but was not in
    `_EDITABLE_FIELDS`, so a PATCH carrying it was silently dropped — the client
    filled the field in and nothing was stored.
    """
    import datetime  # noqa: PLC0415

    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    company = _company(CompanyStatus.draft)
    company_service.update_profile(
        MagicMock(), company, MagicMock(), registration_date=datetime.date(2020, 3, 12)
    )
    assert company.registration_date == datetime.date(2020, 3, 12)


def test_profile_update_schema_accepts_registration_date() -> None:
    import datetime  # noqa: PLC0415

    from app.domains.companies.schemas import (  # noqa: PLC0415
        CompanyDetailOut,
        CompanyProfileUpdateIn,
    )

    parsed = CompanyProfileUpdateIn(registration_date="2020-03-12")  # type: ignore[arg-type]
    assert parsed.registration_date == datetime.date(2020, 3, 12)
    assert "registration_date" in CompanyDetailOut.model_fields


# ── profile schema hardening (the API used to trust the wizard) ────────────────


def test_profile_update_schema_caps_string_lengths() -> None:
    """These columns are unbounded `text`; a 100 000-char name used to be a 200."""
    import pydantic  # noqa: PLC0415

    from app.domains.companies.schemas import CompanyProfileUpdateIn  # noqa: PLC0415

    with pytest.raises(pydantic.ValidationError):
        CompanyProfileUpdateIn(legal_name="A" * 100_000)


@pytest.mark.parametrize("blank", ["   ", "\t", "\n ", ""])
def test_profile_update_schema_treats_blank_as_absent(blank: str) -> None:
    """A whitespace-only legal name used to be stored verbatim."""
    from app.domains.companies.schemas import CompanyProfileUpdateIn  # noqa: PLC0415

    assert CompanyProfileUpdateIn(legal_name=blank).legal_name is None


def test_profile_update_schema_trims_surrounding_whitespace() -> None:
    from app.domains.companies.schemas import CompanyProfileUpdateIn  # noqa: PLC0415

    assert CompanyProfileUpdateIn(legal_name="  ООО «Тест»  ").legal_name == "ООО «Тест»"


def test_profile_update_schema_rejects_future_registration_date() -> None:
    """2099-12-31 and 9999-12-31 were both accepted and stored."""
    import datetime  # noqa: PLC0415

    import pydantic  # noqa: PLC0415

    from app.domains.companies.schemas import CompanyProfileUpdateIn  # noqa: PLC0415

    tomorrow = datetime.datetime.now(datetime.UTC).date() + datetime.timedelta(days=1)
    for bad in (tomorrow, datetime.date(2099, 12, 31), datetime.date(9999, 12, 31)):
        with pytest.raises(pydantic.ValidationError):
            CompanyProfileUpdateIn(registration_date=bad)
    # Today is still fine (a company registered this morning).
    today = datetime.datetime.now(datetime.UTC).date()
    assert CompanyProfileUpdateIn(registration_date=today).registration_date == today


# ── profile editability while a case is undecided (E-IMZO flow) ────────────────


@pytest.mark.parametrize(
    ("case_status_name", "editable"),
    [
        ("checks_running", True),
        ("pending_review", True),
        ("needs_info", True),
        ("approved", False),
        ("rejected", False),
    ],
)
def test_profile_editable_while_case_undecided(case_status_name: str, editable: bool) -> None:
    """A signed company leaves `draft` on wizard step 1, before it is asked for an address.

    `eimzo_service.verify` treats the signature as the first-time submit, so the
    company is already `pending_verification` / `pending_review` when step 5 PATCHes
    the profile. Excluding those states made every E-IMZO registration fail with
    409 `Profile not editable now`, silently dropping the legal address,
    registration date and ownership form the user had entered.
    """
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus, VerificationCaseStatus  # noqa: PLC0415

    company = _company(CompanyStatus.pending_verification)
    case_status = VerificationCaseStatus[case_status_name]

    db = MagicMock()
    # `_assert_profile_editable` looks for a case in an undecided status.
    found = MagicMock() if case_status in company_service._UNDECIDED_CASE_STATUSES else None
    db.query.return_value.filter.return_value.first.return_value = found

    if editable:
        company_service.update_profile(db, company, MagicMock(), legal_address="г. Ташкент")
        assert company.legal_address == "г. Ташкент"
    else:
        with pytest.raises(company_service.ProfileNotEditable):
            company_service.update_profile(db, company, MagicMock(), legal_address="г. Ташкент")
