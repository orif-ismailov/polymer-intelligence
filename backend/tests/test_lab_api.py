"""
Lab APIs — portal + dashboard (P6 W2 — T2.3/T2.4).

The route-registration checks run DB-free; everything else is guarded on a
localhost test_polymer.

What is worth an HTTP test rather than a service test:

  * **isolation** — a company must not see, or raise, an order about somebody
    else's offer, and the answer is 404 (not 403), so probing an id tells an
    outsider nothing;
  * **RBAC split** — an analyst RUNS the lab queue (it is their job), but the
    partner directory decides who we hand other people's material to, so writing
    to it is admin-only;
  * **the operator's error codes** — "409" alone tells someone holding a PDF
    nothing about what to do next;
  * **the seller's own passport upload**, which has to be a PDF, re-enters
    moderation, and cannot delete a result staff produced.
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

_PORTAL = "/api/v1/portal/companies"
_ADMIN = "/api/v1/admin"
_PDF = b"%PDF-1.4 laboratory passport"
_JPEG = b"\xff\xd8\xff\xe0 not a document"


def test_portal_lab_routes_registered() -> None:
    from app.api.portal.lab import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/companies/{company_id}/lab-orders" in paths
    assert "/portal/companies/{company_id}/lab-orders/{order_id}" in paths


def test_admin_lab_routes_registered() -> None:
    from app.api.admin_lab import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    for path in (
        "/admin/lab-orders",
        "/admin/lab-orders/{order_id}",
        "/admin/lab-orders/{order_id}/transition",
        "/admin/lab-orders/{order_id}/result",
        "/admin/lab-orders/{order_id}/partner",
        "/admin/lab-partners",
        "/admin/lab-partners/{partner_id}",
    ):
        assert path in paths


def test_the_customer_cannot_drive_the_status() -> None:
    """Statuses are staff's — nothing a customer could press makes a laboratory
    work faster, and a self-served `done` would forge a passport."""
    from app.api.portal.lab import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert not any("transition" in p or "result" in p for p in paths)


pytestmark_db = requires_real_db


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    from app.models.marketplace import SellerOfferFile  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415
    from tests._fake_redis import FakeRedis  # noqa: PLC0415

    def fake_offer_upload(db, offer_id, content, filename, kind):  # noqa: ANN001, ANN202
        mime = storage_service.validate_upload(content, filename)
        row = SellerOfferFile(
            offer_id=offer_id,
            kind=kind,
            file_name=filename,
            mime_type=mime,
            size_bytes=len(content),
            storage_path=f"offers/{offer_id}/x-{filename}",
        )
        db.add(row)
        db.flush()
        return row

    monkeypatch.setattr(storage_service, "upload_offer_file", fake_offer_upload)

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
    app.dependency_overrides[get_redis] = lambda: FakeRedis()
    from unittest.mock import patch  # noqa: PLC0415

    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _portal_auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


def _staff_auth(staff_id: int, role: str) -> dict[str, str]:
    from app.core.security import create_access_token  # noqa: PLC0415

    return {
        "Authorization": f"Bearer {create_access_token(subject=str(staff_id), role=role)}"
    }


def _seller_scene(session):  # noqa: ANN001, ANN202
    """A verified seller company with an approved offer, plus staff of both roles."""
    from app.models.enums import CompanyStatus, StaffRole  # noqa: PLC0415
    from app.models.staff import StaffUser  # noqa: PLC0415
    from tests._verification_db import make_company, make_seller_offer  # noqa: PLC0415

    with session() as db:
        owner = make_account(db, "+998900000301")
        company = make_company(db, owner, tax_id="300000301")
        company.status = CompanyStatus.verified
        offer = make_seller_offer(db, company=company, product_text="PP H030")
        analyst = StaffUser(
            email="analyst-lab@example.com",
            full_name="Analyst",
            role=StaffRole.analyst,
            password_hash="x",
        )
        admin = StaffUser(
            email="admin-lab2@example.com",
            full_name="Admin",
            role=StaffRole.admin,
            password_hash="x",
        )
        db.add_all([analyst, admin])
        db.commit()
        return {
            "account_id": owner.id,
            "company_id": company.id,
            "offer_id": offer.id,
            "analyst_id": analyst.id,
            "admin_id": admin.id,
        }


@pytestmark_db
class TestPortalLabOrders:
    def test_a_seller_raises_an_order_from_their_offer(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)

        response = client.post(
            f"{_PORTAL}/{scene['company_id']}/lab-orders",
            json={"offer_id": scene["offer_id"], "sample_volume": "2 кг"},
            headers=_portal_auth(scene["account_id"]),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "submitted"
        assert body["number"].startswith("LAB-")
        assert body["sample_volume"] == "2 кг"

    def test_neither_target_is_a_422(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        response = client.post(
            f"{_PORTAL}/{scene['company_id']}/lab-orders",
            json={"comment": "проверьте что-нибудь"},
            headers=_portal_auth(scene["account_id"]),
        )
        assert response.status_code == 422

    def test_both_targets_at_once_is_a_422(self, api) -> None:  # noqa: ANN001
        """Two places to put the passport and no rule for choosing."""
        client, session = api
        scene = _seller_scene(session)
        response = client.post(
            f"{_PORTAL}/{scene['company_id']}/lab-orders",
            json={"offer_id": scene["offer_id"], "deal_id": 1},
            headers=_portal_auth(scene["account_id"]),
        )
        assert response.status_code == 422

    def test_someone_elses_offer_is_a_404_not_a_403(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        from app.models.enums import CompanyStatus  # noqa: PLC0415
        from tests._verification_db import make_company  # noqa: PLC0415

        with session() as db:
            outsider = make_account(db, "+998900000302")
            outsider_company = make_company(db, outsider, tax_id="300000302")
            outsider_company.status = CompanyStatus.verified
            db.commit()
            outsider_id, outsider_company_id = outsider.id, outsider_company.id

        response = client.post(
            f"{_PORTAL}/{outsider_company_id}/lab-orders",
            json={"offer_id": scene["offer_id"]},
            headers=_portal_auth(outsider_id),
        )
        assert response.status_code == 404

    def test_a_non_member_sees_no_orders(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        with session() as db:
            stranger = make_account(db, "+998900000303")
            db.commit()
            stranger_id = stranger.id

        response = client.get(
            f"{_PORTAL}/{scene['company_id']}/lab-orders",
            headers=_portal_auth(stranger_id),
        )
        assert response.status_code == 404

    def test_the_list_is_the_companys_own(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        client.post(
            f"{_PORTAL}/{scene['company_id']}/lab-orders",
            json={"offer_id": scene["offer_id"]},
            headers=_portal_auth(scene["account_id"]),
        )
        response = client.get(
            f"{_PORTAL}/{scene['company_id']}/lab-orders",
            headers=_portal_auth(scene["account_id"]),
        )
        assert response.status_code == 200
        assert len(response.json()) == 1


@pytestmark_db
class TestAdminLabQueue:
    def _order(self, client, scene) -> int:  # noqa: ANN001
        response = client.post(
            f"{_PORTAL}/{scene['company_id']}/lab-orders",
            json={"offer_id": scene["offer_id"], "comment": "MFI"},
            headers=_portal_auth(scene["account_id"]),
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def test_an_analyst_runs_the_queue(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        order_id = self._order(client, scene)

        listing = client.get(
            f"{_ADMIN}/lab-orders", headers=_staff_auth(scene["analyst_id"], "analyst")
        )
        assert listing.status_code == 200, listing.text
        body = listing.json()
        assert body["counters"]["submitted"] == 1
        card = body["items"][0]
        assert card["id"] == order_id
        assert card["company_name"] is not None
        assert card["offer_title"] == "PP H030"
        # The dashboard builds its buttons from this, not from a TS copy of the
        # machine.
        assert card["available_transitions"] == ["accepted", "rejected"]

    def test_the_operator_walks_it_to_analysis(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        order_id = self._order(client, scene)
        headers = _staff_auth(scene["analyst_id"], "analyst")

        for target in ("accepted", "sample_awaited", "in_analysis"):
            response = client.post(
                f"{_ADMIN}/lab-orders/{order_id}/transition",
                json={"to_status": target},
                headers=headers,
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == target

    def test_skipping_a_step_is_409_invalid_transition(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        order_id = self._order(client, scene)
        response = client.post(
            f"{_ADMIN}/lab-orders/{order_id}/transition",
            json={"to_status": "in_analysis"},
            headers=_staff_auth(scene["analyst_id"], "analyst"),
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "invalid_transition"

    def test_rejecting_without_a_reason_is_422_reason_required(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        order_id = self._order(client, scene)
        response = client.post(
            f"{_ADMIN}/lab-orders/{order_id}/transition",
            json={"to_status": "rejected"},
            headers=_staff_auth(scene["analyst_id"], "analyst"),
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "reason_required"

    def test_done_by_hand_is_422_result_required(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        order_id = self._order(client, scene)
        headers = _staff_auth(scene["analyst_id"], "analyst")
        for target in ("accepted", "sample_awaited", "in_analysis"):
            client.post(
                f"{_ADMIN}/lab-orders/{order_id}/transition",
                json={"to_status": target},
                headers=headers,
            )
        response = client.post(
            f"{_ADMIN}/lab-orders/{order_id}/transition",
            json={"to_status": "done"},
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "result_required"

    def test_uploading_the_passport_finishes_it_and_verifies_the_offer(
        self, api
    ) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        order_id = self._order(client, scene)
        headers = _staff_auth(scene["analyst_id"], "analyst")
        for target in ("accepted", "sample_awaited", "in_analysis"):
            client.post(
                f"{_ADMIN}/lab-orders/{order_id}/transition",
                json={"to_status": target},
                headers=headers,
            )

        response = client.post(
            f"{_ADMIN}/lab-orders/{order_id}/result",
            files={"file": ("passport.pdf", _PDF, "application/pdf")},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "done"
        assert body["result_offer_file_id"] is not None
        assert body["available_transitions"] == []

        from app.models.marketplace import SellerOffer  # noqa: PLC0415

        with session() as db:
            offer = db.get(SellerOffer, scene["offer_id"])
            assert offer.lab_verified is True

    def test_a_jpeg_result_is_refused(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        order_id = self._order(client, scene)
        headers = _staff_auth(scene["analyst_id"], "analyst")
        for target in ("accepted", "sample_awaited", "in_analysis"):
            client.post(
                f"{_ADMIN}/lab-orders/{order_id}/transition",
                json={"to_status": target},
                headers=headers,
            )
        response = client.post(
            f"{_ADMIN}/lab-orders/{order_id}/result",
            files={"file": ("scan.jpg", _JPEG, "image/jpeg")},
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "invalid_file_type"


@pytestmark_db
class TestPartnerDirectoryRbac:
    def test_an_analyst_reads_the_directory_but_cannot_write_it(self, api) -> None:  # noqa: ANN001
        """Reading is needed to assign an order; deciding who we send other
        people's material to is an admin call."""
        client, session = api
        scene = _seller_scene(session)
        analyst = _staff_auth(scene["analyst_id"], "analyst")

        assert client.get(f"{_ADMIN}/lab-partners", headers=analyst).status_code == 200
        blocked = client.post(
            f"{_ADMIN}/lab-partners", json={"name": "ЦентрЛаб"}, headers=analyst
        )
        assert blocked.status_code == 403

    def test_an_admin_creates_and_retires_a_partner(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        admin = _staff_auth(scene["admin_id"], "admin")

        created = client.post(
            f"{_ADMIN}/lab-partners",
            json={"name": "ЦентрЛаб", "contacts": {"phone": "+998712000000"}},
            headers=admin,
        )
        assert created.status_code == 201, created.text
        partner_id = created.json()["id"]

        retired = client.post(
            f"{_ADMIN}/lab-partners/{partner_id}/deactivate", headers=admin
        )
        assert retired.status_code == 200
        assert retired.json()["is_active"] is False
        # Retired, not gone: a finished order still points at it.
        assert client.get(f"{_ADMIN}/lab-partners", headers=admin).json() != []

    def test_assigning_a_partner_shows_up_on_the_card(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        admin = _staff_auth(scene["admin_id"], "admin")
        partner_id = client.post(
            f"{_ADMIN}/lab-partners", json={"name": "ЦентрЛаб"}, headers=admin
        ).json()["id"]

        order_id = client.post(
            f"{_PORTAL}/{scene['company_id']}/lab-orders",
            json={"offer_id": scene["offer_id"]},
            headers=_portal_auth(scene["account_id"]),
        ).json()["id"]

        response = client.post(
            f"{_ADMIN}/lab-orders/{order_id}/partner",
            json={"lab_partner_id": partner_id},
            headers=admin,
        )
        assert response.status_code == 200
        assert response.json()["lab_partner_name"] == "ЦентрЛаб"
        # Assigning is not a status change.
        assert response.json()["status"] == "submitted"


@pytestmark_db
class TestSellerPassportUpload:
    def test_a_seller_uploads_their_own_passport_and_re_enters_moderation(
        self, api
    ) -> None:  # noqa: ANN001
        """The badge is public, so staff see it before buyers do — the same rule
        photos follow, and unlike an SDS, which only feeds the verdict."""
        client, session = api
        scene = _seller_scene(session)

        response = client.post(
            f"{_PORTAL}/{scene['company_id']}/offers/{scene['offer_id']}/files",
            data={"kind": "lab_passport"},
            files={"file": ("passport.pdf", _PDF, "application/pdf")},
            headers=_portal_auth(scene["account_id"]),
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "pending_moderation"

        from app.models.marketplace import SellerOffer  # noqa: PLC0415

        with session() as db:
            offer = db.get(SellerOffer, scene["offer_id"])
            assert offer.has_lab_passport is True
            # Uploading a PDF is not the same as having material analysed.
            assert offer.lab_verified is False

    def test_a_jpeg_passport_is_refused(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        response = client.post(
            f"{_PORTAL}/{scene['company_id']}/offers/{scene['offer_id']}/files",
            data={"kind": "lab_passport"},
            files={"file": ("passport.jpg", _JPEG, "image/jpeg")},
            headers=_portal_auth(scene["account_id"]),
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "invalid_file_type"

    def test_the_seller_cannot_delete_a_result_staff_produced(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        staff_headers = _staff_auth(scene["analyst_id"], "analyst")

        order_id = client.post(
            f"{_PORTAL}/{scene['company_id']}/lab-orders",
            json={"offer_id": scene["offer_id"]},
            headers=_portal_auth(scene["account_id"]),
        ).json()["id"]
        for target in ("accepted", "sample_awaited", "in_analysis"):
            client.post(
                f"{_ADMIN}/lab-orders/{order_id}/transition",
                json={"to_status": target},
                headers=staff_headers,
            )
        file_id = client.post(
            f"{_ADMIN}/lab-orders/{order_id}/result",
            files={"file": ("passport.pdf", _PDF, "application/pdf")},
            headers=staff_headers,
        ).json()["result_offer_file_id"]

        response = client.delete(
            f"{_PORTAL}/{scene['company_id']}/offers/{scene['offer_id']}/files/{file_id}",
            headers=_portal_auth(scene["account_id"]),
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "lab_result_locked"

    def test_deleting_a_self_uploaded_passport_drops_the_badge(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _seller_scene(session)
        headers = _portal_auth(scene["account_id"])

        uploaded = client.post(
            f"{_PORTAL}/{scene['company_id']}/offers/{scene['offer_id']}/files",
            data={"kind": "lab_passport"},
            files={"file": ("mine.pdf", _PDF, "application/pdf")},
            headers=headers,
        )
        file_id = uploaded.json()["files"][0]["id"]

        response = client.delete(
            f"{_PORTAL}/{scene['company_id']}/offers/{scene['offer_id']}/files/{file_id}",
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["files"] == []
