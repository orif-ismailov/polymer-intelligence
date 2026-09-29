"""POST /portal/me/delete — the router's contract (mock DB + FakeRedis).

The store-facing contract the mobile app codes against is fixed: 204 on success,
400 `invalid_password`, 401 unauthenticated. What the deletion does to the database
is asserted against real Postgres in `test_account_deletion_db.py`; this file covers
what a caller can observe and runs in CI.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis

_DELETE = "/api/v1/portal/me/delete"
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


def _account(account_id: int = 7, *, must_change: bool = False):  # noqa: ANN202
    from app.core.security import hash_password  # noqa: PLC0415
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    acct = UserAccount(
        phone="+998901234567",
        language="ru",
        status=AccountStatus.active,
        login="acme-trade",
        password_hash=hash_password(_PASS),
        must_change_password=must_change,
    )
    acct.id = account_id
    return acct


def _found(db: MagicMock, account) -> None:  # noqa: ANN001
    db.query.return_value.filter.return_value.first.return_value = account


def _signed_in(fake: FakeRedis, account_id: int = 7) -> tuple[str, str]:
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
    return create_portal_access_token(subject=str(account_id), fam=fam), fam


def test_unauthenticated_is_401(portal_app) -> None:  # noqa: ANN001
    client, _fake, _db = portal_app
    resp = client.post(_DELETE, json={"password": _PASS})
    assert resp.status_code == 401


def test_wrong_password_is_400_invalid_password_and_deletes_nothing(portal_app) -> None:  # noqa: ANN001
    client, fake, db = portal_app
    account = _account()
    _found(db, account)
    token, fam = _signed_in(fake)

    with patch("app.domains.accounts.deletion.delete_account") as deleted:
        resp = client.post(
            _DELETE, json={"password": "wrong"}, headers={"Authorization": f"Bearer {token}"}
        )

    assert resp.status_code == 400
    assert resp.json() == {"detail": "invalid_password"}
    deleted.assert_not_called()
    db.commit.assert_not_called()
    assert f"rs:{fam}" in fake.store  # the session survives a failed attempt


def test_success_is_204_revokes_the_session_and_clears_the_cookie(portal_app) -> None:  # noqa: ANN001
    client, fake, db = portal_app
    account = _account()
    _found(db, account)
    token, fam = _signed_in(fake)

    with patch(
        "app.domains.accounts.deletion.delete_account", return_value=[]
    ) as deleted:
        resp = client.post(
            _DELETE, json={"password": _PASS}, headers={"Authorization": f"Bearer {token}"}
        )

    assert resp.status_code == 204
    assert resp.content == b""
    deleted.assert_called_once_with(db, account)
    db.commit.assert_called_once()
    assert f"rs:{fam}" not in fake.store
    cookie = resp.headers.get("set-cookie", "")
    assert "portal_session=" in cookie
    assert "Max-Age=0" in cookie or "expires=" in cookie.lower()


def test_the_portrait_is_discarded_only_after_the_commit(portal_app) -> None:  # noqa: ANN001
    client, fake, db = portal_app
    _found(db, _account())
    token, _fam = _signed_in(fake)
    order: list[str] = []
    db.commit.side_effect = lambda: order.append("commit")

    with (
        patch("app.domains.accounts.deletion.delete_account", return_value=["tech/1/p.jpg"]),
        patch(
            "app.services.storage_service.discard_object",
            side_effect=lambda key, context: order.append(f"discard:{key}"),
        ),
    ):
        resp = client.post(
            _DELETE, json={"password": _PASS}, headers={"Authorization": f"Bearer {token}"}
        )

    assert resp.status_code == 204
    assert order == ["commit", "discard:tech/1/p.jpg"]


def test_the_first_login_gate_applies(portal_app) -> None:  # noqa: ANN001
    """An account still on its staff-issued password must set its own first."""
    client, fake, db = portal_app
    _found(db, _account(must_change=True))
    token, _fam = _signed_in(fake)

    resp = client.post(
        _DELETE, json={"password": _PASS}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "password_change_required"


def test_attempts_are_capped_per_account(portal_app) -> None:  # noqa: ANN001
    """Not a password oracle: five wrong guesses in five minutes, then 429."""
    from app.services import rate_limit  # noqa: PLC0415

    client, fake, db = portal_app
    _found(db, _account())
    token, _fam = _signed_in(fake)
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(rate_limit.PORTAL_PASSWORD_CHANGE_PER_5MIN):
        assert client.post(_DELETE, json={"password": "x"}, headers=headers).status_code == 400
    resp = client.post(_DELETE, json={"password": _PASS}, headers=headers)
    assert resp.status_code == 429
    assert "retry-after" in {k.lower() for k in resp.headers}


def test_a_deleted_account_is_refused_by_the_guard(portal_app) -> None:  # noqa: ANN001
    """Every outstanding access token dies with the account — the status does it."""
    from app.models.enums import AccountStatus  # noqa: PLC0415

    client, fake, db = portal_app
    account = _account()
    account.status = AccountStatus.deleted
    _found(db, account)
    token, _fam = _signed_in(fake)

    resp = client.get("/api/v1/portal/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_admin_actions_refuse_a_deleted_account() -> None:
    from app.domains.accounts import admin_service as svc  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    account = _account()
    account.status = AccountStatus.deleted
    actor = MagicMock(id=1)
    db = MagicMock()

    for act in (
        lambda: svc.issue_credentials(db, actor=actor, target=account, login="x", password="y"),
        lambda: svc.regenerate_password(db, actor=actor, target=account, password="y"),
        lambda: svc.set_status(db, actor=actor, target=account, status=AccountStatus.active),
        lambda: svc.set_status(db, actor=actor, target=account, status=AccountStatus.blocked),
    ):
        with pytest.raises(svc.PortalAdminRefused) as exc:
            act()
        assert exc.value.code == "account_deleted"
