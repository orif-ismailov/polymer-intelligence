"""
Substance registry: seed + service (P5 W2 — T2.1/T2.2). Guarded real-Postgres.

The registry is the source of truth for regulated chemistry, so the two things
that matter most are:

1. **The seed is idempotent and versioned.** Re-running it must not duplicate a
   row, and re-issuing a list (a new revision) must actually update the rows the
   previous revision wrote — otherwise a corrected threshold would never reach
   production. The one thing a re-seed must never touch is a row an operator has
   edited by hand: `substance_service.update` clears `seed_revision`, which takes
   the row out of the seed's hands permanently.
2. **Search finds a substance the way a seller names it** — by synonym, by CAS,
   by HS code — because a seller typing "ПНД" will not find "Полиэтилен" by
   substring.

Run with a localhost test_polymer DB; skipped otherwise (see _verification_db).
"""

from __future__ import annotations

import decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from tests._verification_db import (
    clean,
    make_engine,
    make_staff,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

pytestmark = requires_real_db


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def db(engine: sa.Engine) -> Session:
    clean(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM substances"))
    session = session_factory(engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _substance(db: Session, **kwargs):  # noqa: ANN003, ANN202
    from app.domains.compliance.models import Substance  # noqa: PLC0415
    from app.models.enums import RegulationLevel  # noqa: PLC0415

    row = Substance(
        code=kwargs.pop("code", "acetone"),
        name_ru=kwargs.pop("name_ru", "Ацетон"),
        hs_code=kwargs.pop("hs_code", "2914.11"),
        regulation_level=kwargs.pop("regulation_level", RegulationLevel.free),
        **kwargs,
    )
    db.add(row)
    db.flush()
    return row


class TestSeed:
    def test_seeding_twice_creates_nothing_new(self, db: Session) -> None:
        from app.seed.seed_substances import seed_substances  # noqa: PLC0415

        first = seed_substances(db)
        assert first.created, "the v1 revision must ship at least one substance"
        second = seed_substances(db)
        assert second.created == []
        assert second.updated == []

    def test_every_seeded_row_carries_its_act_and_revision(self, db: Session) -> None:
        """A row nobody can trace back to a ПКМ is a row a lawyer cannot check."""
        from app.domains.compliance.models import Substance  # noqa: PLC0415
        from app.seed.seed_substances import REVISION, seed_substances  # noqa: PLC0415

        seed_substances(db)
        rows = db.query(Substance).all()
        for row in rows:
            assert row.seed_revision == REVISION
            assert row.source_act, f"{row.code} has no source act"

    def test_the_polymers_this_platform_trades_are_free(self, db: Session) -> None:
        """PP/PE/PVC/PET/PS are in none of the four lists (INTEGRATIONS.md §4).
        If the seed ever marked them regulated, the whole marketplace would stop
        publishing the day the gate is switched on."""
        from app.domains.compliance.models import Substance  # noqa: PLC0415
        from app.models.enums import RegulationLevel  # noqa: PLC0415
        from app.seed.seed_substances import seed_substances  # noqa: PLC0415

        seed_substances(db)
        for code in ("pp", "pe", "pvc", "pet", "ps"):
            row = db.query(Substance).filter(Substance.code == code).one()
            assert row.regulation_level == RegulationLevel.free, code
            assert row.regulation_regime is None, code

    def test_list_iv_precursors_carry_their_threshold_and_exemption(
        self, db: Session
    ) -> None:
        """Список IV regulates acetone at ≥60% with a ≤12 kg/year exemption. A
        level without the threshold would block ordinary solvent trade."""
        from app.domains.compliance.models import Substance  # noqa: PLC0415
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415
        from app.seed.seed_substances import seed_substances  # noqa: PLC0415

        seed_substances(db)
        acetone = db.query(Substance).filter(Substance.code == "acetone").one()
        assert acetone.regulation_level == RegulationLevel.license_required
        assert acetone.regulation_regime == RegulationRegime.precursor_list_iv
        assert acetone.threshold_concentration_pct == decimal.Decimal("60.00")
        assert acetone.exemption_annual_limit == decimal.Decimal("12.000")

    def test_a_new_revision_updates_rows_the_seed_owns(self, db: Session) -> None:
        from app.domains.compliance.models import Substance  # noqa: PLC0415
        from app.seed.seed_substances import seed_substances  # noqa: PLC0415

        seed_substances(db)
        acetone = db.query(Substance).filter(Substance.code == "acetone").one()
        acetone.threshold_concentration_pct = decimal.Decimal("5.00")  # pretend v1 was wrong
        acetone.seed_revision = "v0-old"
        db.flush()

        outcome = seed_substances(db)
        assert "acetone" in outcome.updated
        db.refresh(acetone)
        assert acetone.threshold_concentration_pct == decimal.Decimal("60.00")

    def test_an_operator_edit_is_never_overwritten(self, db: Session) -> None:
        """`substance_service.update` clears `seed_revision`; that NULL is the
        row's "hands off" flag. Losing an operator's correction on the next
        deploy would make the admin panel untrustworthy."""
        from app.domains.compliance.models import Substance  # noqa: PLC0415
        from app.seed.seed_substances import seed_substances  # noqa: PLC0415

        seed_substances(db)
        acetone = db.query(Substance).filter(Substance.code == "acetone").one()
        acetone.threshold_concentration_pct = decimal.Decimal("42.00")
        acetone.seed_revision = None
        db.flush()

        outcome = seed_substances(db)
        assert "acetone" not in outcome.updated
        db.refresh(acetone)
        assert acetone.threshold_concentration_pct == decimal.Decimal("42.00")


class TestSearch:
    def test_finds_by_synonym(self, db: Session) -> None:
        """A seller types "ПНД", not "Полиэтилен" — and one is not a substring
        of the other."""
        from app.domains.compliance import substances as substance_service  # noqa: PLC0415

        _substance(db, code="pe", name_ru="Полиэтилен", synonyms=["ПНД", "HDPE"])
        found = substance_service.search(db, "пнд")
        assert [s.code for s in found] == ["pe"]

    def test_finds_by_cas_and_hs_code(self, db: Session) -> None:
        from app.domains.compliance import substances as substance_service  # noqa: PLC0415

        _substance(db, code="acetone", cas="67-64-1", hs_code="2914.11")
        assert [s.code for s in substance_service.search(db, "67-64-1")] == ["acetone"]
        assert [s.code for s in substance_service.search(db, "2914")] == ["acetone"]

    def test_inactive_rows_stay_out_of_the_picker(self, db: Session) -> None:
        from app.domains.compliance import substances as substance_service  # noqa: PLC0415

        _substance(db, code="old", name_ru="Устаревшее", is_active=False)
        assert substance_service.search(db, "устар") == []
        assert [s.code for s in substance_service.list_all(db, include_inactive=True)] == ["old"]

    def test_blank_query_returns_nothing(self, db: Session) -> None:
        from app.domains.compliance import substances as substance_service  # noqa: PLC0415

        _substance(db)
        assert substance_service.search(db, "   ") == []


class TestResolve:
    def test_cas_wins_over_name(self, db: Session) -> None:
        """CAS is exact; a name is a guess. When the AI gives both, the exact
        identifier decides."""
        from app.domains.compliance import substances as substance_service  # noqa: PLC0415

        _substance(db, code="acetone", name_ru="Ацетон", cas="67-64-1")
        _substance(db, code="toluene", name_ru="Толуол", cas="108-88-3", hs_code="2902.30")
        found = substance_service.resolve(db, cas="108-88-3", name="Ацетон")
        assert found is not None and found.code == "toluene"

    def test_resolves_by_synonym_when_there_is_no_identifier(self, db: Session) -> None:
        from app.domains.compliance import substances as substance_service  # noqa: PLC0415

        _substance(db, code="acetone", name_ru="Ацетон", synonyms=["Диметилкетон", "propanone"])
        found = substance_service.resolve(db, name="propanone")
        assert found is not None and found.code == "acetone"

    def test_unknown_resolves_to_none(self, db: Session) -> None:
        from app.domains.compliance import substances as substance_service  # noqa: PLC0415

        assert substance_service.resolve(db, cas="000-00-0", name="Неизвестное") is None


class TestAdminWrites:
    def test_create_audits_and_stamps_no_seed_revision(self, db: Session) -> None:
        from app.domains.compliance import substances as substance_service  # noqa: PLC0415
        from app.domains.compliance.substance_schemas import SubstanceIn  # noqa: PLC0415

        staff = make_staff(db)
        row = substance_service.create(
            db,
            SubstanceIn(code="xylene", name_ru="Ксилол", hs_code="2902.44"),
            staff_user_id=staff.id,
        )
        assert row.seed_revision is None
        audit = db.execute(
            sa.text("SELECT action FROM audit_log WHERE entity = 'substances'")
        ).scalars().all()
        assert audit == ["substance.create"]

    def test_update_takes_the_row_out_of_the_seeds_hands(self, db: Session) -> None:
        from app.domains.compliance import substances as substance_service  # noqa: PLC0415
        from app.domains.compliance.substance_schemas import SubstanceIn  # noqa: PLC0415

        staff = make_staff(db)
        row = _substance(db, code="acetone", seed_revision="v1-provisional")
        substance_service.update(
            db,
            row,
            SubstanceIn(code="acetone", name_ru="Ацетон (правка)", hs_code="2914.11"),
            staff_user_id=staff.id,
        )
        assert row.seed_revision is None
        assert row.name_ru == "Ацетон (правка)"

    def test_duplicate_code_is_a_domain_error_not_a_500(self, db: Session) -> None:
        from app.domains.compliance import substances as substance_service  # noqa: PLC0415
        from app.domains.compliance.substance_schemas import SubstanceIn  # noqa: PLC0415

        staff = make_staff(db)
        _substance(db, code="acetone")
        with pytest.raises(substance_service.SubstanceExists):
            substance_service.create(
                db,
                SubstanceIn(code="acetone", name_ru="Дубль", hs_code="2914.11"),
                staff_user_id=staff.id,
            )

    def test_duplicate_cas_is_a_domain_error_too(self, db: Session) -> None:
        """Two rows for one CAS would give two different verdicts for the same
        chemical."""
        from app.domains.compliance import substances as substance_service  # noqa: PLC0415
        from app.domains.compliance.substance_schemas import SubstanceIn  # noqa: PLC0415

        staff = make_staff(db)
        _substance(db, code="acetone", cas="67-64-1")
        with pytest.raises(substance_service.SubstanceExists):
            substance_service.create(
                db,
                SubstanceIn(code="propanone", name_ru="Пропанон", hs_code="2914.11", cas="67-64-1"),
                staff_user_id=staff.id,
            )

    def test_deactivate_keeps_the_row(self, db: Session) -> None:
        """Deleting a substance would orphan the offers pointing at it and erase
        why they were once blocked."""
        from app.domains.compliance import substances as substance_service  # noqa: PLC0415

        staff = make_staff(db)
        row = _substance(db, code="acetone")
        substance_service.set_active(db, row, active=False, staff_user_id=staff.id)
        assert row.is_active is False
