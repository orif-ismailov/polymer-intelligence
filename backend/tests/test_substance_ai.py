"""
AI substance suggestion (P5 W4 — T4.1/T4.2, FR-C3). No network.

The LLM client is patched exactly like `parsing.extractor._client` in the rest
of the suite, so nothing here calls Anthropic.

What the tests pin is the shape of the feature rather than the model's answer:

  * **A suggestion is a suggestion.** It is journalled and returned; it never
    writes `substance_id` onto the offer. The seller's explicit decision does
    that, and the decision is journalled too.
  * **The journal survives a miss.** When the model names something the registry
    does not carry, the row is still written with `substance_id = NULL` — that
    gap is the signal for extending the registry, and throwing it away would
    hide it.
  * **The budget guard degrades quietly.** Out of tokens means no suggestion and
    no row, not a 500 in the middle of a seller filling in a form.
  * **The prompt family is versioned and immutable**, like the other four.
"""

from __future__ import annotations

import decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

_PROMPTS = Path(__file__).parent.parent / "parsing" / "prompts"
_P = "/api/v1/portal"


def _completion(tokens_in: int = 400, tokens_out: int = 60) -> MagicMock:
    usage = MagicMock()
    usage.input_tokens = tokens_in
    usage.output_tokens = tokens_out
    usage.cache_creation_input_tokens = 0
    completion = MagicMock()
    completion.usage = usage
    return completion


def _result(**kwargs: Any) -> Any:  # noqa: ANN401
    from app.schemas.substance_match import SubstanceMatchResult  # noqa: PLC0415

    payload = {
        "name": "Ацетон",
        "cas": "67-64-1",
        "hs_code": "2914.11",
        "concentration_pct": 99.5,
        "confidence": 0.9,
    }
    payload.update(kwargs)
    return SubstanceMatchResult(**payload)


class TestPromptFamily:
    def test_v1_exists_and_is_the_pinned_version(self) -> None:
        from app.services import substance_ai_service as svc  # noqa: PLC0415

        assert svc.PROMPT_VERSION == "v1"
        assert (_PROMPTS / "substance_match_v1.md").exists()

    def test_the_prompt_asks_for_a_candidate_not_a_decision(self) -> None:
        """The model proposes; the seller decides. A prompt that told it to
        "classify the offer" would invite writing a regulation level we then
        treat as authoritative."""
        text = (_PROMPTS / "substance_match_v1.md").read_text(encoding="utf-8")
        assert "regulation" not in text.lower(), (
            "the regulation level comes from our registry, never from the model"
        )


class TestRuntimeSetting:
    def test_the_feature_has_a_kill_switch_that_ships_on(self) -> None:
        from app.services.settings_service import _SPECS  # noqa: PLC0415

        spec = _SPECS.get("substance_ai_enabled")
        assert spec is not None
        assert spec.default is True


# ── Behaviour (guarded) ───────────────────────────────────────────────────────


pytestmark_db = requires_real_db


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


def _acetone(db: Session):  # noqa: ANN202
    from app.models.compliance import Substance  # noqa: PLC0415
    from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

    row = Substance(
        code="acetone",
        name_ru="Ацетон",
        hs_code="2914.11",
        cas="67-64-1",
        regulation_level=RegulationLevel.license_required,
        regulation_regime=RegulationRegime.precursor_list_iv,
    )
    db.add(row)
    db.flush()
    return row


def _company(db: Session):  # noqa: ANN202
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = make_account(db, "+998900000201")
    company = make_company(db, account, "301999111")
    company.status = CompanyStatus.verified
    db.flush()
    return account, company


@requires_real_db
class TestSuggest:
    def test_resolves_the_candidate_and_journals_the_run(self, db: Session) -> None:
        from app.services import substance_ai_service as svc  # noqa: PLC0415

        substance = _acetone(db)
        _, company = _company(db)
        with patch.object(svc, "_client") as client:
            client.messages.create_with_completion.return_value = (_result(), _completion())
            row = svc.suggest(db, text="Ацетон технический 99.5%", company_id=company.id)

        assert row is not None
        assert row.substance_id == substance.id
        assert row.suggested_cas == "67-64-1"
        assert row.suggested_concentration_pct == decimal.Decimal("99.50")
        assert row.prompt_version == svc.PROMPT_VERSION
        assert row.model
        assert row.tokens_in == 400
        assert row.accepted is None, "nobody has decided yet"

    def test_an_unknown_candidate_is_still_journalled(self, db: Session) -> None:
        from app.services import substance_ai_service as svc  # noqa: PLC0415

        _, company = _company(db)
        with patch.object(svc, "_client") as client:
            client.messages.create_with_completion.return_value = (
                _result(name="Неизвестное вещество", cas="999-99-9", hs_code="9999"),
                _completion(),
            )
            row = svc.suggest(db, text="что-то странное", company_id=company.id)

        assert row is not None
        assert row.substance_id is None
        assert row.suggested_name == "Неизвестное вещество"

    def test_disabled_makes_no_call_and_no_row(self, db: Session) -> None:
        from app.models.compliance import SubstanceSuggestion  # noqa: PLC0415
        from app.services import settings_service  # noqa: PLC0415
        from app.services import substance_ai_service as svc  # noqa: PLC0415

        _, company = _company(db)
        settings_service.set_many(db, {"substance_ai_enabled": False}, None)
        with patch.object(svc, "_client") as client:
            assert svc.suggest(db, text="Ацетон", company_id=company.id) is None
            client.messages.create_with_completion.assert_not_called()
        assert db.query(SubstanceSuggestion).count() == 0

    def test_an_exhausted_budget_degrades_quietly(self, db: Session) -> None:
        from app.models.compliance import SubstanceSuggestion  # noqa: PLC0415
        from app.services import substance_ai_service as svc  # noqa: PLC0415
        from parsing.schemas import BudgetExceeded  # noqa: PLC0415

        _, company = _company(db)
        with (
            patch.object(svc, "check_and_reserve_tokens", side_effect=BudgetExceeded("nope")),
            patch.object(svc, "_client") as client,
        ):
            assert svc.suggest(db, text="Ацетон", company_id=company.id) is None
            client.messages.create_with_completion.assert_not_called()
        assert db.query(SubstanceSuggestion).count() == 0

    def test_an_llm_error_releases_the_reservation(self, db: Session) -> None:
        from app.services import substance_ai_service as svc  # noqa: PLC0415

        _, company = _company(db)
        with (
            patch.object(svc, "_client") as client,
            patch.object(svc, "record_actual_tokens") as release,
        ):
            client.messages.create_with_completion.side_effect = RuntimeError("boom")
            assert svc.suggest(db, text="Ацетон", company_id=company.id) is None
            release.assert_called_once()

    def test_the_offer_is_never_written_by_the_suggestion(self, db: Session) -> None:
        """FR-C3: no auto-write, ever. Only the seller's decision moves data."""
        from app.services import substance_ai_service as svc  # noqa: PLC0415
        from tests._verification_db import make_seller_offer  # noqa: PLC0415

        _acetone(db)
        _, company = _company(db)
        offer = make_seller_offer(db, company=company)
        with patch.object(svc, "_client") as client:
            client.messages.create_with_completion.return_value = (_result(), _completion())
            svc.suggest(db, text="Ацетон", company_id=company.id, offer_id=offer.id)

        db.refresh(offer)
        assert offer.substance_id is None
        assert offer.cas_number is None


@requires_real_db
class TestDecision:
    def test_accepting_is_journalled(self, db: Session) -> None:
        from app.services import substance_ai_service as svc  # noqa: PLC0415

        _acetone(db)
        account, company = _company(db)
        with patch.object(svc, "_client") as client:
            client.messages.create_with_completion.return_value = (_result(), _completion())
            row = svc.suggest(db, text="Ацетон", company_id=company.id)

        assert row is not None
        svc.decide(db, row, accepted=True, account_id=account.id)
        assert row.accepted is True
        assert row.decided_at is not None
        assert row.decided_by_user_account_id == account.id

    def test_rejecting_is_a_different_state_from_undecided(self, db: Session) -> None:
        from app.services import substance_ai_service as svc  # noqa: PLC0415

        _acetone(db)
        account, company = _company(db)
        with patch.object(svc, "_client") as client:
            client.messages.create_with_completion.return_value = (_result(), _completion())
            row = svc.suggest(db, text="Ацетон", company_id=company.id)

        assert row is not None
        svc.decide(db, row, accepted=False, account_id=account.id)
        assert row.accepted is False


# ── API ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN001, ANN201
    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM substances"))
    session = session_factory(engine)
    fake_redis = FakeRedis()
    app = create_app()

    def _override_db():  # noqa: ANN202
        session_ = session()
        try:
            yield session_
        finally:
            session_.close()

    def _override_redis():  # noqa: ANN202
        yield fake_redis

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _headers(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


@requires_real_db
class TestApi:
    def test_suggest_then_accept(self, api) -> None:  # noqa: ANN001
        from app.services import substance_ai_service as svc  # noqa: PLC0415

        client, session = api
        with session() as db:
            substance = _acetone(db)
            account, company = _company(db)
            db.commit()
            ids = (account.id, company.id, substance.id)

        with patch.object(svc, "_client") as llm:
            llm.messages.create_with_completion.return_value = (_result(), _completion())
            suggested = client.post(
                f"{_P}/companies/{ids[1]}/substance-suggestions",
                json={"text": "Ацетон технический 99.5%"},
                headers=_headers(ids[0]),
            )
        assert suggested.status_code == 200, suggested.text
        body = suggested.json()
        assert body["substance"]["code"] == "acetone"
        assert body["accepted"] is None

        decided = client.post(
            f"{_P}/companies/{ids[1]}/substance-suggestions/{body['id']}/decision",
            json={"accepted": True},
            headers=_headers(ids[0]),
        )
        assert decided.status_code == 200
        assert decided.json()["accepted"] is True

    def test_another_companys_suggestion_is_not_decidable(self, api) -> None:  # noqa: ANN001
        from app.models.compliance import SubstanceSuggestion  # noqa: PLC0415

        client, session = api
        with session() as db:
            account, company = _company(db)
            other_account = make_account(db, "+998900000202")
            other = make_company(db, other_account, "301999222")
            row = SubstanceSuggestion(
                company_id=company.id, input_text="Ацетон", model="m", prompt_version="v1"
            )
            db.add(row)
            db.commit()
            ids = (other_account.id, other.id, row.id)

        denied = client.post(
            f"{_P}/companies/{ids[1]}/substance-suggestions/{ids[2]}/decision",
            json={"accepted": True},
            headers=_headers(ids[0]),
        )
        assert denied.status_code == 404

    def test_a_disabled_feature_answers_204(self, api) -> None:  # noqa: ANN001
        """The form must be able to tell "no hint" from "the hint failed"."""
        client, session = api
        with session() as db:
            account, company = _company(db)
            from app.services import settings_service  # noqa: PLC0415

            settings_service.set_many(db, {"substance_ai_enabled": False}, None)
            db.commit()
            ids = (account.id, company.id)

        answered = client.post(
            f"{_P}/companies/{ids[1]}/substance-suggestions",
            json={"text": "Ацетон"},
            headers=_headers(ids[0]),
        )
        assert answered.status_code == 204
