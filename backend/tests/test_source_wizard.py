"""
Tests for the sources wizard API (POST/GET/PATCH /sources + POST /sources/{id}/test).

Covers:
- test_html_table_test: POST /sources/{id}/test with html_table -> ok + <=10 rows
- test_enable_gate: PATCH /sources/{id} with is_enabled=True but no test -> 422 (T-04-20)
- test_pending_source: telegram_channel source saved -> is_enabled=False, last_test_ok_at=NULL
- test_get_sources_health: GET /sources returns SourceHealthItem[] without config
- test_non_admin_rejected: POST/PATCH/POST-test require admin (T-04-21)
- test_all_four_no_code_types: GET /admin/source-types includes html_table/rss/
  telegram_channel/llm_page with no_code=True after startup registration

Security:
- T-04-20: server-side enable-gate (is_enabled=True requires last_test_ok_at IS NOT NULL)
- T-04-21: admin-only write endpoints
- T-04-22: GET /sources never exposes config column
"""

from __future__ import annotations

import datetime
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

# ── Test helpers ─────────────────────────────────────────────────────────────


def _make_staff_user(role: str, user_id: int = 1, is_active: bool = True):
    """Create a mock StaffUser with the given role."""

    user = MagicMock()
    user.id = user_id
    user.email = f"{role}@polymer.uz"
    user.is_admin = role == "admin"
    user.is_active = is_active
    return user


def _auth_headers(user_id: int, role: str) -> dict[str, str]:
    """Create a Bearer Authorization header."""
    from app.core.security import create_access_token  # noqa: PLC0415

    token = create_access_token(subject=str(user_id))
    return {"Authorization": f"Bearer {token}"}


def _make_mock_source(
    source_id: int = 1,
    adapter: str = "html_table",
    name: str = "Test Source",
    is_enabled: bool = False,
    last_test_ok_at: datetime.datetime | None = None,
    config: dict | None = None,
) -> MagicMock:
    """Create a mock Source ORM object."""
    source = MagicMock()
    source.id = source_id
    source.name = name
    source.adapter = adapter
    # Use string value directly (not the enum instance) to avoid attribute-set
    # issues with Python 3.14 enum (cannot set .value on enum member)
    mock_kind = MagicMock()
    mock_kind.value = "website"
    source.kind = mock_kind
    source.is_enabled = is_enabled
    source.last_test_ok_at = last_test_ok_at
    source.last_fetch_at = None
    source.last_success_at = None
    source.consecutive_failures = 0
    source.config = config or {"url": "https://example.com/data"}
    source.created_at = datetime.datetime(2026, 6, 17, tzinfo=datetime.UTC)
    return source


def _make_client_with_user_and_db(
    staff_user: MagicMock,
    mock_db: MagicMock | None = None,
) -> TestClient:
    """Build a TestClient with get_db mocked to include the given staff_user."""
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    if mock_db is None:
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = staff_user

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    return TestClient(application, raise_server_exceptions=True)


# ── GET /sources ───────────────────────────────────────────────────────────────


def test_get_sources_returns_200_for_admin():
    """GET /api/v1/sources returns 200 for admin users."""
    admin_user = _make_staff_user("admin", user_id=1)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = admin_user
    # Mock the db.execute for the health query
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_db.execute.return_value = mock_result

    client = _make_client_with_user_and_db(admin_user, mock_db)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/sources", headers=_auth_headers(1, "admin"))

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_sources_response_has_no_config_field():
    """GET /api/v1/sources response items do not include 'config' field (T-04-22)."""
    admin_user = _make_staff_user("admin", user_id=1)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = admin_user

    # Simulate a source row with various fields
    source_row = MagicMock()
    source_row.__iter__ = MagicMock(return_value=iter([]))
    # The row returned from sa.text() is a Row object with _mapping or positional access
    # We simulate a row tuple: (id, name, adapter, kind, is_enabled, last_fetch_at,
    #                            last_success_at, consecutive_failures, last_test_ok_at)
    mock_row = (
        1, "My Source", "html_table", "website", False, None, None, 0,
        datetime.datetime(2026, 6, 17, tzinfo=datetime.UTC)
    )
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [mock_row]
    mock_db.execute.return_value = mock_result

    client = _make_client_with_user_and_db(admin_user, mock_db)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/sources", headers=_auth_headers(1, "admin"))

    assert resp.status_code == 200
    data = resp.json()
    if data:
        # Each item must NOT have a 'config' field (T-04-22)
        for item in data:
            assert "config" not in item, f"config column exposed in GET /sources: {item}"


# ── POST /sources ──────────────────────────────────────────────────────────────


def test_post_sources_non_admin_rejected():
    """POST /sources returns 403 for non-admin users."""
    trader_user = _make_staff_user("trader", user_id=3)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = trader_user

    client = _make_client_with_user_and_db(trader_user, mock_db)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.post(
            "/api/v1/sources",
            json={"adapter": "html_table", "name": "X", "config": {"url": "https://example.com"}},
            headers=_auth_headers(3, "trader"),
        )

    assert resp.status_code == 403


# ── POST /sources/{id}/test ────────────────────────────────────────────────────


def test_html_table_test_endpoint_returns_ok():
    """POST /sources/{id}/test with html_table config returns ok=True + sample_rows."""
    admin_user = _make_staff_user("admin", user_id=1)
    mock_source = _make_mock_source(source_id=1, adapter="html_table")

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = admin_user
    mock_db.get.return_value = mock_source

    from app.ingest.base import TestResult  # noqa: PLC0415

    mock_test_result = TestResult(
        ok=True,
        sample_rows=[
            {"product": "PP Raffia", "grade": "H030GP", "volume": "20", "price": "1200",
             "currency": "USD", "section": None, "event_at": None}
        ],
    )

    client = _make_client_with_user_and_db(admin_user, mock_db)

    with (
        patch("app.api.health._check_redis", return_value="ok"),
        patch("app.ingest.registry.get_adapter") as mock_get_adapter,
    ):
        mock_adapter = MagicMock()
        mock_adapter.test = AsyncMock(return_value=mock_test_result)
        mock_get_adapter.return_value = mock_adapter

        resp = client.post(
            "/api/v1/sources/1/test",
            headers=_auth_headers(1, "admin"),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert isinstance(data["sample_rows"], list)
    assert len(data["sample_rows"]) <= 10


def test_test_endpoint_sets_last_test_ok_at_on_pass():
    """POST /sources/{id}/test sets last_test_ok_at when ok=True."""
    admin_user = _make_staff_user("admin", user_id=1)
    mock_source = _make_mock_source(source_id=1, adapter="html_table", last_test_ok_at=None)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = admin_user
    mock_db.get.return_value = mock_source

    from app.ingest.base import TestResult  # noqa: PLC0415

    mock_test_result = TestResult(ok=True, sample_rows=[{"product": "PP", "grade": None,
        "volume": None, "price": None, "currency": "USD", "section": None, "event_at": None}])

    client = _make_client_with_user_and_db(admin_user, mock_db)

    with (
        patch("app.api.health._check_redis", return_value="ok"),
        patch("app.ingest.registry.get_adapter") as mock_get_adapter,
    ):
        mock_adapter = MagicMock()
        mock_adapter.test = AsyncMock(return_value=mock_test_result)
        mock_get_adapter.return_value = mock_adapter

        resp = client.post(
            "/api/v1/sources/1/test",
            headers=_auth_headers(1, "admin"),
        )

    assert resp.status_code == 200
    # last_test_ok_at should have been set on the mock source
    assert mock_source.last_test_ok_at is not None
    assert mock_db.commit.called


def test_test_endpoint_does_not_set_last_test_ok_at_on_fail():
    """POST /sources/{id}/test does NOT set last_test_ok_at when ok=False."""
    admin_user = _make_staff_user("admin", user_id=1)
    mock_source = _make_mock_source(
        source_id=2, adapter="telegram_channel", last_test_ok_at=None
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = admin_user
    mock_db.get.return_value = mock_source

    from app.ingest.base import TestResult  # noqa: PLC0415

    mock_test_result = TestResult(ok=False, error="Available after Phase 5")

    client = _make_client_with_user_and_db(admin_user, mock_db)

    with (
        patch("app.api.health._check_redis", return_value="ok"),
        patch("app.ingest.registry.get_adapter") as mock_get_adapter,
    ):
        mock_adapter = MagicMock()
        mock_adapter.test = AsyncMock(return_value=mock_test_result)
        mock_get_adapter.return_value = mock_adapter

        resp = client.post(
            "/api/v1/sources/2/test",
            headers=_auth_headers(1, "admin"),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["error"] == "Available after Phase 5"
    # last_test_ok_at must NOT be set
    assert mock_source.last_test_ok_at is None
    assert not mock_db.commit.called


# ── PATCH /sources/{id} — enable-gate ────────────────────────────────────────


def test_enable_gate_returns_422_when_no_test_passed():
    """PATCH /sources/{id} with is_enabled=True and last_test_ok_at=NULL -> 422 (T-04-20)."""
    admin_user = _make_staff_user("admin", user_id=1)
    # Source has never been tested (last_test_ok_at is None)
    mock_source = _make_mock_source(source_id=3, is_enabled=False, last_test_ok_at=None)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = admin_user
    mock_db.get.return_value = mock_source

    client = _make_client_with_user_and_db(admin_user, mock_db)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.patch(
            "/api/v1/sources/3",
            json={"is_enabled": True},
            headers=_auth_headers(1, "admin"),
        )

    assert resp.status_code == 422, f"Expected 422 but got {resp.status_code}: {resp.text}"


def test_enable_gate_allows_enable_when_test_passed():
    """PATCH /sources/{id} with is_enabled=True and last_test_ok_at set -> 200."""
    admin_user = _make_staff_user("admin", user_id=1)
    # Source has passed a test
    mock_source = _make_mock_source(
        source_id=4,
        is_enabled=False,
        last_test_ok_at=datetime.datetime(2026, 6, 17, 12, 0, tzinfo=datetime.UTC),
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = admin_user
    mock_db.get.return_value = mock_source

    client = _make_client_with_user_and_db(admin_user, mock_db)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.patch(
            "/api/v1/sources/4",
            json={"is_enabled": True},
            headers=_auth_headers(1, "admin"),
        )

    assert resp.status_code == 200


def test_disable_source_does_not_require_test():
    """PATCH /sources/{id} with is_enabled=False (disable) does not require a test."""
    admin_user = _make_staff_user("admin", user_id=1)
    mock_source = _make_mock_source(
        source_id=5, is_enabled=True, last_test_ok_at=None
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = admin_user
    mock_db.get.return_value = mock_source

    client = _make_client_with_user_and_db(admin_user, mock_db)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.patch(
            "/api/v1/sources/5",
            json={"is_enabled": False},
            headers=_auth_headers(1, "admin"),
        )

    assert resp.status_code == 200


# ── Pending source tests ──────────────────────────────────────────────────────


def test_pending_source_stays_disabled():
    """telegram_channel source test() returns ok=False, so last_test_ok_at stays NULL."""
    admin_user = _make_staff_user("admin", user_id=1)
    mock_source = _make_mock_source(
        source_id=6, adapter="telegram_channel", is_enabled=False, last_test_ok_at=None
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = admin_user
    mock_db.get.return_value = mock_source

    from app.ingest.base import TestResult  # noqa: PLC0415

    pending_result = TestResult(ok=False, error="Available after Phase 5")

    client = _make_client_with_user_and_db(admin_user, mock_db)

    with (
        patch("app.api.health._check_redis", return_value="ok"),
        patch("app.ingest.registry.get_adapter") as mock_get_adapter,
    ):
        mock_adapter = MagicMock()
        mock_adapter.test = AsyncMock(return_value=pending_result)
        mock_get_adapter.return_value = mock_adapter

        resp = client.post(
            "/api/v1/sources/6/test",
            headers=_auth_headers(1, "admin"),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    # Pending source must stay disabled — last_test_ok_at never set
    assert mock_source.last_test_ok_at is None


# ── Admin-only access (T-04-21) ───────────────────────────────────────────────


def test_non_admin_post_sources_rejected():
    """POST /sources returns 403 for non-admin roles (T-04-21)."""
    trader_user = _make_staff_user("trader", user_id=3)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = trader_user

    client = _make_client_with_user_and_db(trader_user, mock_db)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.post(
            "/api/v1/sources",
            json={"adapter": "html_table", "name": "X", "config": {}},
            headers=_auth_headers(3, "trader"),
        )

    assert resp.status_code == 403


def test_non_admin_patch_sources_rejected():
    """PATCH /sources/{id} returns 403 for non-admin roles (T-04-21)."""
    analyst_user = _make_staff_user("analyst", user_id=2)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = analyst_user

    client = _make_client_with_user_and_db(analyst_user, mock_db)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.patch(
            "/api/v1/sources/1",
            json={"is_enabled": True},
            headers=_auth_headers(2, "analyst"),
        )

    assert resp.status_code == 403


# ── GET /admin/source-types includes all four no-code adapters ────────────────


def test_all_four_no_code_types_in_source_types():
    """GET /admin/source-types includes html_table/rss/telegram_channel/llm_page."""
    # Ensure all four adapters are registered for this test. Prior test files
    # (e.g. test_admin_source_types.py) clear the registry via an autouse fixture;
    # module-level imports in main.py don't re-run once modules are cached.
    # We directly populate the registry dict (same pattern as clean_registry fixtures).
    import app.ingest.html_table.adapter as _ht  # noqa: PLC0415
    import app.ingest.llm_page.adapter as _llm  # noqa: PLC0415
    import app.ingest.rss.adapter as _rss  # noqa: PLC0415
    import app.ingest.telegram_channel.adapter as _tg  # noqa: PLC0415
    from app.ingest import registry as _reg  # noqa: PLC0415

    _reg._REGISTRY.setdefault("html_table", _ht.HtmlTableAdapter())
    _reg._REGISTRY.setdefault("rss", _rss.RssAdapter())
    _reg._REGISTRY.setdefault("telegram_channel", _tg.TelegramChannelAdapter())
    _reg._REGISTRY.setdefault("llm_page", _llm.LlmPageAdapter())

    admin_user = _make_staff_user("admin", user_id=1)
    client = _make_client_with_user_and_db(admin_user)

    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get(
            "/api/v1/admin/source-types",
            headers=_auth_headers(1, "admin"),
        )

    assert resp.status_code == 200
    type_names = {item["type_name"] for item in resp.json()}
    for expected in ("html_table", "rss", "telegram_channel", "llm_page"):
        assert expected in type_names, f"{expected} not in source-types: {type_names}"
    # Verify no_code=True for all four
    items = {item["type_name"]: item for item in resp.json()}
    for t in ("html_table", "rss", "telegram_channel", "llm_page"):
        assert items[t]["no_code"] is True, f"{t} should have no_code=True"


# ── Router mounting check ──────────────────────────────────────────────────────


def test_sources_router_mounted():
    """POST/GET /api/v1/sources* routes exist in the app."""
    from app.main import create_app  # noqa: PLC0415

    app = create_app()
    # Resolve the route by endpoint name via url_path_for. This traverses FastAPI
    # >=0.137's lazy `_IncludedRouter` inclusion tree (unlike walking `app.routes`
    # for a flat `.path`, which only sees inline routes under Starlette 1.x) and
    # raises NoMatchFound if the sources router was not mounted.
    path = app.url_path_for("get_sources")
    assert path.startswith("/api/v1/sources"), (
        f"Expected /api/v1/sources* route, got: {path}"
    )


# ── GET /sources/{id} detail (with config) + config edit (Phase 8g) ─────────────


def _news_source(source_id: int, **over):
    src = _make_mock_source(source_id=source_id, adapter="rss",
                            config={"url": "https://feed/rss", "content_kind": "news"}, **over)
    src.country = "UZ"
    src.group_name = "Global"
    src.url = "https://feed/rss"
    return src


def test_get_source_detail_returns_config_for_admin():
    """GET /sources/{id} returns the config (admin-only edit view)."""
    admin = _make_staff_user("admin", 1)
    src = _news_source(7)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = admin
    db.get.return_value = src
    client = _make_client_with_user_and_db(admin, db)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/sources/7", headers=_auth_headers(1, "admin"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["config"]["url"] == "https://feed/rss"
    assert body["config"]["content_kind"] == "news"
    assert body["group_name"] == "Global"


def test_get_source_detail_non_admin_403():
    analyst = _make_staff_user("analyst", 2)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = analyst
    client = _make_client_with_user_and_db(analyst, db)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.get("/api/v1/sources/7", headers=_auth_headers(2, "analyst"))
    assert resp.status_code == 403


def test_edit_config_resets_test_and_disables():
    """Editing the feed config re-validates, clears last_test_ok_at, and disables it."""
    admin = _make_staff_user("admin", 1)
    src = _news_source(8, is_enabled=True,
                       last_test_ok_at=datetime.datetime(2026, 6, 17, tzinfo=datetime.UTC))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = admin
    db.get.return_value = src
    client = _make_client_with_user_and_db(admin, db)
    with patch("app.api.health._check_redis", return_value="ok"), \
         patch("app.ingest.registry.get_adapter") as mock_get:
        mock_get.return_value = MagicMock()  # config_schema(**cfg) accepts it
        resp = client.patch(
            "/api/v1/sources/8",
            json={"config": {"url": "https://new/rss", "content_kind": "news"}},
            headers=_auth_headers(1, "admin"),
        )
    assert resp.status_code == 200, resp.text
    assert src.config == {"url": "https://new/rss", "content_kind": "news"}
    assert src.url == "https://new/rss"
    assert src.last_test_ok_at is None   # reset — must re-test
    assert src.is_enabled is False       # disabled until re-tested


def test_edit_invalid_config_422():
    admin = _make_staff_user("admin", 1)
    src = _news_source(9)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = admin
    db.get.return_value = src
    client = _make_client_with_user_and_db(admin, db)
    with patch("app.api.health._check_redis", return_value="ok"), \
         patch("app.ingest.registry.get_adapter") as mock_get:
        bad = MagicMock()
        bad.config_schema.side_effect = ValueError("url is required")
        mock_get.return_value = bad
        resp = client.patch(
            "/api/v1/sources/9", json={"config": {"nope": 1}}, headers=_auth_headers(1, "admin")
        )
    assert resp.status_code == 422


def test_edit_name_and_country_only_keeps_test_state():
    """Editing only name/country/group must NOT reset the tested/enabled state."""
    admin = _make_staff_user("admin", 1)
    src = _news_source(10, is_enabled=True,
                       last_test_ok_at=datetime.datetime(2026, 6, 17, tzinfo=datetime.UTC))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = admin
    db.get.return_value = src
    client = _make_client_with_user_and_db(admin, db)
    with patch("app.api.health._check_redis", return_value="ok"):
        resp = client.patch(
            "/api/v1/sources/10",
            json={"name": "Renamed feed", "country": "RU", "group_name": "Producers"},
            headers=_auth_headers(1, "admin"),
        )
    assert resp.status_code == 200, resp.text
    assert src.name == "Renamed feed"
    assert src.country == "RU"
    assert src.group_name == "Producers"
    assert src.last_test_ok_at is not None  # unchanged
    assert src.is_enabled is True           # unchanged
