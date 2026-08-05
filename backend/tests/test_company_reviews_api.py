"""Company reviews — eligibility, the aggregate, and what a stranger may read.

There is no moderation queue by design (see migration 0036), so eligibility is
the only thing standing between this and a spam surface. That is what this suite
is mostly about.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)

_PORTAL = "/api/v1/portal/companies"
_PUBLIC = "/api/v1/public"


def test_review_route_registered() -> None:
    from app.api.portal.companies import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/portal/companies/{company_id}/reviews" in paths


def test_public_review_never_names_the_person() -> None:
    """A review is a COMPANY's position.

    `author_account_id` is on the row for audit. Serialising it would both
    misattribute the opinion and make every reviewer's identity scrapable.
    """
    from app.schemas.public import PublicReviewOut  # noqa: PLC0415

    fields = set(PublicReviewOut.model_fields)
    assert "author_account_id" not in fields
    assert "author_company_id" not in fields
    assert {"rating", "body", "author_company_name"} <= fields


def test_review_status_has_no_pending_state() -> None:
    """Reviews publish immediately; `hidden` is a takedown, not a queue.

    Pinned because re-adding `pending` as the default would produce a review
    system whose visible state is the empty list the tab already renders — a
    regression that looks like "no reviews yet" rather than like a bug.
    """
    from app.models.enums import CompanyReviewStatus  # noqa: PLC0415

    assert {m.value for m in CompanyReviewStatus} == {"published", "hidden"}


# ── real-DB API fixture ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
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


def _verified(db, owner, tax_id: str, name: str, *, role=None):  # noqa: ANN001, ANN202
    from app.models.companies import CompanyBusinessRole  # noqa: PLC0415
    from app.models.enums import BusinessRoleStatus, CompanyStatus  # noqa: PLC0415
    from app.models.enums import CompanyBusinessRole as Role  # noqa: PLC0415

    company = make_company(
        db, owner, tax_id=tax_id, legal_name=name, status=CompanyStatus.verified
    )
    db.add(
        CompanyBusinessRole(
            company_id=company.id,
            role=role or Role.trader,
            status=BusinessRoleStatus.confirmed,
        )
    )
    return company


@requires_real_db
def test_review_publishes_immediately_and_drives_the_aggregate(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        subject_owner = make_account(db, "+998900009001")
        subject = _verified(db, subject_owner, "390000001", "Trans Asia Logistics")
        a_owner = make_account(db, "+998900009002")
        author_a = _verified(db, a_owner, "390000002", "Shurtan GCC")
        b_owner = make_account(db, "+998900009003")
        author_b = _verified(db, b_owner, "390000003", "Silk Road Polymers")
        db.commit()
        subject_id = subject.id
        a_id, a_account = author_a.id, a_owner.id
        b_id, b_account = author_b.id, b_owner.id

    first = client.post(
        f"{_PORTAL}/{subject_id}/reviews",
        json={"company_id": a_id, "rating": 5, "body": "Всё вовремя."},
        headers=_auth(a_account),
    )
    assert first.status_code == 201
    # No queue: it is readable by a stranger on the next request.
    assert first.json()["status"] == "published"

    client.post(
        f"{_PORTAL}/{subject_id}/reviews",
        json={"company_id": b_id, "rating": 4, "body": None},
        headers=_auth(b_account),
    )

    detail = client.get(f"{_PUBLIC}/directories/traders/{subject_id}").json()
    assert detail["review_count"] == 2
    assert detail["rating"] == 4.5
    assert {r["author_company_name"] for r in detail["reviews"]} == {
        "Shurtan GCC",
        "Silk Road Polymers",
    }
    # The person is never named.
    assert "author_account_id" not in str(detail)

    row = client.get(f"{_PUBLIC}/directories/traders").json()["items"]
    subject_row = next(i for i in row if i["id"] == subject_id)
    assert subject_row["review_count"] == 2
    assert subject_row["rating"] == 4.5


@requires_real_db
def test_a_company_with_no_reviews_reports_null_not_zero(api) -> None:  # noqa: ANN001
    """«нет отзывов» and «оценка 0» are different sentences.

    A zero would render as a one-star company on every card in the directory.
    """
    client, session = api
    with session() as db:
        owner = make_account(db, "+998900009011")
        company = _verified(db, owner, "390000011", "Unrated Trading")
        db.commit()
        company_id = company.id

    detail = client.get(f"{_PUBLIC}/directories/traders/{company_id}").json()
    assert detail["rating"] is None
    assert detail["review_count"] == 0
    assert detail["reviews"] == []


@requires_real_db
def test_second_review_replaces_the_first(api) -> None:  # noqa: ANN001
    """A review is a standing opinion per counterparty, not an event log."""
    client, session = api
    with session() as db:
        subject_owner = make_account(db, "+998900009021")
        subject = _verified(db, subject_owner, "390000021", "Subject Co")
        author_owner = make_account(db, "+998900009022")
        author = _verified(db, author_owner, "390000022", "Author Co")
        db.commit()
        subject_id, author_id, account_id = subject.id, author.id, author_owner.id

    client.post(
        f"{_PORTAL}/{subject_id}/reviews",
        json={"company_id": author_id, "rating": 2, "body": "Задержали."},
        headers=_auth(account_id),
    )
    client.post(
        f"{_PORTAL}/{subject_id}/reviews",
        json={"company_id": author_id, "rating": 5, "body": "Исправились."},
        headers=_auth(account_id),
    )

    detail = client.get(f"{_PUBLIC}/directories/traders/{subject_id}").json()
    assert detail["review_count"] == 1
    assert detail["rating"] == 5.0
    assert detail["reviews"][0]["body"] == "Исправились."


@requires_real_db
def test_self_review_and_unverified_subject_are_refused(api) -> None:  # noqa: ANN001
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    client, session = api
    with session() as db:
        owner = make_account(db, "+998900009031")
        own = _verified(db, owner, "390000031", "Own Co")
        draft_owner = make_account(db, "+998900009032")
        draft = make_company(
            db, draft_owner, tax_id="390000032", status=CompanyStatus.draft
        )
        db.commit()
        own_id, account_id, draft_id = own.id, owner.id, draft.id

    same = client.post(
        f"{_PORTAL}/{own_id}/reviews",
        json={"company_id": own_id, "rating": 5, "body": None},
        headers=_auth(account_id),
    )
    assert same.status_code == 422
    assert same.json()["detail"] == "self_review"

    assert (
        client.post(
            f"{_PORTAL}/{draft_id}/reviews",
            json={"company_id": own_id, "rating": 5, "body": None},
            headers=_auth(account_id),
        ).status_code
        == 404
    )


@requires_real_db
def test_review_requires_membership_and_a_session(api) -> None:  # noqa: ANN001
    client, session = api
    with session() as db:
        subject_owner = make_account(db, "+998900009041")
        subject = _verified(db, subject_owner, "390000041", "Subject Co")
        author_owner = make_account(db, "+998900009042")
        author = _verified(db, author_owner, "390000042", "Author Co")
        stranger = make_account(db, "+998900009043")
        db.commit()
        subject_id, author_id, stranger_id = subject.id, author.id, stranger.id

    assert (
        client.post(
            f"{_PORTAL}/{subject_id}/reviews", json={"company_id": author_id, "rating": 5}
        ).status_code
        == 401
    )
    # A real account claiming a company it does not belong to.
    assert (
        client.post(
            f"{_PORTAL}/{subject_id}/reviews",
            json={"company_id": author_id, "rating": 5},
            headers=_auth(stranger_id),
        ).status_code
        == 404
    )


@requires_real_db
def test_hidden_reviews_leave_the_aggregate_and_the_list(api) -> None:  # noqa: ANN001
    """`hidden` is the takedown path — and it must move the score, not just the list."""
    from app.models.enums import CompanyReviewStatus  # noqa: PLC0415
    from app.models.reviews import CompanyReview  # noqa: PLC0415

    client, session = api
    with session() as db:
        subject_owner = make_account(db, "+998900009051")
        subject = _verified(db, subject_owner, "390000051", "Subject Co")
        author_owner = make_account(db, "+998900009052")
        author = _verified(db, author_owner, "390000052", "Author Co")
        db.commit()
        subject_id, author_id, account_id = subject.id, author.id, author_owner.id

    client.post(
        f"{_PORTAL}/{subject_id}/reviews",
        json={"company_id": author_id, "rating": 1, "body": "спам"},
        headers=_auth(account_id),
    )

    with session() as db:
        review = db.query(CompanyReview).one()
        review.status = CompanyReviewStatus.hidden
        db.commit()

    detail = client.get(f"{_PUBLIC}/directories/traders/{subject_id}").json()
    assert detail["reviews"] == []
    assert detail["review_count"] == 0
    assert detail["rating"] is None
