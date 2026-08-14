"""send_contract_activated_to_group task tests (R3 Stage B — TB3.3).

Consumer registration + skip/never-raise (DB-free); the actual card send (bot
patched) against test_polymer (guarded).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)


def test_consumer_registered_for_contract_activated() -> None:
    import app.tasks.notify as notify  # noqa: PLC0415
    from app.services import event_types  # noqa: PLC0415
    from app.tasks.events import CONSUMERS  # noqa: PLC0415

    assert notify.send_contract_activated_to_group in CONSUMERS[event_types.CONTRACT_ACTIVATED]


def test_skips_when_no_chat_configured(monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import settings  # noqa: PLC0415
    from app.tasks import notify  # noqa: PLC0415

    monkeypatch.setattr(settings, "VERIFICATION_NOTIFY_CHAT_ID", None)
    monkeypatch.setattr(settings, "REQUEST_NOTIFY_CHAT_ID", None)
    assert notify.send_contract_activated_to_group(aggregate_id="1")["status"] == "skipped"


def test_skips_when_no_contract_id() -> None:
    from app.tasks import notify  # noqa: PLC0415

    assert notify.send_contract_activated_to_group()["status"] == "skipped"


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
def test_sends_card_for_active_contract(engine: sa.Engine, sf, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import settings  # noqa: PLC0415
    from app.domains.contracts.models import Contract, ContractTemplate  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415
    from app.tasks import notify  # noqa: PLC0415

    monkeypatch.setattr("app.core.db.engine", engine)  # task uses Session(engine)
    monkeypatch.setattr(settings, "VERIFICATION_NOTIFY_CHAT_ID", -1000)
    sent = AsyncMock()
    monkeypatch.setattr("telegram.bot.bot.send_message", sent)

    with sf() as db:
        owner = make_account(db, "+998900000001")
        owner2 = make_account(db, "+998900000002")
        a = make_company(db, owner, tax_id="301111111", legal_name="OOO A")
        b = make_company(db, owner2, tax_id="302222222", legal_name="OOO B")
        tpl = ContractTemplate(
            code="X", name_ru="Договор", body_storage_path="x", variables_schema={}, version=1, is_active=True
        )
        db.add(tpl)
        db.flush()
        contract = Contract(
            template_id=tpl.id, template_version=1, initiator_company_id=a.id,
            counterparty_company_id=b.id, title="Договор X", variables={},
            status=ContractStatus.active, created_by_user_account_id=owner.id,
        )
        db.add(contract)
        db.commit()
        cid = contract.id

    result = notify.send_contract_activated_to_group(aggregate_id=str(cid))
    assert result["status"] == "ok", result.get("error")
    sent.assert_awaited_once()
    text = sent.await_args.kwargs["text"]
    assert "OOO A" in text and "OOO B" in text
