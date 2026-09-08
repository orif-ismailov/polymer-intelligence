"""`accounts.service` — the properties the router's answers rest on.

`test_portal_auth_api.py` proves the endpoint says one thing for every kind of failure.
This file proves the layer underneath EARNS that: it does the same work on every miss,
so the answer is uniform in time as well as in text, and it never returns an account
that is not allowed to act.

The timing property is asserted structurally rather than by measuring a clock — a wall
-clock assertion on argon2 is exactly the flaky test that gets deleted in six months.
What is checked instead is that `dummy_verify` is CALLED on both miss paths, which is
the thing that would actually be dropped by a well-meaning refactor.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.security import hash_password, verify_password
from app.domains.accounts import service as account_service
from app.domains.accounts.models import UserAccount
from app.models.enums import AccountStatus

_PASS = "correct horse battery"


def _db_returning(account: UserAccount | None) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = account
    return db


def _account(
    *,
    status: AccountStatus = AccountStatus.active,
    password: str | None = _PASS,
    login: str = "acme-trade",
) -> UserAccount:
    return UserAccount(
        phone="+998901234567",
        login=login,
        password_hash=hash_password(password) if password is not None else None,
        status=status,
    )


# ── normalize_login ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("acme", "acme"), ("  ACME  ", "acme"), ("Acme-Trade", "acme-trade")],
)
def test_normalize_login_folds_case_and_space(raw: str, expected: str) -> None:
    assert account_service.normalize_login(raw) == expected


# ── authenticate ──────────────────────────────────────────────────────────────


def test_authenticate_returns_the_account_and_stamps_last_login() -> None:
    account = _account()
    result = account_service.authenticate(_db_returning(account), "acme-trade", _PASS)
    assert result is account
    assert account.last_login_at is not None


def test_authenticate_rejects_a_wrong_password() -> None:
    account = _account()
    assert account_service.authenticate(_db_returning(account), "acme-trade", "nope") is None


@pytest.mark.parametrize("status", [AccountStatus.blocked, AccountStatus.pending])
def test_authenticate_refuses_an_account_that_may_not_act(status: AccountStatus) -> None:
    """A correct password is not enough — and the caller cannot tell the difference."""
    account = _account(status=status)
    assert account_service.authenticate(_db_returning(account), "acme-trade", _PASS) is None
    assert account.last_login_at is None


def test_authenticate_does_real_kdf_work_for_an_unknown_login() -> None:
    with patch.object(account_service, "dummy_verify") as dummy:
        assert account_service.authenticate(_db_returning(None), "nobody", _PASS) is None
    dummy.assert_called_once_with(_PASS)


def test_authenticate_does_real_kdf_work_for_an_account_without_credentials() -> None:
    """The path a live APPLICATION takes, and the one most likely to be dropped.

    An account with `password_hash IS NULL` has nothing to compare against, so the
    obvious implementation returns early — and then answers measurably faster than a
    real password check, which enumerates every login staff has issued.
    """
    account = _account(password=None, status=AccountStatus.pending)
    with patch.object(account_service, "dummy_verify") as dummy:
        assert (
            account_service.authenticate(_db_returning(account), "acme-trade", _PASS) is None
        )
    dummy.assert_called_once_with(_PASS)


def test_authenticate_looks_up_the_folded_login() -> None:
    """`Acme-Trade` must reach the row stored as `acme-trade`."""
    account = _account()
    db = _db_returning(account)
    assert account_service.authenticate(db, "  Acme-Trade  ", _PASS) is account


# ── register ──────────────────────────────────────────────────────────────────


def test_register_creates_an_application_that_cannot_sign_in() -> None:
    db = MagicMock()
    account = account_service.register(
        db, phone="901234567", contact_name="Иван", company_name="ООО Полимер", note=" hi "
    )
    assert account.status == AccountStatus.pending
    assert account.login is None
    assert account.password_hash is None
    assert account.phone == "+998901234567"  # bare UZ national → E.164
    assert account.applied_company_name == "ООО Полимер"
    assert account.application_note == "hi"
    db.add.assert_called_once_with(account)


def test_register_refuses_an_unparseable_phone() -> None:
    with pytest.raises(account_service.InvalidPhone):
        account_service.register(
            MagicMock(), phone="12", contact_name="И", company_name="X"
        )


def test_register_leaves_blank_optional_fields_as_none() -> None:
    account = account_service.register(
        MagicMock(), phone="+998901234567", contact_name="Иван", company_name="X", note="   "
    )
    assert account.application_note is None


# ── change_password ───────────────────────────────────────────────────────────


def test_change_password_replaces_the_hash_and_clears_the_debt() -> None:
    account = _account()
    account.must_change_password = True

    account_service.change_password(MagicMock(), account, current=_PASS, new="a-new-secret-12")

    assert verify_password("a-new-secret-12", account.password_hash)
    assert account.must_change_password is False
    assert account.password_set_at is not None


def test_change_password_requires_the_current_one() -> None:
    """A borrowed screen must not become a stolen account."""
    account = _account()
    account.must_change_password = True

    with pytest.raises(account_service.WrongPassword):
        account_service.change_password(
            MagicMock(), account, current="not it", new="a-new-secret-12"
        )
    assert account.must_change_password is True
    assert verify_password(_PASS, account.password_hash)


def test_change_password_refuses_an_account_with_no_stored_hash() -> None:
    """Unreachable through the router (it could not have signed in) — checked anyway,
    because `verify_password(x, None)` is a TypeError rather than a refusal."""
    account = _account(password=None)
    with pytest.raises(account_service.WrongPassword):
        account_service.change_password(MagicMock(), account, current="x", new="a-new-secret-12")
