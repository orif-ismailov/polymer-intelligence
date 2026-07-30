"""
Substance registry API: admin CRUD + portal picker (P5 W2 — T2.3/T2.4).

Route registration and schema rules are DB-free; behaviour runs against
test_polymer (guarded).

The schema rules are the interesting half. A registry row is what a publish gate
reasons over, so three shapes are rejected at write time rather than producing a
verdict nobody can act on:

  * a regulated substance with no regime — which act catches it, and whose
    licence would satisfy it?
  * `docs_required` with an empty document list — a gate that demands nothing;
  * a document kind that is not an offer file kind — the verdict would look for
    files that can never be uploaded.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    make_staff,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

_A = "/api/v1/admin"
_P = "/api/v1/portal"


def test_admin_routes_registered() -> None:
    from app.api.admin_substances import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/admin/substances" in paths
    assert "/admin/substances/{substance_id}" in paths


def test_portal_route_registered() -> None:
    from app.api.portal.substances import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/substances" in paths


def test_the_registry_is_never_deleted_from_the_api() -> None:
    """Offers point at substances and a blocked offer's history has to stay
    explainable, so the admin deactivates instead of deleting."""
    from app.api.admin_substances import router  # noqa: PLC0415

    methods = {m for r in router.routes for m in r.methods}  # type: ignore[attr-defined]
    assert "DELETE" not in methods


class TestSchemaRules:
    def test_a_regulated_substance_needs_a_regime(self) -> None:
        from app.models.enums import RegulationLevel  # noqa: PLC0415
        from app.schemas.substance import SubstanceIn  # noqa: PLC0415

        with pytest.raises(ValidationError, match="regulation_regime"):
            SubstanceIn(
                code="acetone",
                name_ru="Ацетон",
                hs_code="2914.11",
                regulation_level=RegulationLevel.license_required,
            )

    def test_free_substances_need_no_regime(self) -> None:
        from app.schemas.substance import SubstanceIn  # noqa: PLC0415

        row = SubstanceIn(code="pp", name_ru="Полипропилен", hs_code="3902")
        assert row.regulation_regime is None

    def test_docs_required_must_name_the_documents(self) -> None:
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415
        from app.schemas.substance import SubstanceIn  # noqa: PLC0415

        with pytest.raises(ValidationError, match="required_docs"):
            SubstanceIn(
                code="waste",
                name_ru="Отходы пластмасс",
                hs_code="3915",
                regulation_level=RegulationLevel.docs_required,
                regulation_regime=RegulationRegime.pkm916_import,
                required_docs=[],
            )

    def test_required_docs_must_be_uploadable_kinds(self) -> None:
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415
        from app.schemas.substance import SubstanceIn  # noqa: PLC0415

        with pytest.raises(ValidationError):
            SubstanceIn(
                code="waste",
                name_ru="Отходы пластмасс",
                hs_code="3915",
                regulation_level=RegulationLevel.docs_required,
                regulation_regime=RegulationRegime.pkm916_import,
                required_docs=["passport_of_quality"],
            )

    def test_a_photo_is_not_a_compliance_document(self) -> None:
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415
        from app.schemas.substance import SubstanceIn  # noqa: PLC0415

        with pytest.raises(ValidationError):
            SubstanceIn(
                code="waste",
                name_ru="Отходы пластмасс",
                hs_code="3915",
                regulation_level=RegulationLevel.docs_required,
                regulation_regime=RegulationRegime.pkm916_import,
                required_docs=["image"],
            )


# ── Behaviour (guarded) ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN001, ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM substances"))
    session = session_factory(engine)
    fake_redis = FakeRedis()
    app = create_app()

    def _override_db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    def _override_redis():  # noqa: ANN202
        yield fake_redis

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _staff_headers(session, role="admin", email="admin@example.com"):  # noqa: ANN001, ANN202
    from app.core.security import create_access_token  # noqa: PLC0415
    from app.models.enums import StaffRole  # noqa: PLC0415

    with session() as db:
        staff = make_staff(db, email)
        staff.role = StaffRole(role)
        db.commit()
        staff_id = staff.id
    return {"Authorization": f"Bearer {create_access_token(subject=str(staff_id), role=role)}"}


def _account_headers(session, phone="+998900000009"):  # noqa: ANN001, ANN202
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    with session() as db:
        account = make_account(db, phone)
        db.commit()
        account_id = account.id
    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


_ACETONE = {
    "code": "acetone",
    "name_ru": "Ацетон",
    "name_en": "Acetone",
    "hs_code": "2914.11",
    "cas": "67-64-1",
    "regulation_level": "license_required",
    "regulation_regime": "precursor_list_iv",
    "threshold_concentration_pct": "60.00",
    "synonyms": ["Диметилкетон", "propanone"],
    "source_act": "ПКМ №330 от 12.11.2015, Список IV",
}


@requires_real_db
class TestAdminCrud:
    def test_admin_creates_and_lists(self, api) -> None:  # noqa: ANN001
        client, session = api
        headers = _staff_headers(session)

        created = client.post(f"{_A}/substances", json=_ACETONE, headers=headers)
        assert created.status_code == 201, created.text
        assert created.json()["code"] == "acetone"

        listed = client.get(f"{_A}/substances", headers=headers)
        assert [s["code"] for s in listed.json()] == ["acetone"]

    def test_analyst_may_watch_but_not_write(self, api) -> None:  # noqa: ANN001
        """The registry decides what may be sold; editing it is an admin act."""
        client, session = api
        analyst = _staff_headers(session, "analyst", "analyst@example.com")

        assert client.get(f"{_A}/substances", headers=analyst).status_code == 200
        assert client.post(f"{_A}/substances", json=_ACETONE, headers=analyst).status_code == 403

    def test_anonymous_is_rejected(self, api) -> None:  # noqa: ANN001
        client, _ = api
        assert client.get(f"{_A}/substances").status_code in (401, 403)

    def test_duplicate_code_is_a_409(self, api) -> None:  # noqa: ANN001
        client, session = api
        headers = _staff_headers(session)
        client.post(f"{_A}/substances", json=_ACETONE, headers=headers)
        again = client.post(f"{_A}/substances", json=_ACETONE, headers=headers)
        assert again.status_code == 409
        assert again.json()["detail"] == "substance_exists"

    def test_patch_edits_and_deactivate_hides(self, api) -> None:  # noqa: ANN001
        client, session = api
        headers = _staff_headers(session)
        substance_id = client.post(f"{_A}/substances", json=_ACETONE, headers=headers).json()["id"]

        patched = client.patch(
            f"{_A}/substances/{substance_id}",
            json={**_ACETONE, "threshold_concentration_pct": "65.00"},
            headers=headers,
        )
        assert patched.status_code == 200
        assert patched.json()["threshold_concentration_pct"] == "65.00"

        off = client.post(
            f"{_A}/substances/{substance_id}/deactivate", headers=headers
        )
        assert off.status_code == 200
        assert off.json()["is_active"] is False
        # Still listed for staff (with the flag), gone from the seller's picker.
        assert client.get(f"{_A}/substances", headers=headers).json()[0]["is_active"] is False


@requires_real_db
class TestPortalPicker:
    def test_search_needs_an_account(self, api) -> None:  # noqa: ANN001
        client, _ = api
        assert client.get(f"{_P}/substances", params={"q": "ацет"}).status_code in (401, 403)

    def test_search_returns_what_publishing_will_require(self, api) -> None:  # noqa: ANN001
        """The picker shows the level up front so a seller learns about a licence
        before filling in the whole form, not at the 409."""
        client, session = api
        admin = _staff_headers(session)
        client.post(f"{_A}/substances", json=_ACETONE, headers=admin)

        found = client.get(
            f"{_P}/substances", params={"q": "propanone"}, headers=_account_headers(session)
        )
        assert found.status_code == 200
        body = found.json()
        assert len(body) == 1
        assert body[0]["code"] == "acetone"
        assert body[0]["regulation_level"] == "license_required"
        assert body[0]["threshold_concentration_pct"] == "60.00"

    def test_deactivated_substances_are_not_offered(self, api) -> None:  # noqa: ANN001
        client, session = api
        admin = _staff_headers(session)
        substance_id = client.post(f"{_A}/substances", json=_ACETONE, headers=admin).json()["id"]
        client.post(f"{_A}/substances/{substance_id}/deactivate", headers=admin)

        found = client.get(
            f"{_P}/substances", params={"q": "ацетон"}, headers=_account_headers(session)
        )
        assert found.json() == []
