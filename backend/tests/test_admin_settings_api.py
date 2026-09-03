"""
Tests for the admin settings + news-ops API (mocked db/auth).

`/admin/settings` is read/write/reset, gated on the `appSettings` page — plus
`is_admin` for the two Didox credentials. DB + services are mocked; the
precedence and validation rules themselves live in `test_settings_env_source.py`.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _app(*, is_admin: bool = True, can_write: bool = True):  # noqa: ANN202
    from app.api.deps import get_current_staff_user, require_admin  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    def _db() -> Generator[Any, None, None]:
        yield MagicMock()

    user = MagicMock(id=3, is_admin=is_admin, is_active=True)

    if not is_admin and can_write:
        # A non-administrator reaches this router through a page grant, and
        # `_resolve_page_access` reads that grant off the session. Without it the
        # page guard refuses first, and the sensitive-key test below would pass
        # on a build where the sensitive gate had been deleted.
        def _db() -> Generator[Any, None, None]:  # noqa: F811
            session = MagicMock()
            session.execute.return_value.all.return_value = [("appSettings", "write")]
            yield session

    application = create_app()
    application.dependency_overrides[get_db] = _db
    application.dependency_overrides[require_admin] = lambda: user
    application.dependency_overrides[get_current_staff_user] = lambda: user
    return application, user


def _client(**kwargs: Any) -> TestClient:
    application, _ = _app(**kwargs)
    with patch("app.api.health._check_redis", return_value="ok"):
        return TestClient(application, raise_server_exceptions=False)


def _item(**overrides: Any) -> dict[str, Any]:
    """A `get_all` row. Every field the schema requires, so a patched service
    cannot silently drift from the response model."""
    base = {
        "key": "news_ai_enabled",
        "label": "AI summaries in reports",
        "group": "news",
        "value": True,
        "env_value": True,
        "env_var": "NEWS_AI_ENABLED",
        "overridden": False,
        "overridden_by": None,
        "overridden_at": None,
        "editable": True,
        "sensitive": False,
        "confirm": "",
        "kind": "bool",
        "choices": [],
    }
    base.update(overrides)
    return base


class TestSettingsRead:
    def test_list_settings(self) -> None:
        with patch("app.api.admin_settings.settings_service.get_all", return_value=[_item()]):
            resp = _client().get("/api/v1/admin/settings")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["key"] == "news_ai_enabled"

    def test_list_settings_names_the_env_var(self) -> None:
        """The value alone is not actionable — the panel has to say where to change it."""
        resp = _client().get("/api/v1/admin/settings")
        assert resp.status_code == 200, resp.text
        by_key = {r["key"]: r for r in resp.json()}
        assert by_key["didox_mode"]["env_var"] == "DIDOX_MODE"
        assert by_key["gov_registry_mode"]["env_var"] == "GOV_REGISTRY_MODE"

    def test_every_row_carries_both_values(self) -> None:
        """`value` and `env_value` together are the screen's whole point: one
        says what is running, the other says what Reset would restore."""
        resp = _client().get("/api/v1/admin/settings")
        assert resp.status_code == 200, resp.text
        for row in resp.json():
            assert "value" in row and "env_value" in row, row
            assert row["overridden"] is False, "a mocked db has no override rows"
            assert row["value"] == row["env_value"], row["key"]

    def test_list_settings_requires_auth(self) -> None:
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        def _db() -> Generator[Any, None, None]:
            yield MagicMock()

        app = create_app()
        app.dependency_overrides[get_db] = _db  # no auth override → must be rejected
        with patch("app.api.health._check_redis", return_value="ok"), TestClient(
            app, raise_server_exceptions=False
        ) as tc:
            resp = tc.get("/api/v1/admin/settings")
        assert resp.status_code == 401, resp.text


class TestSettingsWrite:
    """The write path exists. What it must never do is the interesting part."""

    def test_unknown_key_is_404(self) -> None:
        resp = _client().put("/api/v1/admin/settings/not_a_setting", json={"value": 1})
        assert resp.status_code == 404, resp.text

    def test_a_bad_value_is_refused(self) -> None:
        resp = _client().put(
            "/api/v1/admin/settings/gov_registry_mode", json={"value": "didoks"}
        )
        assert resp.status_code == 400, resp.text
        assert "stub" in resp.json()["detail"]

    def test_out_of_range_is_refused_not_clamped(self) -> None:
        """The `_coerce` this replaced silently clamped. Running for a month on a
        number nobody chose is worse than a rejection the operator can read."""
        resp = _client().put(
            "/api/v1/admin/settings/news_refresh_interval_minutes", json={"value": 1}
        )
        assert resp.status_code == 400, resp.text

    def test_a_rejection_carries_no_secret(self) -> None:
        """`ValidationError.errors()` embeds `input_value` for every field, and
        the candidate model we validate holds every credential this deployment
        has. Only `msg` may cross the wire — this is the test that says so."""
        from app.core.config import settings  # noqa: PLC0415

        resp = _client().put("/api/v1/admin/settings/escrow_mode", json={"value": "live"})
        assert resp.status_code == 400, resp.text
        body = resp.text
        for name in ("JWT_SECRET", "S3_SECRET_KEY", "VERIFICATION_ENC_KEY", "ANTHROPIC_API_KEY"):
            secret = str(getattr(settings, name))
            assert secret and secret not in body, f"{name} leaked into a 400 body"

    def test_a_rail_without_its_credential_is_refused_by_name(self) -> None:
        """The 31.08 incident, inverted. Turning the registry rail on without a
        token used to become a 503 that blamed Didox; now it is a 400 that names
        the token, at the moment the operator asked for it."""
        from tests.conftest import set_switch  # noqa: PLC0415

        set_switch(didox_partner_token="")
        resp = _client().put(
            "/api/v1/admin/settings/gov_registry_mode", json={"value": "didox"}
        )
        assert resp.status_code == 400, resp.text
        assert "DIDOX_PARTNER_TOKEN" in resp.json()["detail"]

    def test_a_sensitive_key_refuses_a_non_administrator(self) -> None:
        """A page grant says "may tune the platform". Replacing the Didox partner
        token is a different act, and delegating the first must not delegate it."""
        resp = _client(is_admin=False).put(
            "/api/v1/admin/settings/didox_partner_token", json={"value": "x"}
        )
        assert resp.status_code == 403, resp.text
        # Pin WHICH guard refused. This account HOLDS `appSettings:write`, so a
        # bare 403 assertion would also pass if the sensitive gate were deleted
        # and the page guard had merely denied the grant — the message is what
        # distinguishes the two, and it is the one under test.
        assert resp.json()["detail"] == "Access denied: administrator only", resp.text

    def test_reset_route_exists(self) -> None:
        resp = _client().delete("/api/v1/admin/settings/news_ai_enabled")
        assert resp.status_code == 200, resp.text

    def test_reset_of_an_unknown_key_is_404(self) -> None:
        resp = _client().delete("/api/v1/admin/settings/not_a_setting")
        assert resp.status_code == 404, resp.text


class TestSettingItemSchema:
    @pytest.mark.parametrize(
        ("value", "expected_type"),
        [(60, int), (True, bool), ("v3", str), (2.0, float), (None, type(None))],
    )
    def test_value_round_trips_its_type(self, value: object, expected_type: type) -> None:
        """Order matters in the union: bool before int so True does not become 1,
        int before float so 60 does not come back as 60.0."""
        from app.schemas.admin_settings import SettingItem  # noqa: PLC0415

        item = SettingItem.model_validate(_item(value=value, env_value=value))
        assert isinstance(item.value, expected_type), item.value
