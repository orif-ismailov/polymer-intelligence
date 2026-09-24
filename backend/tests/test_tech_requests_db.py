"""Real-Postgres tests for the technologist marketplace's request lifecycle.

A verified factory posts; every listed expert sees it (the factory anonymised
until a thread exists); experts offer and talk; the factory accepts one — which
declines the rest and reveals both sides' contacts — then completes it with a
review that feeds the expert's rating.
"""

from __future__ import annotations

import decimal

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_staff,
    migrate_head,
    requires_real_db,
    session_factory,
)


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


_PROFILE = {
    "full_name": "Акмаль Каримов",
    "title": "Технолог экструзии",
    "country": "UZ",
    "years_experience": 12,
    "processes": ["film", "extrusion"],
    "languages": ["ru"],
    "work_formats": ["on_site"],
    "contact_phone": "+998901112233",
}

_REQUEST = {
    "need_type": "material_selection",
    "process": "film",
    "equipment": "Экструзионная линия",
    "product": "PE плёнка",
    "current_material": "LLDPE C4",
    "problem": "Хотим заменить сырьё на более дешёвое",
    "capacity": "400",
    "capacity_unit": "kg_h",
    "country": "UZ",
    "city": "Ташкент",
    "urgency": "week",
    "work_format": "on_site",
    "languages": ["ru"],
}

_OFFER = {
    "scope": "2 дня консультации + 1 день на заводе",
    "price": "1500",
    "currency": "USD",
    "duration_days": 3,
    "work_format": "on_site",
}


def _factory(db, *, verified=True, tax="301000001", phone="+998900000301"):  # noqa: ANN001, ANN202
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    owner = make_account(db, phone)
    company = make_company(db, owner, tax_id=tax, legal_name="ООО Плёнка")
    if verified:
        company.status = CompanyStatus.verified
    db.flush()
    return owner, company


def _expert(db, staff, phone="+998900000311", **overrides):  # noqa: ANN001, ANN003, ANN202
    from app.domains.technologists import profiles  # noqa: PLC0415
    from app.domains.technologists.schemas import TechnologistProfileIn  # noqa: PLC0415

    account = make_account(db, phone)
    account.applied_as = "technologist"
    db.flush()
    profile = profiles.update_own(db, account, TechnologistProfileIn(**{**_PROFILE, **overrides}))
    profiles.submit_own(db, account)
    profiles.approve(db, profile, staff.id)
    return account, profile


def _post(db, owner, company, **overrides):  # noqa: ANN001, ANN003, ANN202
    from app.domains.technologists import requests as svc  # noqa: PLC0415
    from app.domains.technologists.schemas import TechRequestIn  # noqa: PLC0415

    return svc.create_request(
        db, company=company, account=owner, data=TechRequestIn(**{**_REQUEST, **overrides})
    )


def _offer(db, request, profile, **overrides):  # noqa: ANN001, ANN003, ANN202
    from app.domains.technologists import requests as svc  # noqa: PLC0415
    from app.domains.technologists.schemas import TechOfferIn  # noqa: PLC0415

    return svc.submit_offer(db, request, profile, TechOfferIn(**{**_OFFER, **overrides}))


@requires_real_db
def test_an_unverified_company_cannot_post(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import requests as svc  # noqa: PLC0415

    with sf() as db:
        owner, company = _factory(db, verified=False)
        with pytest.raises(svc.CompanyNotVerified):
            _post(db, owner, company)


@requires_real_db
def test_numbering(sf) -> None:  # noqa: ANN001
    with sf() as db:
        owner, company = _factory(db)
        first = _post(db, owner, company)
        second = _post(db, owner, company)
        assert first.number.startswith("IMX-TECH-")
        assert int(second.number.rsplit("-", 1)[1]) == int(first.number.rsplit("-", 1)[1]) + 1


@requires_real_db
def test_posting_notifies_experts_of_that_process_only(sf) -> None:  # noqa: ANN001
    from app.domains.notifications.models import PortalNotification  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        film_acc, _ = _expert(db, staff)
        mold_acc, _ = _expert(db, staff, "+998900000312", processes=["injection_molding"])
        owner, company = _factory(db)
        _post(db, owner, company)
        notified = {
            n.user_account_id
            for n in db.query(PortalNotification).filter_by(kind="tech_request_new")
        }
        assert notified == {film_acc.id}
        assert mold_acc.id not in notified


@requires_real_db
def test_the_feed_is_open_requests_and_anonymous_until_a_thread(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import requests as svc  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        _acc, profile = _expert(db, staff)
        owner, company = _factory(db)
        open_request = _post(db, owner, company)
        cancelled = _post(db, owner, company)
        svc.cancel_request(db, cancelled, owner)

        feed = svc.feed_for(db, profile)
        assert [r.id for r in feed] == [open_request.id]
        assert svc.company_visible_to(db, open_request, profile) is False

        svc.open_thread(db, open_request, profile)
        assert svc.company_visible_to(db, open_request, profile) is True


@requires_real_db
def test_an_unlisted_expert_sees_nothing(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import profiles  # noqa: PLC0415
    from app.domains.technologists import requests as svc  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        _acc, profile = _expert(db, staff)
        owner, company = _factory(db)
        request = _post(db, owner, company)
        profiles.suspend(db, profile, staff.id, "жалобы")
        assert svc.feed_for(db, profile) == []
        with pytest.raises(svc.TechRequestNotFound):
            svc.get_for_expert(db, profile, request.id)
        with pytest.raises(svc.InvalidTechTransition):
            _offer(db, request, profile)


@requires_real_db
def test_one_active_offer_withdraw_and_offer_again(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import requests as svc  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        _acc, profile = _expert(db, staff)
        owner, company = _factory(db)
        request = _post(db, owner, company)

        offer = _offer(db, request, profile)
        assert svc.thread_for(db, request.id, profile.id) is not None, "an offer opens the thread"
        with pytest.raises(svc.OfferConflict):
            _offer(db, request, profile)
        svc.withdraw_offer(db, offer, profile)
        assert offer.status == "withdrawn"
        again = _offer(db, request, profile, price="1200")
        assert again.status == "submitted"


@requires_real_db
def test_accepting_declines_the_rest_and_reveals_contacts(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import requests as svc  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        _a1, winner = _expert(db, staff)
        _a2, loser = _expert(db, staff, "+998900000312")
        owner, company = _factory(db)
        request = _post(db, owner, company)
        chosen = _offer(db, request, winner)
        other = _offer(db, request, loser)

        assert not svc.contacts_visible(request, winner.id)
        svc.accept_offer(db, request, chosen, owner)

        assert request.status == "assigned"
        assert request.assigned_offer_id == chosen.id
        assert chosen.status == "accepted"
        assert other.status == "declined"
        assert svc.contacts_visible(request, winner.id)
        assert not svc.contacts_visible(request, loser.id)
        with pytest.raises(svc.InvalidTechTransition):
            _offer(db, request, loser)


@requires_real_db
def test_an_offer_on_someone_elses_request_is_not_acceptable(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import requests as svc  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        _a, profile = _expert(db, staff)
        owner, company = _factory(db)
        mine = _post(db, owner, company)
        theirs = _post(db, owner, company)
        offer = _offer(db, theirs, profile)
        with pytest.raises(svc.TechRequestNotFound):
            svc.accept_offer(db, mine, offer, owner)


@requires_real_db
def test_completion_needs_an_assignment_and_feeds_the_rating(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import requests as svc  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        _a, profile = _expert(db, staff)
        owner, company = _factory(db)

        first = _post(db, owner, company)
        with pytest.raises(svc.InvalidTechTransition):
            svc.complete(db, first, owner, rating=5, text=None)
        svc.accept_offer(db, first, _offer(db, first, profile), owner)
        svc.complete(db, first, owner, rating=5, text="Отлично")

        second = _post(db, owner, company)
        svc.accept_offer(db, second, _offer(db, second, profile), owner)
        svc.complete(db, second, owner, rating=4, text=None)

        assert first.status == "completed"
        assert profile.rating_count == 2
        assert profile.rating_avg == decimal.Decimal("4.50")
        with pytest.raises(svc.InvalidTechTransition):
            svc.complete(db, first, owner, rating=1, text=None)


@requires_real_db
def test_cancel_declines_submitted_offers(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import requests as svc  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        _a, profile = _expert(db, staff)
        owner, company = _factory(db)
        request = _post(db, owner, company)
        offer = _offer(db, request, profile)
        svc.cancel_request(db, request, owner)
        assert request.status == "cancelled"
        assert offer.status == "declined"
        with pytest.raises(svc.InvalidTechTransition):
            svc.cancel_request(db, request, owner)


@requires_real_db
def test_an_edit_is_allowed_only_before_any_offer(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import requests as svc  # noqa: PLC0415
    from app.domains.technologists.schemas import TechRequestIn  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        _a, profile = _expert(db, staff)
        owner, company = _factory(db)
        request = _post(db, owner, company)
        svc.update_request(db, request, TechRequestIn(**{**_REQUEST, "problem": "Толщина"}))
        assert request.problem == "Толщина"
        _offer(db, request, profile)
        with pytest.raises(svc.InvalidTechTransition):
            svc.update_request(db, request, TechRequestIn(**_REQUEST))


@requires_real_db
def test_invites_are_idempotent_and_mark_the_feed(sf) -> None:  # noqa: ANN001
    from app.domains.notifications.models import PortalNotification  # noqa: PLC0415
    from app.domains.technologists import requests as svc  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        acc, profile = _expert(db, staff, processes=["pipe"])
        owner, company = _factory(db)
        request = _post(db, owner, company)
        svc.invite(db, request, profile.id, owner)
        svc.invite(db, request, profile.id, owner)
        assert [r.id for r in svc.feed_for(db, profile, invited_only=True)] == [request.id]
        assert (
            db.query(PortalNotification)
            .filter_by(kind="tech_invite", user_account_id=acc.id)
            .count()
            == 1
        )


@requires_real_db
def test_threads_are_private_to_their_two_sides(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import requests as svc  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        a1, p1 = _expert(db, staff)
        _a2, p2 = _expert(db, staff, "+998900000312")
        owner, company = _factory(db)
        stranger, _other = _factory(db, tax="301000002", phone="+998900000302")
        request = _post(db, owner, company)
        thread = svc.open_thread(db, request, p1)

        svc.post_message(db, thread, author_kind="technologist", account=a1, body="Здравствуйте")
        svc.post_message(db, thread, author_kind="company", account=owner, body="Добрый день")
        assert [m.body for m in svc.list_messages(db, thread)] == ["Здравствуйте", "Добрый день"]

        assert svc.get_thread_for_expert(db, p1, thread.id)[0].id == thread.id
        with pytest.raises(svc.TechRequestNotFound):
            svc.get_thread_for_expert(db, p2, thread.id)
        assert svc.get_thread_for_company(db, owner, company.id, thread.id)[0].id == thread.id
        with pytest.raises(svc.TechRequestNotFound):
            svc.get_thread_for_company(db, stranger, _other.id, thread.id)
        with pytest.raises(ValueError, match="empty_message"):
            svc.post_message(db, thread, author_kind="company", account=owner, body="  ")


@requires_real_db
def test_the_company_opens_a_thread_only_with_an_offerer_or_invitee(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import requests as svc  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        _a, profile = _expert(db, staff)
        owner, company = _factory(db)
        request = _post(db, owner, company)
        with pytest.raises(svc.TechRequestNotFound):
            svc.open_thread_as_company(db, request, profile.id)
        svc.invite(db, request, profile.id, owner)
        assert svc.open_thread_as_company(db, request, profile.id).profile_id == profile.id
