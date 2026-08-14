"""
Tests for the xarid procurement parse path:

- signal_service.create_buy_request_signal_from_xarid (structured payload → Signal)
- parse_xarid_item Celery task routing:
    * synonym match           → buy_request signal, parse_status='parsed'
    * LLM resolves the product → buy_request signal (via='llm')
    * nothing resolves         → parse_status='irrelevant', no signal (noise filter)
- xarid fetch enqueues parse_xarid_item (not the UZEX parse_raw_item)

All HTTP/LLM/DB is mocked — no network, no Postgres.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

# NOTE: app.* imports are deferred into the tests (conftest patches env at fixture
# time, so importing app.core.db / models at module top fails Settings() at collection).

# A realistic xarid detail payload (mirrors app.ingest.xarid.adapters._to_draft).
XARID_PAYLOAD: dict[str, Any] = {
    "kind_hint": "buy_request",
    "buyer": "Buyer Alpha LLC",
    "product_text": "Полиэтилен HDPE",
    "product_code": "20.16.10.000-001",
    "quantity": "50.0",
    "unit": "тонна",
    "price": "12000000.00",
    "currency": "So'm",
    "delivery_location": "Ташкент Юнусабад",
    "country": "УЗБЕКИСТАН",
    "publication_date": "2026-07-01T09:00:00",
    "deadline": "2026-08-01T10:00:00",
    "phone": "998901112233",
    "email": "buyer@alpha.uz",
    "tender_url": "https://xarid.uzex.uz/auction/detail/101",
}


def _raw_item(payload: dict[str, Any], *, raw_item_id: int = 101, source_id: int = 5) -> MagicMock:
    item = MagicMock()
    item.id = raw_item_id
    item.source_id = source_id
    item.payload = payload
    item.parse_status = "pending"
    item.event_at = None
    item.content = (
        f"Buyer: {payload.get('buyer')} | Products: {payload.get('product_text')}"
    )
    return item


# ── Unit: structured payload → Signal ────────────────────────────────────────


class TestCreateBuyRequestSignal:
    def test_maps_structured_payload_to_buy_request(self) -> None:
        from app.domains.signals.service import create_buy_request_signal_from_xarid
        from app.models.enums import SignalKind

        session = MagicMock()
        sig = create_buy_request_signal_from_xarid(
            session, _raw_item(XARID_PAYLOAD), product_id=1, grade_id=None, grade_text="HDPE"
        )

        assert sig.kind == SignalKind.buy_request          # forced, never inferred
        assert sig.product_id == 1
        assert sig.counterparty_text == "Buyer Alpha LLC"  # buyer → counterparty
        assert sig.volume == Decimal("50")                 # quantity → volume
        assert sig.price == Decimal("12000000")
        assert sig.currency == "UZS"                        # "So'm" normalized
        assert sig.region == "Ташкент Юнусабад"
        assert sig.grade_text == "HDPE"
        assert sig.raw_item_id == 101
        assert sig.source_id == 5
        # event_at derived from the tender's publication date.
        assert sig.event_at.year == 2026 and sig.event_at.month == 7

    def test_grade_text_falls_back_to_product_text(self) -> None:
        from app.domains.signals.service import create_buy_request_signal_from_xarid

        sig = create_buy_request_signal_from_xarid(
            MagicMock(), _raw_item(XARID_PAYLOAD), product_id=2, grade_id=None, grade_text=None
        )
        assert sig.grade_text == "Полиэтилен HDPE"


# ── Task routing ─────────────────────────────────────────────────────────────


def _patch_session(mock_get_session: MagicMock, raw_item: MagicMock) -> MagicMock:
    session = MagicMock()
    mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
    mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
    session.get.return_value = raw_item
    return session


class TestParseXaridItemRouting:
    def test_synonym_match_creates_buy_request(self) -> None:
        """Dictionary hit → buy_request signal, no LLM call."""
        from app.models.enums import SignalKind
        from app.tasks.parse import parse_xarid_item

        raw_item = _raw_item(XARID_PAYLOAD)
        with (
            patch("app.tasks.parse.get_session") as mock_get_session,
            patch("app.tasks.parse.match_product", return_value=7),
            patch("app.tasks.parse.write_parse_run"),
            patch("app.tasks.parse.llm_extract_signal") as mock_llm,
            patch("app.services.grade_service.extract_grade", return_value=(None, "HDPE")),
        ):
            session = _patch_session(mock_get_session, raw_item)
            result = parse_xarid_item(101)

        assert result["status"] == "parsed"
        assert result["via"] == "rule_based"
        mock_llm.assert_not_called()                       # dictionary hit → no tokens spent
        added = session.add.call_args[0][0]                # the real Signal we built
        assert added.kind == SignalKind.buy_request
        assert raw_item.parse_status == "parsed"

    def test_llm_resolves_product_creates_signal(self) -> None:
        """Dictionary miss → LLM maps the procurement name to a polymer → signal."""
        from app.models.enums import SignalKind
        from app.tasks.parse import parse_xarid_item

        raw_item = _raw_item(XARID_PAYLOAD)
        llm_result = MagicMock()
        llm_result.product = "PP"
        llm_result.grade_text = None

        with (
            patch("app.tasks.parse.get_session") as mock_get_session,
            # 1st call (product_text) → miss; 2nd call (LLM's "PP") → hit.
            patch("app.tasks.parse.match_product", side_effect=[None, 3]),
            patch("app.tasks.parse.check_and_reserve_tokens"),
            patch("app.tasks.parse.record_actual_tokens"),
            patch(
                "app.tasks.parse.llm_extract_signal",
                return_value=(llm_result, {"parser": "llm_extract_tools", "model": "haiku"}),
            ),
            patch("app.tasks.parse.write_parse_run"),
            patch("app.services.grade_service.extract_grade", return_value=(None, "HDPE")),
        ):
            session = _patch_session(mock_get_session, raw_item)
            result = parse_xarid_item(101)

        assert result["status"] == "parsed"
        assert result["via"] == "llm"
        added = session.add.call_args[0][0]
        assert added.kind == SignalKind.buy_request
        assert added.product_id == 3

    def test_unresolved_product_marks_irrelevant(self) -> None:
        """Neither the dictionary nor the LLM maps it to a polymer → dropped (irrelevant)."""
        from app.tasks.parse import parse_xarid_item

        # Blank content → LLM is skipped entirely; product stays unresolved.
        raw_item = _raw_item(XARID_PAYLOAD)
        raw_item.content = ""

        with (
            patch("app.tasks.parse.get_session") as mock_get_session,
            patch("app.tasks.parse.match_product", return_value=None),
            patch("app.tasks.parse.queue_for_classification") as mock_queue,
            patch("app.tasks.parse.write_parse_run"),
        ):
            session = _patch_session(mock_get_session, raw_item)
            result = parse_xarid_item(101)

        assert result["status"] == "irrelevant"
        assert raw_item.parse_status == "irrelevant"
        session.add.assert_not_called()                    # no signal
        mock_queue.assert_called_once()

    def test_double_parse_guard(self) -> None:
        """A non-pending raw_item returns immediately without work."""
        from app.tasks.parse import parse_xarid_item

        raw_item = _raw_item(XARID_PAYLOAD)
        raw_item.parse_status = "parsed"
        with (
            patch("app.tasks.parse.get_session") as mock_get_session,
            patch("app.tasks.parse.match_product") as mock_match,
        ):
            _patch_session(mock_get_session, raw_item)
            result = parse_xarid_item(101)

        assert result["status"] == "already_parsed"
        mock_match.assert_not_called()


# ── Fetch routing ────────────────────────────────────────────────────────────


class TestXaridFetchRouting:
    def test_fetch_enqueues_xarid_parser(self) -> None:
        """_execute_xarid_fetch routes new rows to parse_xarid_item, not parse_raw_item."""
        from app.tasks import ingest

        # get_adapter + Session are function-local imports in _execute_xarid_fetch,
        # so patch them at their source modules (resolved at call time).
        with (
            patch("app.ingest.registry.get_adapter", return_value=MagicMock()),
            patch("sqlalchemy.orm.Session") as mock_session_cls,
            patch("app.tasks.ingest._load_enabled_sources", return_value=[MagicMock(id=5)]),
            patch("app.tasks.ingest.run_source_fetch_isolated", return_value=0) as mock_run,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            ingest._execute_xarid_fetch("xarid_tenders")

        assert mock_run.call_args.kwargs.get("parse_task_name") == "parse_xarid_item"
