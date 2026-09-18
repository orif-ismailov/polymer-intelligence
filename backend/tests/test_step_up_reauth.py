"""Step-up re-authentication for sensitive actions (IMEX-1).

Of the five sensitive actions the ticket names, payout details are the one that both
exists and was unprotected: a valid access token was enough to add or archive a
company bank account. Password change already re-authenticates through its
`current_password` field, and email/phone have no self-service endpoint to guard.

What is asserted here is the distinction the guard exists to make — a live session
that has not re-authenticated is asked for a password (403 with a code the cabinet
routes on), a dead one is sent to sign in (401), and an unreachable session store
refuses the action without destroying the session (503).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
import redis
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis

_BANK = "/api/v1/portal/companies/1/bank-accounts"
_STEP_UP = "/api/v1/portal/auth/step-up"
_PASS = "correct horse battery"


@pytest.fixture
def portal_app() -> Iterator[tuple[TestClient, FakeRedis, MagicMock]]:
    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    app = create_app()
    fake = FakeRedis()
    db = MagicMock()

    def _override_db() -> Iterator[MagicMock]:
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = lambda: fake

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, fake, db


def _account(account_id: int = 7):  # noqa: ANN202
    from app.core.security import hash_password  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    account = MagicMock()
    account.id = account_id
    account.status = AccountStatus.active
    account.must_change_password = False
    account.password_hash = hash_password(_PASS)
    account.name = "Tester"
    account.language = "ru"
    return account


def _found(db: MagicMock, row: object) -> None:
    db.query.return_value.filter.return_value.first.return_value = row


def _signed_in(fake: FakeRedis, account_id: int = 7, *, fresh: bool = False) -> tuple[str, str]:
    """Start a session and return (access token, family id).

    Sign-in stamps the step-up window, so `fresh=False` (the default) ages that
    stamp out — the state a session spends nearly all of its life in, and the only
    one in which the guard has anything to do.
    """
    import json  # noqa: PLC0415

    from app.core.security import (  # noqa: PLC0415
        create_portal_access_token,
        new_family_id,
        new_jti,
    )
    from app.services import session_service  # noqa: PLC0415

    fam = new_family_id()
    session_service.start(
        fake,
        kind=session_service.KIND_PORTAL,
        subject_id=account_id,
        fam=fam,
        jti=new_jti(),
        abs_exp=int(time.time()) + 90 * 86400,
    )
    if not fresh:
        record = json.loads(fake.store[f"rs:{fam}"])
        record["step_up_at"] = int(time.time()) - 3600
        fake.store[f"rs:{fam}"] = json.dumps(record)
    return create_portal_access_token(subject=str(account_id), fam=fam), fam


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── the guard ─────────────────────────────────────────────────────────────────


def test_adding_a_bank_account_without_a_step_up_is_refused(portal_app) -> None:  # noqa: ANN001
    client, fake, db = portal_app
    _found(db, _account())
    token, _ = _signed_in(fake)

    resp = client.post(
        _BANK,
        headers=_bearer(token),
        json={"bank_mfo": "00014", "account_number": "20208000000000000001"},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "step_up_required"


def test_archiving_a_bank_account_without_a_step_up_is_refused(portal_app) -> None:  # noqa: ANN001
    """Removing a payout account is as sensitive as adding one — an attacker who can
    only delete still redirects nothing, but leaves the seller unpayable."""
    client, fake, db = portal_app
    _found(db, _account())
    token, _ = _signed_in(fake)

    resp = client.delete(f"{_BANK}/5", headers=_bearer(token))

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "step_up_required"


def test_a_token_with_no_session_binding_cannot_reach_a_sensitive_action(portal_app) -> None:  # noqa: ANN001
    """`fam` is optional on access tokens, so this is the case that decides whether
    that was safe: no family claim must mean refused, never assumed-fine."""
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    client, _fake, db = portal_app
    _found(db, _account())
    unbound = create_portal_access_token(subject="7")  # no fam

    resp = client.post(
        _BANK,
        headers=_bearer(unbound),
        json={"bank_mfo": "00014", "account_number": "20208000000000000001"},
    )

    assert resp.status_code == 401


def test_a_revoked_session_is_sent_to_sign_in_not_to_the_password_prompt(portal_app) -> None:  # noqa: ANN001
    """403 would ask for a password that cannot possibly help."""
    from app.services import session_service  # noqa: PLC0415

    client, fake, db = portal_app
    _found(db, _account())
    token, fam = _signed_in(fake)
    session_service.revoke(fake, fam)

    resp = client.delete(f"{_BANK}/5", headers=_bearer(token))

    assert resp.status_code == 401


def test_an_unreachable_session_store_refuses_without_destroying_the_session(portal_app) -> None:  # noqa: ANN001
    client, fake, db = portal_app
    _found(db, _account())
    token, _ = _signed_in(fake)

    with patch.object(
        FakeRedis, "get", side_effect=redis.ConnectionError("connection refused")
    ):
        resp = client.delete(f"{_BANK}/5", headers=_bearer(token))

    assert resp.status_code == 503


# ── opening the window ────────────────────────────────────────────────────────


def test_step_up_with_the_right_password_unlocks_the_action(portal_app) -> None:  # noqa: ANN001
    client, fake, db = portal_app
    _found(db, _account())
    token, _ = _signed_in(fake)

    opened = client.post(_STEP_UP, headers=_bearer(token), json={"password": _PASS})
    assert opened.status_code == 200
    assert opened.json()["expires_in"] > 0

    # The first query of the next request authenticates the caller; after that the
    # mock answers "no such row", so the request lands on an honest 404 instead of
    # dying inside the real handler on a MagicMock company. 404 means it got past
    # the guard, which is the whole assertion.
    rows = [_account(), None, None, None]
    db.query.return_value.filter.return_value.first.side_effect = rows

    resp = client.delete(f"{_BANK}/5", headers=_bearer(token))
    assert resp.status_code == 404


def test_step_up_with_the_wrong_password_does_not_unlock(portal_app) -> None:  # noqa: ANN001
    client, fake, db = portal_app
    _found(db, _account())
    token, _ = _signed_in(fake)

    refused = client.post(_STEP_UP, headers=_bearer(token), json={"password": "nope"})
    assert refused.status_code == 401

    resp = client.delete(f"{_BANK}/5", headers=_bearer(token))
    assert resp.status_code == 403


def test_the_step_up_window_expires(portal_app) -> None:  # noqa: ANN001
    import json  # noqa: PLC0415

    client, fake, db = portal_app
    _found(db, _account())
    token, fam = _signed_in(fake)
    client.post(_STEP_UP, headers=_bearer(token), json={"password": _PASS})

    record = json.loads(fake.store[f"rs:{fam}"])
    record["step_up_at"] = int(time.time()) - 3600
    fake.store[f"rs:{fam}"] = json.dumps(record)

    resp = client.delete(f"{_BANK}/5", headers=_bearer(token))
    assert resp.status_code == 403


def test_a_just_signed_in_user_is_not_asked_again(portal_app) -> None:  # noqa: ANN001
    """The registration wizard adds a bank account minutes after the first sign-in
    (`features/company-wizard/model/useSubmitWizard.ts`). Gating that on a second
    password entry would interrupt registration to ask for the password the user
    had just typed — so sign-in stamps the window and this asserts it stays stamped.
    """
    client, fake, db = portal_app
    _found(db, _account())
    token, _ = _signed_in(fake, fresh=True)

    rows = [_account(), None, None, None]
    db.query.return_value.filter.return_value.first.side_effect = rows

    resp = client.delete(f"{_BANK}/5", headers=_bearer(token))
    assert resp.status_code == 404  # past the guard


def test_step_up_needs_a_session_bound_token(portal_app) -> None:  # noqa: ANN001
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    client, _fake, db = portal_app
    _found(db, _account())

    resp = client.post(
        _STEP_UP,
        headers=_bearer(create_portal_access_token(subject="7")),
        json={"password": _PASS},
    )

    assert resp.status_code == 401
