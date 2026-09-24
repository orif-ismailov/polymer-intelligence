"""`/admin/portal-accounts` — the door credentials come through.

Mirrors `test_admin_users_api.py` in shape, and asserts the two things that make this
surface different from ordinary CRUD:

* **The plaintext password appears exactly once and is never recoverable.** It is in
  the response that created it, and in no read route, no audit row and no log line.
  Every part of that is easy to break by adding a convenience field later, so each
  part has a test.
* **Issuing credentials is an admin act, not a grantable one.** A non-administrator
  staff member is refused even with a page grant, because there is no page to grant.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_BASE = "/api/v1/admin/portal-accounts"


@pytest.fixture
def admin_app() -> Iterator[tuple[TestClient, MagicMock, object]]:
    """TestClient with an ADMIN staff identity and a mock session."""
    from app.api.deps import get_current_staff_user  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    from app.models.staff import StaffUser  # noqa: PLC0415

    actor = StaffUser(email="admin@example.com", full_name="Admin", is_admin=True)
    actor.id = 1

    app = create_app()
    db = MagicMock()

    def _override_db() -> Iterator[MagicMock]:
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_staff_user] = lambda: actor

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, db, actor


def _application(account_id: int = 5):  # noqa: ANN202
    """An application as `service.register` leaves it, AFTER a flush.

    `must_change_password` and `created_at` are set by hand because column defaults
    are applied at INSERT, and nothing here ever reaches a database — an in-memory
    instance carries `None` for both, which is not a state production can produce.
    """
    import datetime  # noqa: PLC0415

    from app.domains.accounts.models import UserAccount  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    account = UserAccount(
        phone="+998901234567",
        name="Иван Петров",
        language="ru",
        status=AccountStatus.pending,
        applied_company_name="ООО Полимер",
        application_note="Хотим закупать ПВХ",
        must_change_password=False,
    )
    account.id = account_id
    account.created_at = datetime.datetime.now(datetime.UTC)
    return account


def _target(db: MagicMock, account) -> None:  # noqa: ANN001
    db.get.return_value = account
    db.execute.return_value.scalar_one_or_none.return_value = None  # login is free


# ── issuing ───────────────────────────────────────────────────────────────────


def test_issuing_credentials_activates_the_account_and_returns_the_password_once(
    admin_app,  # noqa: ANN001
) -> None:
    from app.core.security import verify_password  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    client, db, _actor = admin_app
    account = _application()
    _target(db, account)

    resp = client.post(f"{_BASE}/5/credentials", json={"login": "Acme-Trade"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["login"] == "acme-trade"  # folded on the way in
    assert len(body["password"]) >= 16
    # The account is now usable, and owes a first-login change.
    assert account.status == AccountStatus.active
    assert account.must_change_password is True
    assert account.credentials_issued_by == 1
    assert account.credentials_issued_at is not None
    # What is stored is a hash of what was returned, and nothing else.
    assert account.password_hash != body["password"]
    assert verify_password(body["password"], account.password_hash)


def test_a_staff_supplied_password_is_used_as_given(admin_app) -> None:  # noqa: ANN001
    from app.core.security import verify_password  # noqa: PLC0415

    client, db, _actor = admin_app
    account = _application()
    _target(db, account)

    resp = client.post(
        f"{_BASE}/5/credentials", json={"login": "acme", "password": "a-chosen-password"}
    )
    assert resp.status_code == 200
    assert resp.json()["password"] == "a-chosen-password"
    assert verify_password("a-chosen-password", account.password_hash)


def test_a_short_supplied_password_is_refused(admin_app) -> None:  # noqa: ANN001
    client, db, _actor = admin_app
    _target(db, _application())
    resp = client.post(f"{_BASE}/5/credentials", json={"login": "acme", "password": "short"})
    assert resp.status_code == 422


def test_a_taken_login_is_a_409_with_a_translatable_code(admin_app) -> None:  # noqa: ANN001
    client, db, _actor = admin_app
    db.get.return_value = _application()
    db.execute.return_value.scalar_one_or_none.return_value = 99  # somebody else has it

    resp = client.post(f"{_BASE}/5/credentials", json={"login": "acme-trade"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "login_taken"


def test_the_generated_password_avoids_ambiguous_characters(admin_app) -> None:  # noqa: ANN001
    """It is read off a printed contract and typed by hand, so `0/O/1/l/I` are out."""
    from app.domains.accounts.admin_service import generate_password  # noqa: PLC0415

    passwords = [generate_password() for _ in range(50)]
    assert all(len(p) >= 16 for p in passwords)
    assert not set("".join(passwords)) & set("0O1lI")
    assert len(set(passwords)) == 50  # `secrets`, not a fixed sequence


def test_an_unknown_account_is_404(admin_app) -> None:  # noqa: ANN001
    client, db, _actor = admin_app
    db.get.return_value = None
    assert client.post(f"{_BASE}/999/credentials", json={"login": "x"}).status_code == 404


# ── the password never appears anywhere else ──────────────────────────────────


def test_no_read_route_can_return_the_password(admin_app) -> None:  # noqa: ANN001
    """The account schema has no password field — the hash is not "masked", it is absent."""
    client, db, _actor = admin_app
    account = _application()
    _target(db, account)

    issued = client.post(f"{_BASE}/5/credentials", json={"login": "acme"}).json()["password"]

    detail = client.get(f"{_BASE}/5")
    assert detail.status_code == 200
    assert issued not in detail.text
    assert "password_hash" not in detail.text
    assert "password" not in detail.json()


def test_the_audit_row_records_the_act_and_not_the_secret(admin_app) -> None:  # noqa: ANN001
    """`login` is an identifier and belongs in the record; the password is not there
    in any form — not the value, not the hash, not its length."""
    client, db, _actor = admin_app
    account = _application()
    _target(db, account)

    with patch("app.domains.accounts.admin_service.write_audit") as audit:
        issued = client.post(f"{_BASE}/5/credentials", json={"login": "acme"}).json()["password"]

    audit.assert_called_once()
    kwargs = audit.call_args.kwargs
    assert kwargs["action"] == "portal_account.credentials_issued"
    assert kwargs["details"] == {"login": "acme"}
    assert issued not in str(kwargs)


def test_the_password_is_not_logged(admin_app, caplog) -> None:  # noqa: ANN001
    client, db, _actor = admin_app
    _target(db, _application())

    with caplog.at_level("DEBUG"):
        issued = client.post(f"{_BASE}/5/credentials", json={"login": "acme"}).json()["password"]

    assert issued not in caplog.text


# ── regenerate / block / unblock ──────────────────────────────────────────────


def test_regenerating_replaces_the_password_and_re_arms_the_forced_change(admin_app) -> None:  # noqa: ANN001
    from app.core.security import hash_password, verify_password  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    client, db, _actor = admin_app
    account = _application()
    account.login = "acme"
    account.password_hash = hash_password("the-old-password")
    account.status = AccountStatus.active
    account.must_change_password = False
    _target(db, account)

    resp = client.post(f"{_BASE}/5/password", json={})
    assert resp.status_code == 200
    new = resp.json()["password"]
    assert verify_password(new, account.password_hash)
    assert not verify_password("the-old-password", account.password_hash)
    assert account.must_change_password is True


def test_regenerating_for_an_account_with_no_login_is_refused(admin_app) -> None:  # noqa: ANN001
    client, db, _actor = admin_app
    _target(db, _application())  # an application: no login yet
    resp = client.post(f"{_BASE}/5/password", json={})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "no_credentials"


def test_blocking_closes_the_door_without_deleting_anything(admin_app) -> None:  # noqa: ANN001
    from app.core.security import hash_password  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    client, db, _actor = admin_app
    account = _application()
    account.login, account.password_hash = "acme", hash_password("x" * 12)
    account.status = AccountStatus.active
    _target(db, account)

    assert client.post(f"{_BASE}/5/block").status_code == 200
    assert account.status == AccountStatus.blocked
    assert db.delete.call_count == 0


def test_unblocking_an_account_that_never_had_credentials_is_refused(admin_app) -> None:  # noqa: ANN001
    """Otherwise it would be `active` and unable to sign in — a person the system
    believes is cleared to act, who cannot."""
    client, db, _actor = admin_app
    _target(db, _application())
    resp = client.post(f"{_BASE}/5/unblock")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "no_credentials"


# ── authorization ─────────────────────────────────────────────────────────────


def test_a_non_administrator_is_refused(admin_app) -> None:  # noqa: ANN001
    """There is no page grant that opens this — `require_admin` is the only key.

    Deliberate, and the same call `pages.py` makes for `adminUsers`: whoever can mint
    a cabinet credential can sign in as a customer, so it is not grantable.
    """
    from app.api.deps import get_current_staff_user  # noqa: PLC0415
    from app.models.staff import StaffUser  # noqa: PLC0415

    client, db, _actor = admin_app
    analyst = StaffUser(email="a@example.com", full_name="Analyst", is_admin=False)
    analyst.id = 2
    client.app.dependency_overrides[get_current_staff_user] = lambda: analyst
    _target(db, _application())

    assert client.get(_BASE).status_code == 403
    assert client.post(f"{_BASE}/5/credentials", json={"login": "acme"}).status_code == 403


def test_an_anonymous_caller_is_refused() -> None:
    from app.main import create_app  # noqa: PLC0415

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(
        create_app()
    ) as client:
        assert client.get(_BASE).status_code == 401


# ── technologist applications (0055) ────────────────────────────────────────


def test_the_queue_can_be_narrowed_to_technologists(admin_app) -> None:  # noqa: ANN001
    client, db, _actor = admin_app
    db.execute.return_value.scalars.return_value = []

    assert client.get(_BASE, params={"applied_as": "technologist"}).status_code == 200
    stmt = db.execute.call_args.args[0]
    # The column is in every SELECT list; what matters is the WHERE clause.
    assert "user_accounts.applied_as = " in str(stmt)


def test_staff_see_who_applied_as_what(admin_app) -> None:  # noqa: ANN001
    client, db, _actor = admin_app
    account = _application()
    account.applied_as = "technologist"
    _target(db, account)

    body = client.get(f"{_BASE}/5").json()
    assert body["applied_as"] == "technologist"


def test_an_unflushed_application_reads_as_a_company_one(admin_app) -> None:  # noqa: ANN001
    """The column default lands at INSERT; an in-memory row must still serialise."""
    client, db, _actor = admin_app
    _target(db, _application())
    assert client.get(f"{_BASE}/5").json()["applied_as"] == "company"
