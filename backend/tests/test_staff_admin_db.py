"""Staff administration against a real Postgres: creation, access, lockout guards.

Real DB rather than mocks, because the properties that matter here are ones a
mocked session cannot express: the unique constraint on (user, page), the CHECK
on the level, the CASCADE that takes grants with the account, and — most of all —
the administrator count that the lockout guards are computed from.

THE LOCKOUT GUARDS ARE THE POINT. Fully dynamic access with no floor is how you
lock yourself out of your own dashboard, and once out, no endpoint can let you
back in. The two rules under test:
  * the last active administrator cannot be demoted or deactivated;
  * you cannot demote or deactivate yourself.
Both refusals are audited, because "who tried to remove the last administrator"
is a question worth being able to answer.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)

_PW = "a-long-enough-password"


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


def _admin(db, email="boss@polymer.uz"):  # noqa: ANN001, ANN202
    from app.models.staff import StaffUser  # noqa: PLC0415

    user = StaffUser(
        email=email, full_name="The Boss", is_admin=True, password_hash="x"
    )
    db.add(user)
    db.flush()
    return user


def _audit_actions(db) -> list[str]:  # noqa: ANN001
    from app.models.staff import AuditLog  # noqa: PLC0415

    return [
        a.action for a in db.query(AuditLog).order_by(AuditLog.id).all()
    ]


# ── Creation ──────────────────────────────────────────────────────────────────


@requires_real_db
def test_create_stores_only_the_granted_pages(sf) -> None:  # noqa: ANN001
    """A page absent from the map gets no row — absence is how "no access" is spelled."""
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        actor = _admin(db)
        user = svc.create_user(
            db, actor=actor, email="ivan@polymer.uz", full_name="Ivan",
            password=_PW, is_admin=False,
            access={"verification": "write", "companies": "read"},
        )
        db.commit()

        assert svc.access_map(db, user.id) == {
            "verification": "write", "companies": "read"
        }
        # 26 pages in the catalog, 2 granted, 24 rows deliberately absent.
        count = db.execute(
            sa.text("SELECT count(*) FROM staff_page_access WHERE staff_user_id = :i"),
            {"i": user.id},
        ).scalar_one()
        assert count == 2


@requires_real_db
def test_the_password_is_hashed_never_stored_plainly(sf) -> None:  # noqa: ANN001
    from app.core.security import verify_password  # noqa: PLC0415
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        user = svc.create_user(
            db, actor=_admin(db), email="ivan@polymer.uz", full_name="Ivan",
            password=_PW, is_admin=False, access={},
        )
        db.commit()
        assert _PW not in user.password_hash
        assert user.password_hash.startswith("$argon2")
        assert verify_password(_PW, user.password_hash)


@requires_real_db
def test_an_administrator_is_created_without_grant_rows(sf) -> None:  # noqa: ANN001
    """Administrators hold every page implicitly — stored rows would go stale."""
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        user = svc.create_user(
            db, actor=_admin(db), email="admin2@polymer.uz", full_name="Second",
            password=_PW, is_admin=True, access={"deals": "write"},
        )
        db.commit()
        assert svc.access_map(db, user.id) == {}


@requires_real_db
def test_duplicate_email_is_refused(sf) -> None:  # noqa: ANN001
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        actor = _admin(db)
        svc.create_user(db, actor=actor, email="ivan@polymer.uz", full_name="Ivan",
                        password=_PW, is_admin=False, access={})
        db.commit()
        with pytest.raises(svc.EmailAlreadyUsed):
            svc.create_user(db, actor=actor, email="ivan@polymer.uz", full_name="Other",
                            password=_PW, is_admin=False, access={})


# ── Access replacement ────────────────────────────────────────────────────────


@requires_real_db
def test_set_access_replaces_wholesale_rather_than_merging(sf) -> None:  # noqa: ANN001
    """The screen submits every page it rendered, so the map IS the desired state.

    A merge would leave a page the administrator un-ticked silently granted.
    """
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        actor = _admin(db)
        user = svc.create_user(
            db, actor=actor, email="ivan@polymer.uz", full_name="Ivan",
            password=_PW, is_admin=False,
            access={"deals": "write", "escrow": "read", "alerts": "read"},
        )
        db.commit()

        svc.set_access(db, actor=actor, target=user, access={"deals": "read"})
        db.commit()

        assert svc.access_map(db, user.id) == {"deals": "read"}


@requires_real_db
def test_granting_pages_to_an_administrator_is_refused(sf) -> None:  # noqa: ANN001
    """They already hold everything; a matrix for them would be a lie on screen."""
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        actor = _admin(db)
        other = _admin(db, "admin2@polymer.uz")
        db.commit()
        with pytest.raises(svc.StaffAdminRefused):
            svc.set_access(db, actor=actor, target=other, access={"deals": "read"})


@requires_real_db
def test_deleting_a_staff_user_takes_their_grants(sf) -> None:  # noqa: ANN001
    """ON DELETE CASCADE — grants must not outlive the account they describe."""
    from app.models.staff import StaffUser  # noqa: PLC0415
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        user = svc.create_user(
            db, actor=_admin(db), email="ivan@polymer.uz", full_name="Ivan",
            password=_PW, is_admin=False, access={"deals": "read"},
        )
        db.commit()
        uid = user.id
        db.execute(sa.delete(StaffUser).where(StaffUser.id == uid))
        db.commit()
        left = db.execute(
            sa.text("SELECT count(*) FROM staff_page_access WHERE staff_user_id = :i"),
            {"i": uid},
        ).scalar_one()
        assert left == 0


# ── Lockout guards ────────────────────────────────────────────────────────────


@requires_real_db
def test_the_last_administrator_cannot_be_demoted(sf) -> None:  # noqa: ANN001
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        actor = _admin(db)
        target = _admin(db, "admin2@polymer.uz")
        # `actor` demotes themselves out of the way first — refused, so instead
        # demote the OTHER one, leaving exactly one active administrator.
        svc.update_user(db, actor=actor, target=target,
                        full_name=None, is_admin=False, password=None)
        db.commit()

        with pytest.raises(svc.StaffAdminRefused, match="last active administrator"):
            svc.update_user(db, actor=target, target=actor,
                            full_name=None, is_admin=False, password=None)


@requires_real_db
def test_the_last_administrator_cannot_be_deactivated(sf) -> None:  # noqa: ANN001
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        actor = _admin(db)
        other = _admin(db, "admin2@polymer.uz")
        svc.set_active(db, actor=actor, target=other, is_active=False)
        db.commit()

        with pytest.raises(svc.StaffAdminRefused, match="last active administrator"):
            svc.set_active(db, actor=other, target=actor, is_active=False)


@requires_real_db
def test_you_cannot_demote_yourself(sf) -> None:  # noqa: ANN001
    """The common way to reach the last-admin case by accident.

    Refused even when other administrators exist, because the person who could
    undo it is the person who just lost the ability to.
    """
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        actor = _admin(db)
        _admin(db, "admin2@polymer.uz")     # a second admin exists
        db.commit()
        with pytest.raises(svc.StaffAdminRefused, match="your own"):
            svc.update_user(db, actor=actor, target=actor,
                            full_name=None, is_admin=False, password=None)


@requires_real_db
def test_you_cannot_deactivate_yourself(sf) -> None:  # noqa: ANN001
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        actor = _admin(db)
        _admin(db, "admin2@polymer.uz")
        db.commit()
        with pytest.raises(svc.StaffAdminRefused, match="your own"):
            svc.set_active(db, actor=actor, target=actor, is_active=False)


@requires_real_db
def test_a_non_administrator_can_be_deactivated_freely(sf) -> None:  # noqa: ANN001
    """The guards protect administrability, not every account."""
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        actor = _admin(db)
        user = svc.create_user(db, actor=actor, email="ivan@polymer.uz",
                               full_name="Ivan", password=_PW, is_admin=False, access={})
        db.commit()
        svc.set_active(db, actor=actor, target=user, is_active=False)
        db.commit()
        assert user.is_active is False


# ── Audit ─────────────────────────────────────────────────────────────────────


@requires_real_db
def test_every_mutation_is_audited(sf) -> None:  # noqa: ANN001
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        actor = _admin(db)
        user = svc.create_user(db, actor=actor, email="ivan@polymer.uz",
                               full_name="Ivan", password=_PW, is_admin=False, access={})
        svc.set_access(db, actor=actor, target=user, access={"deals": "read"})
        svc.update_user(db, actor=actor, target=user,
                        full_name="Ivan P", is_admin=None, password=None)
        svc.set_active(db, actor=actor, target=user, is_active=False)
        db.commit()

        assert _audit_actions(db) == [
            "staff_user.create",
            "staff_user.set_access",
            "staff_user.update",
            "staff_user.deactivate",
        ]


@requires_real_db
def test_a_password_reset_is_audited_without_the_password(sf) -> None:  # noqa: ANN001
    """The FACT of a reset, never the value — not even the hash."""
    from app.models.staff import AuditLog  # noqa: PLC0415
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        actor = _admin(db)
        user = svc.create_user(db, actor=actor, email="ivan@polymer.uz",
                               full_name="Ivan", password=_PW, is_admin=False, access={})
        svc.update_user(db, actor=actor, target=user,
                        full_name=None, is_admin=None, password="another-long-password")
        db.commit()

        row = (
            db.query(AuditLog)
            .filter(AuditLog.action == "staff_user.update")
            .one()
        )
        assert row.details == {"password_reset": True}
        assert "another-long-password" not in str(row.details)


@requires_real_db
def test_a_refused_action_is_audited_too(sf) -> None:  # noqa: ANN001
    """"Who tried to remove the last administrator" is worth being able to answer."""
    from app.services import staff_admin_service as svc  # noqa: PLC0415

    with sf() as db:
        actor = _admin(db)
        db.commit()
        try:
            svc.update_user(db, actor=actor, target=actor,
                            full_name=None, is_admin=False, password=None)
        except svc.StaffAdminRefused as exc:
            svc.audit_refusal(db, actor=actor, target_id=actor.id,
                              action="staff_user.update", reason=str(exc))
            db.commit()

        assert "staff_user.update.refused" in _audit_actions(db)
