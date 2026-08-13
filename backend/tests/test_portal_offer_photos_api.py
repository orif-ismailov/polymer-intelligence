"""Portal offer-photo API tests (P1 W3 — T3.1).

The upload endpoint already existed; this pins the rules the plan adds on top:
the 8-image cap, images-only MIME for `kind=image`, deletion, the owner-scoped
byte endpoint (so a seller can see photos on a draft, which the public catalog
endpoint refuses), `files`/`cover_file_id` in the offer payload, and the
re-moderation rule when photos change on an approved offer.

Route registration is DB-free; behaviour runs against test_polymer (guarded).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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

_BASE = "/api/v1/portal/companies"

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_JPEG = b"\xff\xd8\xff" + b"\x00" * 64
_PDF = b"%PDF-1.4 not a picture"


def test_routes_registered() -> None:
    from app.domains.marketplace.api_portal import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/companies/{company_id}/offers/{offer_id}/files" in paths
    assert "/portal/companies/{company_id}/offers/{offer_id}/files/{file_id}" in paths


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    from tests._fake_redis import FakeRedis  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    fake_redis = FakeRedis()
    # Moderation notifications must not reach a broker.
    monkeypatch.setattr("app.domains.marketplace.service.enqueue_offer_group_notify", lambda *a, **k: None)
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


def _auth(session, phone: str) -> dict[str, str]:  # noqa: ANN001
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    with session() as db:
        account = make_account(db, phone)
        db.commit()
        account_id = account.id
    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


def _verified_company(session, client, auth: dict[str, str], tax_id: str) -> int:  # noqa: ANN001
    """A company must be verified before it may publish offers (R1 gate)."""
    from app.models.companies import Company  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    created = client.post(_BASE, json={"tax_id": tax_id}, headers=auth)
    assert created.status_code == 201, created.text
    company_id = int(created.json()["id"])
    with session() as db:
        from app.models.enums import CompanyBusinessRole  # noqa: PLC0415
        from app.services import company_service  # noqa: PLC0415

        company = db.get(Company, company_id)
        assert company is not None
        # distributor+trader: publishes offers — the role gates (T-B) require it
        company_service.set_business_roles(
            db, company, [CompanyBusinessRole.distributor, CompanyBusinessRole.trader]
        )
        company.status = CompanyStatus.verified
        db.commit()
    return company_id


def _offer(client, auth: dict[str, str], company_id: int) -> int:  # noqa: ANN001
    payload = {
        "product_text": "PP H030 GP",
        "availability": "in_stock",
        "qty_unit": "MT",
        "currency": "USD",
        "incoterms": "FCA",
    }
    res = client.post(f"{_BASE}/{company_id}/offers", json=payload, headers=auth)
    assert res.status_code == 201, res.text
    return int(res.json()["id"])


def _upload(client, auth, company_id: int, offer_id: int, content: bytes, name: str):  # noqa: ANN001, ANN201
    return client.post(
        f"{_BASE}/{company_id}/offers/{offer_id}/files",
        files={"file": (name, content, "image/png")},
        data={"kind": "image"},
        headers=auth,
    )


def _set_status(session, offer_id: int, status_value: str) -> None:  # noqa: ANN001
    from app.domains.marketplace.models import SellerOffer  # noqa: PLC0415
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415

    with session() as db:
        offer = db.get(SellerOffer, offer_id)
        assert offer is not None
        offer.status = SellerOfferStatus(status_value)
        db.commit()


# ── The 8-photo cap (FR-M2) ──────────────────────────────────────────────────


@requires_real_db
def test_eight_photos_allowed_ninth_rejected(api) -> None:  # noqa: ANN001
    client, session = api
    auth = _auth(session, "+998900000201")
    company_id = _verified_company(session, client, auth, "110000001")
    offer_id = _offer(client, auth, company_id)

    with patch("app.core.storage.s3_client", MagicMock()):
        for i in range(8):
            res = _upload(client, auth, company_id, offer_id, _PNG, f"p{i}.png")
            assert res.status_code == 201, f"photo {i}: {res.text}"

        ninth = _upload(client, auth, company_id, offer_id, _PNG, "p8.png")
    assert ninth.status_code == 422
    assert ninth.json()["detail"] == "too_many_files"


@requires_real_db
def test_the_cap_counts_images_only(api) -> None:  # noqa: ANN001
    """A TDS/certificate must not consume a photo slot."""
    client, session = api
    auth = _auth(session, "+998900000202")
    company_id = _verified_company(session, client, auth, "110000002")
    offer_id = _offer(client, auth, company_id)

    with patch("app.core.storage.s3_client", MagicMock()):
        for i in range(8):
            assert _upload(client, auth, company_id, offer_id, _PNG, f"p{i}.png").status_code == 201
        doc = client.post(
            f"{_BASE}/{company_id}/offers/{offer_id}/files",
            files={"file": ("spec.pdf", _PDF, "application/pdf")},
            data={"kind": "tds"},
            headers=auth,
        )
    assert doc.status_code == 201, doc.text


# ── kind=image means an image ────────────────────────────────────────────────


@requires_real_db
def test_pdf_rejected_for_image_kind(api) -> None:  # noqa: ANN001
    client, session = api
    auth = _auth(session, "+998900000203")
    company_id = _verified_company(session, client, auth, "110000003")
    offer_id = _offer(client, auth, company_id)

    fake_s3 = MagicMock()
    with patch("app.core.storage.s3_client", fake_s3):
        res = _upload(client, auth, company_id, offer_id, _PDF, "sneaky.png")
    assert res.status_code == 422
    assert res.json()["detail"] == "invalid_file_type"
    fake_s3.put_object.assert_not_called()


# ── Payload: files + cover (FR-M2/M3) ───────────────────────────────────────


@requires_real_db
def test_offer_payload_exposes_files_and_the_first_photo_as_cover(api) -> None:  # noqa: ANN001
    client, session = api
    auth = _auth(session, "+998900000204")
    company_id = _verified_company(session, client, auth, "110000004")
    offer_id = _offer(client, auth, company_id)

    with patch("app.core.storage.s3_client", MagicMock()):
        first = _upload(client, auth, company_id, offer_id, _PNG, "a.png").json()
        second = _upload(client, auth, company_id, offer_id, _JPEG, "b.jpg").json()

    ids = [f["id"] for f in second["files"]]
    # Order is upload order (id ASC) and the first photo is the cover.
    assert ids == sorted(ids)
    assert second["cover_file_id"] == first["files"][0]["id"]
    assert len(first["files"]) == 1


@requires_real_db
def test_cover_is_null_without_photos(api) -> None:  # noqa: ANN001
    client, session = api
    auth = _auth(session, "+998900000205")
    company_id = _verified_company(session, client, auth, "110000005")
    offer_id = _offer(client, auth, company_id)

    listed = client.get(f"{_BASE}/{company_id}/offers", headers=auth).json()
    mine = next(o for o in listed if o["id"] == offer_id)
    assert mine["cover_file_id"] is None
    assert mine["files"] == []


# ── Owner-scoped bytes: a draft's photos must be visible to its seller ───────


@requires_real_db
def test_owner_can_fetch_photo_bytes_on_a_draft(api) -> None:  # noqa: ANN001
    client, session = api
    auth = _auth(session, "+998900000206")
    company_id = _verified_company(session, client, auth, "110000006")
    offer_id = _offer(client, auth, company_id)

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": MagicMock(read=lambda: _PNG)}
    with patch("app.core.storage.s3_client", fake_s3):
        file_id = _upload(client, auth, company_id, offer_id, _PNG, "a.png").json()["files"][0]["id"]
        res = client.get(
            f"{_BASE}/{company_id}/offers/{offer_id}/files/{file_id}", headers=auth
        )
    assert res.status_code == 200
    assert res.content == _PNG
    assert res.headers["content-type"].startswith("image/")


@requires_real_db
def test_another_company_cannot_fetch_the_bytes(api) -> None:  # noqa: ANN001
    client, session = api
    owner_auth = _auth(session, "+998900000207")
    company_id = _verified_company(session, client, owner_auth, "110000007")
    offer_id = _offer(client, owner_auth, company_id)
    outsider_auth = _auth(session, "+998900000208")

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": MagicMock(read=lambda: _PNG)}
    with patch("app.core.storage.s3_client", fake_s3):
        file_id = _upload(client, owner_auth, company_id, offer_id, _PNG, "a.png").json()["files"][0]["id"]
        res = client.get(
            f"{_BASE}/{company_id}/offers/{offer_id}/files/{file_id}", headers=outsider_auth
        )
    assert res.status_code == 404


# ── Delete ───────────────────────────────────────────────────────────────────


@requires_real_db
def test_delete_photo_removes_it_and_moves_the_cover(api) -> None:  # noqa: ANN001
    client, session = api
    auth = _auth(session, "+998900000209")
    company_id = _verified_company(session, client, auth, "110000008")
    offer_id = _offer(client, auth, company_id)

    fake_s3 = MagicMock()
    with patch("app.core.storage.s3_client", fake_s3):
        first_id = _upload(client, auth, company_id, offer_id, _PNG, "a.png").json()["files"][0]["id"]
        body = _upload(client, auth, company_id, offer_id, _JPEG, "b.jpg").json()
        second_id = [f["id"] for f in body["files"] if f["id"] != first_id][0]
        assert body["cover_file_id"] == first_id

        deleted = client.delete(
            f"{_BASE}/{company_id}/offers/{offer_id}/files/{first_id}", headers=auth
        )
        assert deleted.status_code == 200, deleted.text
        # Removing the cover promotes the next photo.
        assert deleted.json()["cover_file_id"] == second_id
        assert [f["id"] for f in deleted.json()["files"]] == [second_id]
    fake_s3.delete_object.assert_called()


@requires_real_db
def test_deleting_an_unknown_file_is_404(api) -> None:  # noqa: ANN001
    client, session = api
    auth = _auth(session, "+998900000210")
    company_id = _verified_company(session, client, auth, "110000009")
    offer_id = _offer(client, auth, company_id)

    res = client.delete(f"{_BASE}/{company_id}/offers/{offer_id}/files/999999", headers=auth)
    assert res.status_code == 404


# ── Re-moderation when photos change on a live offer (FR-M2) ────────────────


@requires_real_db
def test_adding_a_photo_to_an_approved_offer_requeues_moderation(api) -> None:  # noqa: ANN001
    client, session = api
    auth = _auth(session, "+998900000211")
    company_id = _verified_company(session, client, auth, "110000010")
    offer_id = _offer(client, auth, company_id)
    _set_status(session, offer_id, "approved")

    with patch("app.core.storage.s3_client", MagicMock()):
        res = _upload(client, auth, company_id, offer_id, _PNG, "new.png")
    assert res.status_code == 201
    assert res.json()["status"] == "pending_moderation"


@requires_real_db
def test_deleting_a_photo_from_an_approved_offer_requeues_moderation(api) -> None:  # noqa: ANN001
    client, session = api
    auth = _auth(session, "+998900000212")
    company_id = _verified_company(session, client, auth, "110000011")
    offer_id = _offer(client, auth, company_id)

    with patch("app.core.storage.s3_client", MagicMock()):
        file_id = _upload(client, auth, company_id, offer_id, _PNG, "a.png").json()["files"][0]["id"]
        _set_status(session, offer_id, "approved")
        res = client.delete(
            f"{_BASE}/{company_id}/offers/{offer_id}/files/{file_id}", headers=auth
        )
    assert res.status_code == 200
    assert res.json()["status"] == "pending_moderation"


@requires_real_db
def test_photo_change_before_approval_does_not_touch_status(api) -> None:  # noqa: ANN001
    """Only an approved/rejected offer is requeued; a fresh one keeps its status."""
    client, session = api
    auth = _auth(session, "+998900000213")
    company_id = _verified_company(session, client, auth, "110000012")
    offer_id = _offer(client, auth, company_id)

    before = next(
        o for o in client.get(f"{_BASE}/{company_id}/offers", headers=auth).json()
        if o["id"] == offer_id
    )["status"]

    with patch("app.core.storage.s3_client", MagicMock()):
        body = _upload(client, auth, company_id, offer_id, _PNG, "a.png").json()
    assert body["status"] == before


@requires_real_db
def test_requeue_is_audited(api) -> None:  # noqa: ANN001
    client, session = api
    auth = _auth(session, "+998900000214")
    company_id = _verified_company(session, client, auth, "110000013")
    offer_id = _offer(client, auth, company_id)
    _set_status(session, offer_id, "approved")

    with patch("app.core.storage.s3_client", MagicMock()):
        _upload(client, auth, company_id, offer_id, _PNG, "a.png")

    from app.models.staff import AuditLog  # noqa: PLC0415

    with session() as db:
        actions = [
            row.action
            for row in db.query(AuditLog)
            .filter(AuditLog.entity == "seller_offers", AuditLog.entity_id == str(offer_id))
            .all()
        ]
    assert "offer.photos_changed" in actions
