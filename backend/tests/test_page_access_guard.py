"""The per-page guard, driven through real endpoints.

`require_page` decides whether a staff account may reach a screen. These drive
routes people actually use rather than a fixture built to be tested, because a
guard proven only against a purpose-made hook can pass while the endpoints that
matter are gated on something else — or on nothing.

The properties under test:
  * a grant on the right page at the right level admits;
  * `write` admits a reader, `read` does not admit a writer;
  * NO GRANT DENIES — absence is the denial, which is what makes a page added to
    the catalog later closed rather than open;
  * an administrator bypasses the matrix entirely;
  * an endpoint serving several screens admits anyone who holds ANY of them.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# (path, the page that grants it, the level it needs)
READ_ROUTES = [
    ("/api/v1/admin/deals", "deals", "read"),
    ("/api/v1/admin/verification/cases", "verification", "read"),
    ("/api/v1/admin/substances", "substances", "read"),
    ("/api/v1/admin/moderation/offers", "moderation", "read"),
]


def _staff(*, is_admin: bool = False, user_id: int = 7) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.email = "staff@polymer.uz"
    user.full_name = "Staff Member"
    user.is_admin = is_admin
    user.is_active = True
    return user


def _client(user: MagicMock, grants: dict[str, str]) -> TestClient:
    """A TestClient where `user` holds exactly `grants`.

    The identity is injected; the GUARD ITSELF IS NOT MOCKED — it runs against a
    session that answers the grant lookup from `grants`, so what the test proves
    is the real decision.
    """
    from app.api.deps import get_current_staff_user
    from app.core.db import get_db
    from app.main import create_app

    db = MagicMock()

    def _execute(stmt: Any, *a: Any, **kw: Any) -> MagicMock:
        result = MagicMock()
        # Both the guard and page_access_for select (page, access) rows.
        result.all.return_value = list(grants.items())
        result.scalar_one_or_none.return_value = None
        result.fetchall.return_value = []
        return result

    db.execute.side_effect = _execute
    db.query.return_value.filter.return_value.first.return_value = user
    db.query.return_value.order_by.return_value.all.return_value = []

    def _override_db() -> Generator[Any, None, None]:
        yield db

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_staff_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


# ── The grant admits ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("path,page,_level", READ_ROUTES)
def test_read_grant_admits(path: str, page: str, _level: str) -> None:
    resp = _client(_staff(), {page: "read"}).get(path)
    assert resp.status_code != 403, resp.text


@pytest.mark.parametrize("path,page,_level", READ_ROUTES)
def test_write_grant_admits_a_reader(path: str, page: str, _level: str) -> None:
    """`write` implies `read` — otherwise every editable page needs both ticked."""
    resp = _client(_staff(), {page: "write"}).get(path)
    assert resp.status_code != 403, resp.text


# ── Absence denies ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path,page,_level", READ_ROUTES)
def test_no_grant_denies(path: str, page: str, _level: str) -> None:
    """The property that makes a newly added page closed rather than open."""
    resp = _client(_staff(), {}).get(path)
    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize("path,page,_level", READ_ROUTES)
def test_a_grant_on_a_different_page_denies(path: str, page: str, _level: str) -> None:
    """Holding one page must not leak into another."""
    other = "alerts" if page != "alerts" else "deals"
    resp = _client(_staff(), {other: "write"}).get(path)
    assert resp.status_code == 403, resp.text


def test_read_grant_does_not_admit_a_write() -> None:
    """Read is not write — the split is the whole point of three levels."""
    resp = _client(_staff(), {"substances": "read"}).post(
        "/api/v1/admin/substances", json={}
    )
    assert resp.status_code == 403, resp.text


def test_write_grant_admits_a_write() -> None:
    resp = _client(_staff(), {"substances": "write"}).post(
        "/api/v1/admin/substances", json={}
    )
    # 422 (the empty body) means the guard let it through, which is what we assert.
    assert resp.status_code != 403, resp.text


# ── Administrators bypass ─────────────────────────────────────────────────────


@pytest.mark.parametrize("path,page,_level", READ_ROUTES)
def test_administrator_needs_no_grants(path: str, page: str, _level: str) -> None:
    """An administrator holds every page, including ones added after their account."""
    resp = _client(_staff(is_admin=True), {}).get(path)
    assert resp.status_code != 403, resp.text


# ── Endpoints that serve more than one screen ─────────────────────────────────


@pytest.mark.parametrize("granted", ["dashboard", "liveFeed", "offers"])
def test_feed_admits_any_page_that_renders_it(granted: str) -> None:
    """`GET /feed` backs three screens, so any one of them admits.

    Gating it on the live feed alone would leave somebody granted only the
    dashboard staring at a permission error on their landing page.
    """
    resp = _client(_staff(), {granted: "read"}).get("/api/v1/feed")
    assert resp.status_code != 403, resp.text


def test_feed_denies_someone_holding_none_of_its_pages() -> None:
    resp = _client(_staff(), {"alerts": "write"}).get("/api/v1/feed")
    assert resp.status_code == 403, resp.text


# ── Staff administration is not grantable ─────────────────────────────────────


def test_page_grants_cannot_reach_staff_administration() -> None:
    """No combination of page grants opens /admin/users — it needs `is_admin`.

    This is the privilege-escalation guard: whoever can edit staff accounts can
    mint an administrator, so it must not be something an administrator can hand
    out.
    """
    from app.core.pages import PAGES  # noqa: PLC0415

    every_page = {p.key: "write" for p in PAGES}
    client = _client(_staff(), every_page)
    assert client.get("/api/v1/admin/users").status_code == 403
    assert client.get("/api/v1/admin/pages").status_code == 403
