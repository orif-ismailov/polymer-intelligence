"""Migration 0055: the technologist marketplace.

Offline half: the file is wired into the single-head chain. Real-DB half: the
seven tables exist and the constraints the service relies on are enforced by
Postgres, not just by Python — a second active offer, a rating of 6, an unknown
`applied_as` are refused by the database itself.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

from tests._verification_db import clean, make_engine, migrate_head, requires_real_db

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0055_technologists.py"

_TABLES = (
    "technologist_profiles",
    "tech_requests",
    "tech_request_invites",
    "tech_offers",
    "tech_threads",
    "tech_messages",
    "tech_reviews",
)


def test_migration_is_wired() -> None:
    spec = importlib.util.spec_from_file_location("migration_0055", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    assert module.revision == "0055"  # type: ignore[attr-defined]
    assert module.down_revision == "0054"  # type: ignore[attr-defined]


def test_models_match_the_tables() -> None:
    import app.models  # noqa: F401, PLC0415
    from app.core.db import Base  # noqa: PLC0415

    for table in _TABLES:
        assert table in Base.metadata.tables, table
    assert "applied_as" in Base.metadata.tables["user_accounts"].c


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


def _account(conn: sa.Connection, phone: str, applied_as: str = "technologist") -> int:
    return int(
        conn.execute(
            sa.text(
                "INSERT INTO user_accounts (phone, applied_as, status) "
                "VALUES (:p, :a, 'active') RETURNING id"
            ),
            {"p": phone, "a": applied_as},
        ).scalar_one()
    )


def _world(conn: sa.Connection) -> tuple[int, int]:
    """(request_id, profile_id) on a fresh company + expert."""
    owner = _account(conn, "+998900000091", "company")
    company = conn.execute(
        sa.text(
            "INSERT INTO companies (jurisdiction, tax_id, created_by_user_account_id) "
            "VALUES ('UZ', '309999991', :o) RETURNING id"
        ),
        {"o": owner},
    ).scalar_one()
    expert = _account(conn, "+998900000092")
    profile = conn.execute(
        sa.text("INSERT INTO technologist_profiles (user_account_id) VALUES (:a) RETURNING id"),
        {"a": expert},
    ).scalar_one()
    request = conn.execute(
        sa.text(
            "INSERT INTO tech_requests (number, company_id, created_by_user_account_id, "
            "need_type, process, equipment, product, problem, country, urgency, work_format) "
            "VALUES ('IMX-TECH-T1', :c, :o, 'troubleshooting', 'film', 'line', 'PE film', "
            "'thickness', 'UZ', 'week', 'on_site') RETURNING id"
        ),
        {"c": company, "o": owner},
    ).scalar_one()
    return int(request), int(profile)


@requires_real_db
def test_tables_exist_and_account_default(engine: sa.Engine) -> None:
    clean(engine)
    insp = sa.inspect(engine)
    for table in _TABLES:
        assert insp.has_table(table), table
    with engine.begin() as conn:
        row = conn.execute(
            sa.text("INSERT INTO user_accounts (phone) VALUES ('+998900000090') RETURNING applied_as")
        ).scalar_one()
        assert row == "company"
    clean(engine)


@requires_real_db
def test_unknown_applied_as_is_refused(engine: sa.Engine) -> None:
    clean(engine)
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        _account(conn, "+998900000093", "wizard")
    clean(engine)


@requires_real_db
def test_one_active_offer_per_expert_per_request(engine: sa.Engine) -> None:
    clean(engine)
    insert = sa.text(
        "INSERT INTO tech_offers (request_id, profile_id, scope, price, currency, "
        "duration_days, work_format, status) "
        "VALUES (:r, :p, 'audit', 1500, 'USD', 3, 'on_site', :s)"
    )
    with engine.begin() as conn:
        request, profile = _world(conn)
        conn.execute(insert, {"r": request, "p": profile, "s": "withdrawn"})
        conn.execute(insert, {"r": request, "p": profile, "s": "submitted"})
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        conn.execute(insert, {"r": request, "p": profile, "s": "submitted"})
    clean(engine)


@requires_real_db
def test_rating_is_one_to_five(engine: sa.Engine) -> None:
    clean(engine)
    with engine.begin() as conn:
        request, profile = _world(conn)
        company, owner = conn.execute(
            sa.text("SELECT company_id, created_by_user_account_id FROM tech_requests WHERE id=:r"),
            {"r": request},
        ).one()
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO tech_reviews (request_id, profile_id, company_id, rating, "
                "created_by_user_account_id) VALUES (:r, :p, :c, 6, :o)"
            ),
            {"r": request, "p": profile, "c": company, "o": owner},
        )
    clean(engine)
