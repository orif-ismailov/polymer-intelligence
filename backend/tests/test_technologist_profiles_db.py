"""Real-Postgres tests for technologist profiles: editing, moderation, the catalog.

The load-bearing rule: the catalog serves `published_snapshot`, written only on
approval — so an expert editing a live profile stays listed as the approved
version, and an unreviewed change never reaches a factory.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
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


def _expert(db, phone="+998900000201"):  # noqa: ANN001, ANN202
    account = make_account(db, phone)
    account.applied_as = "technologist"
    db.flush()
    return account


_COMPLETE = {
    "full_name": "Акмаль Каримов",
    "title": "Технолог экструзии",
    "country": "UZ",
    "city": "Ташкент",
    "years_experience": 12,
    "processes": ["extrusion", "film"],
    "materials": ["LLDPE", "PP"],
    "languages": ["ru", "uz"],
    "work_formats": ["on_site"],
    "contact_phone": "+998901112233",
}


def _fill(db, account, **overrides):  # noqa: ANN001, ANN003, ANN202
    from app.domains.technologists import profiles  # noqa: PLC0415
    from app.domains.technologists.schemas import TechnologistProfileIn  # noqa: PLC0415

    return profiles.update_own(db, account, TechnologistProfileIn(**{**_COMPLETE, **overrides}))


def _publish(db, account, staff, **overrides):  # noqa: ANN001, ANN003, ANN202
    from app.domains.technologists import profiles  # noqa: PLC0415

    profile = _fill(db, account, **overrides)
    profiles.submit_own(db, account)
    profiles.approve(db, profile, staff.id)
    return profile


@requires_real_db
def test_a_company_account_has_no_profile(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import profiles  # noqa: PLC0415

    with sf() as db:
        account = make_account(db, "+998900000202")
        with pytest.raises(profiles.NotATechnologist):
            profiles.get_or_create_own(db, account)


@requires_real_db
def test_submit_names_what_is_missing(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import profiles  # noqa: PLC0415

    with sf() as db:
        account = _expert(db)
        _fill(db, account, title=None, processes=[])
        with pytest.raises(profiles.ProfileIncomplete) as exc:
            profiles.submit_own(db, account)
        assert set(exc.value.args[0]) == {"title", "processes"}


@requires_real_db
def test_approval_lists_the_card_without_contacts(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import profiles  # noqa: PLC0415

    with sf() as db:
        account = _expert(db)
        staff = make_staff(db)
        profile = _publish(db, account, staff)
        db.commit()

        assert profile.status == "published"
        assert profiles.is_listed(profile)
        assert profile.published_snapshot is not None
        assert "contact_phone" not in profile.published_snapshot
        items, total = profiles.list_published(db)
        assert total == 1
        assert items[0].id == profile.id


@requires_real_db
def test_a_live_edit_keeps_serving_the_approved_card(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import profiles  # noqa: PLC0415

    with sf() as db:
        account = _expert(db)
        staff = make_staff(db)
        profile = _publish(db, account, staff)

        _fill(db, account, title="Главный технолог")
        profiles.submit_own(db, account)
        assert profile.status == "pending_review"
        assert profiles.is_listed(profile), "the approved version stays up during review"
        assert profile.published_snapshot["title"] == "Технолог экструзии"

        profiles.reject(db, profile, staff.id, "Уточните заголовок")
        assert profiles.is_listed(profile), "a rejected EDIT does not unlist the expert"
        assert profile.published_snapshot["title"] == "Технолог экструзии"

        _fill(db, account, title="Главный технолог")
        profiles.submit_own(db, account)
        profiles.approve(db, profile, staff.id)
        assert profile.published_snapshot["title"] == "Главный технолог"


@requires_real_db
def test_a_never_approved_profile_is_not_listed(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import profiles  # noqa: PLC0415

    with sf() as db:
        account = _expert(db)
        staff = make_staff(db)
        profile = _fill(db, account)
        profiles.submit_own(db, account)
        assert not profiles.is_listed(profile)
        profiles.reject(db, profile, staff.id, "Нет опыта")
        assert not profiles.is_listed(profile)
        assert profiles.list_published(db)[1] == 0


@requires_real_db
def test_suspension_unlists(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import profiles  # noqa: PLC0415

    with sf() as db:
        account = _expert(db)
        staff = make_staff(db)
        profile = _publish(db, account, staff)
        profiles.suspend(db, profile, staff.id, "Жалобы")
        assert profile.status == "suspended"
        assert not profiles.is_listed(profile)
        assert profiles.list_published(db)[1] == 0


@requires_real_db
def test_only_a_pending_profile_can_be_decided(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import profiles  # noqa: PLC0415

    with sf() as db:
        account = _expert(db)
        staff = make_staff(db)
        profile = _fill(db, account)
        with pytest.raises(profiles.InvalidProfileTransition):
            profiles.approve(db, profile, staff.id)


@requires_real_db
def test_catalog_filters(sf) -> None:  # noqa: ANN001
    from app.domains.technologists import profiles  # noqa: PLC0415

    with sf() as db:
        staff = make_staff(db)
        film = _publish(db, _expert(db, "+998900000211"), staff)
        _publish(
            db,
            _expert(db, "+998900000212"),
            staff,
            full_name="Mehmet Kaya",
            processes=["injection_molding"],
            materials=["ABS"],
            languages=["tr", "en"],
            country="TR",
        )

        assert [p.id for p in profiles.list_published(db, process="film")[0]] == [film.id]
        assert profiles.list_published(db, material="ABS")[1] == 1
        assert profiles.list_published(db, language="tr")[1] == 1
        assert profiles.list_published(db, country="UZ")[1] == 1
        assert profiles.list_published(db, q="kaya")[1] == 1
        assert profiles.list_published(db)[1] == 2


@requires_real_db
def test_moderation_is_audited(sf) -> None:  # noqa: ANN001
    from app.models.staff import AuditLog  # noqa: PLC0415

    with sf() as db:
        account = _expert(db)
        staff = make_staff(db)
        profile = _publish(db, account, staff)
        db.commit()
        actions = {
            a.action
            for a in db.query(AuditLog).filter(AuditLog.entity_id == str(profile.id)).all()
        }
        assert {"technologist.submit", "technologist.approve"} <= actions
