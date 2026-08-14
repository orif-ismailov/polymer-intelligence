"""Portal notification-centre API tests (R2 W3 T3.5).

Route reg DB-free; the rest against test_polymer (guarded): list + unread-count +
mark-read (ids / all), account isolation, and keyset pagination.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)

_BASE = "/api/v1/portal/notifications"


def test_notification_routes_registered() -> None:
    from app.domains.notifications.api_portal import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/notifications" in paths
    assert "/portal/notifications/unread-count" in paths
    assert "/portal/notifications/read" in paths


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    app = create_app()

    def _override_db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


def _seed(db, account_id: int, n: int):  # noqa: ANN001, ANN202
    from app.services import notification_service  # noqa: PLC0415

    for i in range(n):
        notification_service.notify_account(
            db, account_id, kind="request_status",
            title_key="notifications.request_status.title",
            body_key="notifications.request_status.body",
            params={"n": i}, entity="request", entity_id=str(i),
        )


@requires_real_db
def test_list_unread_count_and_mark_read(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        account = make_account(db, "+998900008001")
        _seed(db, account.id, 3)
        db.commit()
        account_id = account.id

    assert client.get(f"{_BASE}/unread-count", headers=_auth(account_id)).json()["count"] == 3

    page = client.get(_BASE, headers=_auth(account_id)).json()
    assert len(page["items"]) == 3
    assert page["items"][0]["title_key"] == "notifications.request_status.title"

    first_id = page["items"][0]["id"]
    marked = client.post(
        f"{_BASE}/read", json={"ids": [first_id]}, headers=_auth(account_id)
    ).json()
    assert marked["marked"] == 1
    assert client.get(f"{_BASE}/unread-count", headers=_auth(account_id)).json()["count"] == 2

    # mark all
    assert client.post(f"{_BASE}/read", json={"all": True}, headers=_auth(account_id)).json()["marked"] == 2
    assert client.get(f"{_BASE}/unread-count", headers=_auth(account_id)).json()["count"] == 0

    # unread_only now returns nothing
    assert client.get(_BASE, params={"unread_only": True}, headers=_auth(account_id)).json()["items"] == []


@requires_real_db
def test_account_isolation_and_pagination(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        a = make_account(db, "+998900008100")
        b = make_account(db, "+998900008101")
        _seed(db, a.id, 5)
        _seed(db, b.id, 1)
        db.commit()
        a_id, b_id = a.id, b.id

    # A sees only A's 5
    assert client.get(f"{_BASE}/unread-count", headers=_auth(a_id)).json()["count"] == 5
    assert client.get(f"{_BASE}/unread-count", headers=_auth(b_id)).json()["count"] == 1

    # keyset pagination
    p1 = client.get(_BASE, params={"limit": 2}, headers=_auth(a_id)).json()
    assert len(p1["items"]) == 2
    assert p1["next_cursor"] is not None
    p2 = client.get(
        _BASE, params={"limit": 2, "cursor": p1["next_cursor"]}, headers=_auth(a_id)
    ).json()
    assert len(p2["items"]) == 2
    # newest-first, non-overlapping pages
    assert {i["id"] for i in p1["items"]} & {i["id"] for i in p2["items"]} == set()
