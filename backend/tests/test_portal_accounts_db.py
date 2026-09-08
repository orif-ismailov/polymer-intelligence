"""Migration 0048 against a real Postgres — the claims only a database can refute.

Every assertion here is invisible to the mocked suite, and each corresponds to a way
this change could ship broken while looking fine:

* **`account_status` really has `pending`.** `AccountStatus.pending` exists in Python
  the instant the enum member is written, so every mocked test accepts it; a missing
  `ALTER TYPE` surfaces only as `invalid input value for enum` on the first real INSERT
  — i.e. on the first person who fills in the registration form.
* **`login` is unique case-INSENSITIVELY, and only where it exists.** A plain column
  constraint would allow `Acme` beside `acme` (two accounts, one of them unreachable)
  and would collide the hundreds of credential-less rows against each other.
* **`phone` is NOT unique any more.** With the constraint still standing, the anonymous
  registration form 500s on a repeat number, and that 500 is the enumeration answer the
  endpoint's uniform 202 exists to withhold.

Run with:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \
        uv run pytest tests/test_portal_accounts_db.py -q
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


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


@requires_real_db
def test_a_pending_account_can_be_inserted(sf) -> None:  # noqa: ANN001
    from app.domains.accounts import service as account_service  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    with sf() as db:
        account = account_service.register(
            db, phone="+998901112233", contact_name="Иван", company_name="ООО Полимер"
        )
        db.commit()
        assert account.id is not None
        assert account.status == AccountStatus.pending


@requires_real_db
def test_status_defaults_to_pending_for_a_raw_insert(sf) -> None:  # noqa: ANN001
    """A seeder or a hand-written INSERT that forgets `status` gets an applicant.

    The server_default moved `active` → `pending` in 0048 for exactly this: the
    fail-closed direction is the one where forgetting produces somebody who cannot
    sign in, rather than somebody who can.
    """
    with sf() as db:
        db.execute(
            sa.text("INSERT INTO user_accounts (phone) VALUES ('+998900000001')")
        )
        db.commit()
        status = db.execute(
            sa.text("SELECT status FROM user_accounts WHERE phone = '+998900000001'")
        ).scalar_one()
    assert status == "pending"


@requires_real_db
def test_login_is_unique_case_insensitively(sf) -> None:  # noqa: ANN001
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    with sf() as db:
        db.add(
            UserAccount(
                phone="+998901112233",
                login="acme-trade",
                password_hash="x",
                status=AccountStatus.active,
            )
        )
        db.commit()

    with sf() as db, pytest.raises(sa.exc.IntegrityError):
        db.add(
            UserAccount(
                phone="+998904445566",
                login="ACME-Trade",
                password_hash="y",
                status=AccountStatus.active,
            )
        )
        db.commit()


@requires_real_db
def test_many_accounts_may_have_no_login(sf) -> None:  # noqa: ANN001
    """The index is PARTIAL — otherwise every application would collide on NULL.

    (Postgres would in fact allow repeated NULLs in a plain unique index, but the
    partial form is what makes that guarantee explicit and survives a future switch to
    NULLS NOT DISTINCT.)
    """
    from app.domains.accounts import service as account_service  # noqa: PLC0415

    with sf() as db:
        for i in range(3):
            account_service.register(
                db, phone=f"+99890111223{i}", contact_name="И", company_name="X"
            )
        db.commit()
        count = db.execute(
            sa.text("SELECT count(*) FROM user_accounts WHERE login IS NULL")
        ).scalar_one()
    assert count == 3


@requires_real_db
def test_the_same_phone_may_apply_twice(sf) -> None:  # noqa: ANN001
    """The registration form is anonymous and unverified, so a repeat is ordinary.

    While `phone` carried a UNIQUE constraint the second application raised, and the
    resulting 500 told the caller the first one existed.
    """
    from app.domains.accounts import service as account_service  # noqa: PLC0415

    with sf() as db:
        account_service.register(
            db, phone="+998901112233", contact_name="Иван", company_name="ООО Полимер"
        )
        account_service.register(
            db, phone="+998901112233", contact_name="Иван", company_name="ООО Полимер"
        )
        db.commit()
        count = db.execute(
            sa.text("SELECT count(*) FROM user_accounts WHERE phone = '+998901112233'")
        ).scalar_one()
    assert count == 2


@requires_real_db
def test_sms_send_log_is_gone(sf) -> None:  # noqa: ANN001
    """The table 0048 dropped. Also guards `_verification_db._TABLES`, whose `clean()`
    would otherwise DELETE FROM a table that no longer exists at every teardown."""
    with sf() as db:
        exists = db.execute(
            sa.text("SELECT to_regclass('public.sms_send_log')")
        ).scalar_one()
    assert exists is None


@requires_real_db
def test_authenticate_finds_an_account_through_the_folded_index(sf) -> None:  # noqa: ANN001
    """End to end against real SQL: `lower(login) = :login` must use the stored row.

    The mocked suite cannot see this — its `db.query(...)` returns whatever the mock
    was handed, so a filter that never matches in Postgres passes there.
    """
    from app.core.security import hash_password  # noqa: PLC0415
    from app.domains.accounts import service as account_service  # noqa: PLC0415
    from app.domains.accounts.models import UserAccount  # noqa: PLC0415
    from app.models.enums import AccountStatus  # noqa: PLC0415

    with sf() as db:
        db.add(
            UserAccount(
                phone="+998901112233",
                login="acme-trade",
                password_hash=hash_password("correct horse battery"),
                status=AccountStatus.active,
            )
        )
        db.commit()

    with sf() as db:
        found = account_service.authenticate(db, "  ACME-Trade ", "correct horse battery")
        assert found is not None
        assert found.login == "acme-trade"
        assert account_service.authenticate(db, "acme-trade", "wrong") is None
