"""Staff moderation of technologists: the page grant gates it, the queue works.

Reading needs the `technologists` page at `read`; deciding needs `write`.
Absence of a grant denies — a page added to the catalog is closed by default.
"""

from __future__ import annotations

from unittest.mock import patch

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

_BASE = "/api/v1/admin/technologists"


def test_the_page_is_in_the_catalog() -> None:
    from app.core.pages import PAGES  # noqa: PLC0415

    assert any(p.key == "technologists" and p.group == "counterparties" for p in PAGES)


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def setup(engine: sa.Engine):  # noqa: ANN201
    """(client_for(grant), profile_id) — a submitted expert and a staff member
    whose grant each test chooses."""
    from app.api.deps import get_current_staff_user  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.domains.technologists import profiles  # noqa: PLC0415
    from app.domains.technologists.schemas import TechnologistProfileIn  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    from app.models.staff import StaffPageAccess, StaffUser  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    with session() as db:
        staff = StaffUser(email="mod@example.com", full_name="Mod", is_admin=False, password_hash="x")
        db.add(staff)
        expert = make_account(db, "+998900030001")
        expert.applied_as = "technologist"
        db.flush()
        profile = profiles.update_own(
            db,
            expert,
            TechnologistProfileIn(
                full_name="Ivan Petrov",
                title="Polymer processing",
                country="DE",
                years_experience=18,
                processes=["film"],
                languages=["en"],
                work_formats=["online"],
            ),
        )
        profiles.submit_own(db, expert)
        db.commit()
        staff_id, profile_id = staff.id, profile.id

    def client_for(level: str | None) -> TestClient:
        with session() as db:
            db.execute(sa.delete(StaffPageAccess))
            if level:
                db.add(StaffPageAccess(staff_user_id=staff_id, page="technologists", access=level))
            db.commit()
        app = create_app()

        def _override_db():  # noqa: ANN202
            db = session()
            try:
                yield db
            finally:
                db.close()

        def _staff() -> StaffUser:
            with session() as db:
                return db.get(StaffUser, staff_id)  # type: ignore[return-value]

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_staff_user] = _staff
        return TestClient(app)

    with patch("app.api.health._check_redis", return_value="ok"):
        yield client_for, profile_id
    clean(engine)


@requires_real_db
def test_no_grant_denies(setup) -> None:  # noqa: ANN001
    client_for, _pid = setup
    assert client_for(None).get(_BASE).status_code == 403


@requires_real_db
def test_a_reader_sees_the_queue_but_cannot_decide(setup) -> None:  # noqa: ANN001
    client_for, pid = setup
    client = client_for("read")
    queue = client.get(_BASE, params={"status": "pending_review"})
    assert queue.status_code == 200
    assert [p["id"] for p in queue.json()] == [pid]
    assert client.post(f"{_BASE}/{pid}/approve").status_code == 403


@requires_real_db
def test_a_writer_approves_and_the_expert_is_listed(setup) -> None:  # noqa: ANN001
    client_for, pid = setup
    client = client_for("write")
    resp = client.post(f"{_BASE}/{pid}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"
    assert resp.json()["is_listed"] is True
    assert client.post(f"{_BASE}/{pid}/approve").status_code == 409


@requires_real_db
def test_reject_needs_a_reason(setup) -> None:  # noqa: ANN001
    client_for, pid = setup
    client = client_for("write")
    assert client.post(f"{_BASE}/{pid}/reject", json={"reason": "  "}).status_code == 422
    resp = client.post(f"{_BASE}/{pid}/reject", json={"reason": "Нет подтверждения опыта"})
    assert resp.status_code == 200
    assert resp.json()["rejection_reason"] == "Нет подтверждения опыта"
