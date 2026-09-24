"""Cabinet auth API tests — login + password, registration, forced change (0048).

TestClient with `get_db` (mock session) + `get_redis` (FakeRedis) overridden. The
service's own logic is unit-tested in `test_portal_account_service.py`; what this file
covers is the router's contract: what a caller can observe.

Three of those observations are the whole point of the design and are asserted here
rather than left to review:

* **Sign-in says one thing.** Unknown login, wrong password, blocked account and an
  application that was never granted credentials all produce the identical 401 body.
* **Registration says one thing.** The same 202 whether or not that phone has applied
  before — the enumeration oracle the dropped UNIQUE constraint removed at the schema
  level must not come back through the response.
* **The forced-change gate is real.** An account that owes a password change is refused
  by `get_current_account` (so ~140 routes are closed to it) and can still reach exactly
  the two routes that let it settle the debt.

Plus the properties inherited from the OTP era that must survive the swap: JWT audience
isolation in both directions, blocked → 403, and refresh rotating the cookie.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis

_LOGIN = "/api/v1/portal/auth/login"
_REGISTER = "/api/v1/portal/auth/register"
_PASSWORD = "/api/v1/portal/auth/password"
_REFRESH = "/api/v1/portal/auth/refresh"
_LOGOUT = "/api/v1/portal/auth/logout"
_ME = "/api/v1/portal/me"
_PHONE = "+998901234567"
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

    def _override_redis() -> Iterator[FakeRedis]:
        yield fake

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, fake, db


def _account(  # noqa: ANN202
    account_id: int,
    status: str = "active",
    *,
    login: str = "acme-trade",
    password: str | None = _PASS,
    must_change: bool = False,
):
    """A cabinet account as staff would have issued it.

    The password is hashed for real — `authenticate` compares against argon2, and a
    canned hash would make every sign-in test pass for the wrong reason.
    """
    from app.core.security import hash_password  # noqa: PLC0415
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    acct = UserAccount(
        phone=_PHONE,
        language="ru",
        status=AccountStatus(status),
        login=login,
        password_hash=hash_password(password) if password is not None else None,
        must_change_password=must_change,
    )
    acct.id = account_id
    return acct


def _found(db: MagicMock, account) -> None:  # noqa: ANN001
    db.query.return_value.filter.return_value.first.return_value = account


# ── Sign-in ───────────────────────────────────────────────────────────────────


def test_login_success_issues_token_and_cookie(portal_app) -> None:  # noqa: ANN001
    from app.core.security import decode_token  # noqa: PLC0415

    client, _fake, db = portal_app
    _found(db, _account(7))

    resp = client.post(_LOGIN, json={"login": "acme-trade", "password": _PASS})
    assert resp.status_code == 200

    body = resp.json()
    payload = decode_token(body["access_token"], expected_type="portal_access")
    assert payload["sub"] == "7"
    assert body["account"]["login"] == "acme-trade"
    assert body["account"]["must_change_password"] is False
    assert "portal_session=" in resp.headers.get("set-cookie", "")


def test_login_is_case_insensitive_in_the_login(portal_app) -> None:  # noqa: ANN001
    """`Acme-Trade` reaches the account stored as `acme-trade`.

    The unique index is on `lower(login)`, so a case-sensitive lookup would create
    accounts that exist and cannot be signed into — which is what `staff_users.email`
    paid for once already.
    """
    client, _fake, db = portal_app
    _found(db, _account(7))

    resp = client.post(_LOGIN, json={"login": "  Acme-Trade  ", "password": _PASS})
    assert resp.status_code == 200


@pytest.mark.parametrize(
    ("case", "account", "password"),
    [
        ("unknown login", None, _PASS),
        ("wrong password", "active", "not the password"),
        ("blocked account", "blocked", _PASS),
        ("application, no credentials", "pending", _PASS),
    ],
)
def test_login_failures_are_indistinguishable(portal_app, case, account, password) -> None:  # noqa: ANN001
    """Every way to fail produces the SAME 401 body.

    Splitting them — 403 for blocked, 404 for unknown — would tell a caller which
    logins exist and which accounts are merely disabled, which is most of what an
    attacker came for.
    """
    client, _fake, db = portal_app
    if account is None:
        _found(db, None)
    elif account == "pending":
        _found(db, _account(7, "pending", password=None))
    else:
        _found(db, _account(7, account))

    resp = client.post(_LOGIN, json={"login": "acme-trade", "password": password})
    assert resp.status_code == 401, case
    assert resp.json() == {"detail": "Invalid credentials"}, case


def test_login_is_rate_limited_per_ip_with_retry_after(portal_app) -> None:  # noqa: ANN001
    client, _fake, db = portal_app
    _found(db, None)

    from app.services.rate_limit import PORTAL_LOGIN_PER_IP_PER_MIN  # noqa: PLC0415

    # Each attempt names a DIFFERENT login, so only the per-IP bucket can stop it.
    for i in range(PORTAL_LOGIN_PER_IP_PER_MIN):
        resp = client.post(_LOGIN, json={"login": f"who-{i}", "password": "x"})
        assert resp.status_code == 401

    resp = client.post(_LOGIN, json={"login": "who-last", "password": "x"})
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0


def test_login_per_account_bucket_is_keyed_by_the_normalized_login(portal_app) -> None:  # noqa: ANN001
    """Varying only the CASE must not buy more attempts."""
    client, _fake, db = portal_app
    _found(db, _account(7))

    from app.services.rate_limit import PORTAL_LOGIN_PER_ACCOUNT_PER_5MIN  # noqa: PLC0415

    for _ in range(PORTAL_LOGIN_PER_ACCOUNT_PER_5MIN):
        client.post(_LOGIN, json={"login": "ACME-trade", "password": "wrong"})

    resp = client.post(_LOGIN, json={"login": "acme-trade", "password": _PASS})
    assert resp.status_code == 429


# ── Registration ──────────────────────────────────────────────────────────────


_APPLICATION = {
    "contact_name": "Иван Петров",
    "phone": _PHONE,
    "company_name": "ООО Полимер",
    "note": "Хотим закупать ПВХ",
}


def test_register_accepts_and_grants_nothing(portal_app) -> None:  # noqa: ANN001
    client, _fake, db = portal_app

    resp = client.post(_REGISTER, json=_APPLICATION)
    assert resp.status_code == 202
    assert resp.json() == {"status": "received"}
    # No session, no token, nothing a caller could act with.
    assert "portal_session=" not in resp.headers.get("set-cookie", "")
    assert "access_token" not in resp.text
    assert db.commit.called


def test_register_creates_a_pending_account(portal_app) -> None:  # noqa: ANN001
    from app.models.enums import AccountStatus  # noqa: PLC0415

    client, _fake, db = portal_app
    client.post(_REGISTER, json=_APPLICATION)

    added = [c.args[0] for c in db.add.call_args_list]
    accounts = [a for a in added if type(a).__name__ == "UserAccount"]
    assert len(accounts) == 1
    assert accounts[0].status == AccountStatus.pending
    assert accounts[0].password_hash is None
    assert accounts[0].login is None
    assert accounts[0].applied_company_name == "ООО Полимер"


def test_register_answers_identically_for_a_repeat_phone(portal_app) -> None:  # noqa: ANN001
    """Byte-identical answers, so the response cannot enumerate applicants.

    The schema half of this property is the dropped UNIQUE on `phone` (0048): with it
    in place the database would raise on the second call and the endpoint would 500,
    which is itself the answer an attacker wanted.
    """
    client, _fake, _db = portal_app

    first = client.post(_REGISTER, json=_APPLICATION)
    second = client.post(_REGISTER, json=_APPLICATION)
    assert (first.status_code, first.json()) == (second.status_code, second.json())


def test_register_rejects_an_unparseable_phone(portal_app) -> None:  # noqa: ANN001
    """The one thing this route may vary on: a form error the applicant can fix."""
    client, _fake, _db = portal_app
    resp = client.post(_REGISTER, json={**_APPLICATION, "phone": "12"})
    assert resp.status_code == 422


def test_register_is_rate_limited_per_ip(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app

    from app.services.rate_limit import PORTAL_REGISTER_PER_IP_PER_HOUR  # noqa: PLC0415

    for _ in range(PORTAL_REGISTER_PER_IP_PER_HOUR):
        assert client.post(_REGISTER, json=_APPLICATION).status_code == 202

    resp = client.post(_REGISTER, json=_APPLICATION)
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0


def test_forged_x_forwarded_for_cannot_escape_the_per_ip_cap(portal_app) -> None:  # noqa: ANN001
    """Rotating X-Forwarded-For must not mint a fresh bucket.

    `_client_ip` reads X-Real-IP only. nginx builds XFF by APPENDING to whatever the
    client sent, so its first entry is attacker-controlled; keying on it made the cap
    decorative. Guarded here because the symptom of a regression is silence.
    """
    client, _fake, _db = portal_app

    from app.services.rate_limit import PORTAL_REGISTER_PER_IP_PER_HOUR  # noqa: PLC0415

    for i in range(PORTAL_REGISTER_PER_IP_PER_HOUR):
        resp = client.post(
            _REGISTER, json=_APPLICATION, headers={"X-Forwarded-For": f"10.0.0.{i}"}
        )
        assert resp.status_code == 202

    resp = client.post(
        _REGISTER, json=_APPLICATION, headers={"X-Forwarded-For": "10.0.0.250"}
    )
    assert resp.status_code == 429


def test_x_real_ip_keys_the_per_ip_bucket(portal_app) -> None:  # noqa: ANN001
    """Two different X-Real-IP values get two different buckets."""
    client, _fake, _db = portal_app

    from app.services.rate_limit import PORTAL_REGISTER_PER_IP_PER_HOUR  # noqa: PLC0415

    for _ in range(PORTAL_REGISTER_PER_IP_PER_HOUR):
        client.post(_REGISTER, json=_APPLICATION, headers={"X-Real-IP": "203.0.113.1"})

    assert (
        client.post(
            _REGISTER, json=_APPLICATION, headers={"X-Real-IP": "203.0.113.1"}
        ).status_code
        == 429
    )
    assert (
        client.post(
            _REGISTER, json=_APPLICATION, headers={"X-Real-IP": "203.0.113.2"}
        ).status_code
        == 202
    )


# ── The forced-change gate ────────────────────────────────────────────────────


def _bearer(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


def test_an_account_owing_a_password_change_is_refused_by_guarded_routes(portal_app) -> None:  # noqa: ANN001
    """403 with a machine-readable code, from the guard rather than the route.

    `PATCH /portal/me` stands in for the ~140 routes behind `get_current_account`: the
    gate lives in the dependency precisely so none of them has to remember it.
    """
    client, _fake, db = portal_app
    _found(db, _account(7, must_change=True))

    resp = client.patch(_ME, json={"name": "Иван"}, headers=_bearer(7))
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "password_change_required"


def test_an_account_owing_a_password_change_can_still_read_me(portal_app) -> None:  # noqa: ANN001
    """After a hard reload this is the only way the client learns it owes one."""
    client, _fake, db = portal_app
    _found(db, _account(7, must_change=True))

    resp = client.get(_ME, headers=_bearer(7))
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is True


def test_changing_the_password_clears_the_debt_and_rotates_the_cookie(portal_app) -> None:  # noqa: ANN001
    from app.core.security import verify_password  # noqa: PLC0415

    client, _fake, db = portal_app
    account = _account(7, must_change=True)
    _found(db, account)

    resp = client.post(
        _PASSWORD,
        json={"current_password": _PASS, "new_password": "a-longer-new-secret"},
        headers=_bearer(7),
    )
    assert resp.status_code == 200
    assert account.must_change_password is False
    assert verify_password("a-longer-new-secret", account.password_hash)
    assert account.password_set_at is not None
    assert "portal_session=" in resp.headers.get("set-cookie", "")
    assert resp.json()["account"]["must_change_password"] is False


def test_changing_the_password_requires_the_current_one(portal_app) -> None:  # noqa: ANN001
    client, _fake, db = portal_app
    account = _account(7, must_change=True)
    _found(db, account)

    resp = client.post(
        _PASSWORD,
        json={"current_password": "not it", "new_password": "a-longer-new-secret"},
        headers=_bearer(7),
    )
    assert resp.status_code == 400
    assert account.must_change_password is True


def test_a_short_new_password_is_refused(portal_app) -> None:  # noqa: ANN001
    client, _fake, db = portal_app
    _found(db, _account(7, must_change=True))

    resp = client.post(
        _PASSWORD,
        json={"current_password": _PASS, "new_password": "short"},
        headers=_bearer(7),
    )
    assert resp.status_code == 422


def test_an_ordinary_account_is_unaffected_by_the_gate(portal_app) -> None:  # noqa: ANN001
    """The payoff of putting the gate in the guard: nothing else had to change.

    `must_change_password` defaults false, so every account that never owed a change —
    including the ones the rest of the suite mints straight from
    `create_portal_access_token` — reaches guarded routes exactly as before.
    """
    client, _fake, db = portal_app
    _found(db, _account(7))

    assert client.patch(_ME, json={"name": "Иван"}, headers=_bearer(7)).status_code == 200


# ── get_current_account: audience isolation + blocked ─────────────────────────


def test_me_requires_auth(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    assert client.get(_ME).status_code == 401


def test_staff_token_rejected_by_portal_me(portal_app) -> None:  # noqa: ANN001
    from app.core.security import create_access_token  # noqa: PLC0415

    client, _fake, _db = portal_app
    staff = create_access_token(subject="1")
    resp = client.get(_ME, headers={"Authorization": f"Bearer {staff}"})
    assert resp.status_code == 401


def test_client_session_token_rejected_by_portal_me(portal_app) -> None:  # noqa: ANN001
    from app.core.security import create_client_session_token  # noqa: PLC0415

    client, _fake, _db = portal_app
    cs = create_client_session_token(subject="123456")
    resp = client.get(_ME, headers={"Authorization": f"Bearer {cs}"})
    assert resp.status_code == 401


def test_portal_token_rejected_by_staff_endpoint(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    resp = client.get("/api/v1/admin/users", headers=_bearer(7))
    assert resp.status_code == 401


def test_me_success_with_portal_token(portal_app) -> None:  # noqa: ANN001
    client, _fake, db = portal_app
    _found(db, _account(7))
    resp = client.get(_ME, headers=_bearer(7))
    assert resp.status_code == 200
    assert resp.json()["id"] == 7


def test_me_blocked_account_returns_403(portal_app) -> None:  # noqa: ANN001
    client, _fake, db = portal_app
    _found(db, _account(7, status="blocked"))
    resp = client.get(_ME, headers=_bearer(7))
    assert resp.status_code == 403


def test_me_pending_account_returns_403(portal_app) -> None:  # noqa: ANN001
    """An application cannot act, even if it somehow holds a token."""
    client, _fake, db = portal_app
    _found(db, _account(7, status="pending", password=None))
    resp = client.get(_ME, headers=_bearer(7))
    assert resp.status_code == 403


def test_me_unknown_account_returns_401(portal_app) -> None:  # noqa: ANN001
    client, _fake, db = portal_app
    _found(db, None)
    resp = client.get(_ME, headers=_bearer(999))
    assert resp.status_code == 401


# ── refresh + logout ──────────────────────────────────────────────────────────


def _live_session(fake, account_id: int = 7, *, days: int = 90) -> str:  # noqa: ANN001
    """Record a refresh-token family in Redis and return its cookie value.

    A refresh JWT on its own is no longer enough to refresh with — the family has to
    exist — so tests that want a signed-in cabinet must set up both halves, exactly
    as `POST /auth/login` does.
    """
    import time  # noqa: PLC0415

    from app.core.security import (  # noqa: PLC0415
        create_portal_refresh_token,
        new_family_id,
        new_jti,
    )
    from app.services import session_service  # noqa: PLC0415

    fam, jti = new_family_id(), new_jti()
    abs_exp = int(time.time()) + days * 86400
    session_service.start(
        fake,
        kind=session_service.KIND_PORTAL,
        subject_id=account_id,
        fam=fam,
        jti=jti,
        abs_exp=abs_exp,
    )
    return create_portal_refresh_token(
        subject=str(account_id), fam=fam, jti=jti, abs_exp=abs_exp
    )


def _cookie_from(resp) -> str | None:  # noqa: ANN001
    match = re.search(r"portal_session=([^;]+)", resp.headers.get("set-cookie", ""))
    return match.group(1) if match else None


def test_refresh_rotates_cookie_and_returns_new_access_token(portal_app) -> None:  # noqa: ANN001
    client, fake, db = portal_app
    _found(db, _account(7))
    old_refresh = _live_session(fake)

    resp = client.post(_REFRESH, headers={"Cookie": f"portal_session={old_refresh}"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]
    assert _cookie_from(resp) not in (None, old_refresh)  # rotated


def test_the_previous_refresh_token_stops_working(portal_app) -> None:  # noqa: ANN001
    """The acceptance criterion a stateless JWT could not meet. Before IMEX-1 the
    old cookie kept working for its full lifetime and "rotation" meant nothing."""
    client, fake, db = portal_app
    _found(db, _account(7))
    old_refresh = _live_session(fake)

    client.post(_REFRESH, headers={"Cookie": f"portal_session={old_refresh}"})
    fake.delete(f"rs:used:{__import__('jose').jwt.get_unverified_claims(old_refresh)['jti']}")

    replay = client.post(_REFRESH, headers={"Cookie": f"portal_session={old_refresh}"})
    assert replay.status_code == 401


def test_replaying_a_spent_token_kills_the_live_session_too(portal_app) -> None:  # noqa: ANN001
    """Reuse means two copies exist and we cannot tell which caller is the thief, so
    both lose. The successor issued moments ago stops working as well."""
    from jose import jwt as jose_jwt  # noqa: PLC0415

    client, fake, db = portal_app
    _found(db, _account(7))
    old_refresh = _live_session(fake)

    first = client.post(_REFRESH, headers={"Cookie": f"portal_session={old_refresh}"})
    successor = _cookie_from(first)
    fake.delete(f"rs:used:{jose_jwt.get_unverified_claims(old_refresh)['jti']}")

    client.post(_REFRESH, headers={"Cookie": f"portal_session={old_refresh}"})  # the theft

    assert successor is not None
    victim = client.post(_REFRESH, headers={"Cookie": f"portal_session={successor}"})
    assert victim.status_code == 401


def test_a_concurrent_second_tab_is_not_treated_as_a_thief(portal_app) -> None:  # noqa: ANN001
    """Two tabs refresh at the same moment; the loser gets the winner's token, not
    a 401. Without the grace window this design signs people out at random."""
    client, fake, db = portal_app
    _found(db, _account(7))
    old_refresh = _live_session(fake)

    first = client.post(_REFRESH, headers={"Cookie": f"portal_session={old_refresh}"})
    second = client.post(_REFRESH, headers={"Cookie": f"portal_session={old_refresh}"})

    assert second.status_code == 200
    assert _cookie_from(second) == _cookie_from(first)


def test_refresh_refuses_a_session_past_its_absolute_cap(portal_app) -> None:  # noqa: ANN001
    """Sliding does not mean immortal: at 90 days the session ends mid-activity."""
    client, fake, db = portal_app
    _found(db, _account(7))
    expired = _live_session(fake, days=0)

    resp = client.post(_REFRESH, headers={"Cookie": f"portal_session={expired}"})
    assert resp.status_code == 401


def test_refresh_works_for_an_account_owing_a_password_change(portal_app) -> None:  # noqa: ANN001
    """Not gated on purpose: refusing here strands a reloaded tab on the very screen
    where the debt is paid, holding an expired access token and no way to mint one."""
    client, fake, db = portal_app
    _found(db, _account(7, must_change=True))

    resp = client.post(
        _REFRESH, headers={"Cookie": f"portal_session={_live_session(fake)}"}
    )
    assert resp.status_code == 200
    assert resp.json()["account"]["must_change_password"] is True


def test_refresh_without_cookie_returns_401(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    assert client.post(_REFRESH).status_code == 401


def test_refresh_rejects_a_staff_refresh_token(portal_app) -> None:  # noqa: ANN001
    import time  # noqa: PLC0415

    from app.core.security import create_refresh_token  # noqa: PLC0415

    client, _fake, _db = portal_app
    staff_refresh = create_refresh_token(
        subject="1", fam="f", jti="j", abs_exp=int(time.time()) + 86400
    )
    resp = client.post(_REFRESH, headers={"Cookie": f"portal_session={staff_refresh}"})
    assert resp.status_code == 401  # type mismatch: 'refresh' != 'portal_refresh'


def test_logout_clears_cookie(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    resp = client.post(_LOGOUT)
    assert resp.status_code == 200
    assert "portal_session=" in resp.headers.get("set-cookie", "")


# ── Technologist applications (0055) ─────────────────────────────────────────


def test_a_technologist_applies_without_a_company(portal_app) -> None:  # noqa: ANN001
    """A private expert has no company to name — the field is not theirs to fill."""
    client, _fake, db = portal_app
    body = {k: v for k, v in _APPLICATION.items() if k != "company_name"}
    resp = client.post(_REGISTER, json={**body, "applied_as": "technologist"})
    assert resp.status_code == 202

    added = [c.args[0] for c in db.add.call_args_list]
    account = next(a for a in added if type(a).__name__ == "UserAccount")
    assert account.applied_as == "technologist"
    assert account.applied_company_name is None


def test_a_company_application_still_needs_the_company_name(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    body = {k: v for k, v in _APPLICATION.items() if k != "company_name"}
    assert client.post(_REGISTER, json=body).status_code == 422


def test_an_unknown_applicant_kind_is_refused(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    resp = client.post(_REGISTER, json={**_APPLICATION, "applied_as": "wizard"})
    assert resp.status_code == 422


def test_the_account_payload_says_who_the_account_is() -> None:
    """The cabinet routes on it: a technologist with no company is not unfinished."""
    from app.domains.accounts.schemas import AccountOut  # noqa: PLC0415

    assert "applied_as" in AccountOut.model_fields
