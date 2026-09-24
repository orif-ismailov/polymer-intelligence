"""Seeding the MGBUS-based templates retires the dev placeholders (real Postgres)."""

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


@pytest.fixture
def sf(monkeypatch):  # noqa: ANN001, ANN201
    from app.services import storage_service  # noqa: PLC0415

    migrate_head()
    engine = make_engine()
    monkeypatch.setattr(
        storage_service, "store_contract_template", lambda code, v, html: f"contracts/templates/{code}_v{v}.html"
    )
    clean(engine)
    yield session_factory(engine)
    clean(engine)


@requires_real_db
def test_the_new_templates_replace_the_placeholders(sf) -> None:  # noqa: ANN001
    from app.domains.contracts.models import ContractTemplate  # noqa: PLC0415
    from app.seed.seed_contract_templates import seed_contract_templates  # noqa: PLC0415

    with sf() as db:
        seed_contract_templates(db)
        db.commit()
        active = {
            t.code for t in db.execute(sa.select(ContractTemplate).where(ContractTemplate.is_active)).scalars()
        }
        assert {"SUPPLY_FRAME_V1", "SUPPLY_ONE_OFF_V1"} <= active
        assert not {"SUPPLY_V1", "SUPPLY_V2"} & active

        # A placeholder staff switched back on stays on across later seeds.
        v1 = db.execute(sa.select(ContractTemplate).where(ContractTemplate.code == "SUPPLY_V1")).scalar_one()
        v1.is_active = True
        db.commit()
        seed_contract_templates(db)
        db.commit()
        db.refresh(v1)
        assert v1.is_active
