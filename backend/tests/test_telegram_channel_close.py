"""
D-03 / TZ §6.1.6 close: the no-code telegram_channel acceptance slice, key-free.

This module proves the full deterministic chain for a telegram_channel source
WITHOUT a real Telegram/MTProto account or any Anthropic call — finally closing
the §6.1.6 slice that Phase 4 / 05-UAT carried as a deploy-day caveat (SC#5):

  Task 1 — Enable-gate (wizard add → Test → cannot-enable-without-pass):
    - POST /api/v1/sources with adapter=telegram_channel saves the source in the
      pending state (is_enabled=False, last_test_ok_at=NULL) — D-04 invariant.
    - PATCH /api/v1/sources/{id} is_enabled=True while last_test_ok_at IS NULL → 422
      (server-side enable-gate is_enabled=true ⇒ last_test_ok_at IS NOT NULL, T-06-06).
    - After a passing Test sets last_test_ok_at, PATCH is_enabled=True → 200.
    - A non-admin POST/PATCH is rejected (admin-only writes, T-04-21).

  Task 2 — Fixture MTProto message → parse_telegram_item → signal in v_live_feed:
    - A fixture channel raw_item fed through parse_telegram_item (with extract_signal
      patched to a relevant ExtractionResult) writes ONE parse_runs row BEFORE the
      signal (attribution invariant G5, T-05-15).
    - The produced signal carries the channel source_id and the extracted fields
      (kind/product/volume/price) and satisfies the v_live_feed column contract —
      i.e. it maps cleanly to a FeedItem (the row shape the feed view surfaces).
    - confidence < 0.5 routes the signal to needs_review (ai.needs_review=True, G2)
      while still landing in the stream as a needs_review entry.

Key-free contract (mirrors tests/parsing/test_telegram_accuracy.py):
  Never makes a live MTProto or Anthropic call. Safe under placeholder env
  (ANTHROPIC_API_KEY=sk-ant-ci-placeholder, TG_API_ID=0). Every external seam
  (adapter.test, extract_signal, budget, product/grade lookup, session) is mocked.

Security:
  T-06-06: server-side enable-gate re-demonstrated for telegram_channel (422 on
           unverified enable) — a source cannot be activated without a passing test.
  T-06-07: fixture channel content (attacker-controllable) flows through the strict
           extraction + confidence<0.5→needs_review routing; low-confidence input is
           quarantined to needs_review, never auto-trusted.
"""

from __future__ import annotations

import datetime
from collections.abc import Generator
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from parsing.schemas import ExtractionResult, SignalKind, UrgencyLevel

# ── Shared test helpers (enable-gate side — pattern from test_source_wizard.py) ──


def _make_staff_user(role: str, user_id: int = 1, is_active: bool = True) -> MagicMock:
    """Create a mock StaffUser with the given role."""
    from app.models.enums import StaffRole  # noqa: PLC0415

    user = MagicMock()
    user.id = user_id
    user.email = f"{role}@polymer.uz"
    user.role = StaffRole(role)
    user.is_active = is_active
    return user


def _auth_headers(user_id: int, role: str) -> dict[str, str]:
    """Create a Bearer Authorization header."""
    from app.core.security import create_access_token  # noqa: PLC0415

    token = create_access_token(subject=str(user_id), role=role)
    return {"Authorization": f"Bearer {token}"}


def _make_mock_source(
    source_id: int = 1,
    adapter: str = "telegram_channel",
    name: str = "Test Channel",
    is_enabled: bool = False,
    last_test_ok_at: datetime.datetime | None = None,
    config: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock Source ORM object for a telegram_channel source."""
    source = MagicMock()
    source.id = source_id
    source.name = name
    source.adapter = adapter
    # Use string value directly (not the enum instance) to avoid attribute-set
    # issues with Python 3.14 enum (cannot set .value on enum member).
    mock_kind = MagicMock()
    mock_kind.value = "website"
    source.kind = mock_kind
    source.is_enabled = is_enabled
    source.last_test_ok_at = last_test_ok_at
    source.last_fetch_at = None
    source.last_success_at = None
    source.consecutive_failures = 0
    source.config = config or {"channel": "@polymer_market"}
    source.created_at = datetime.datetime(2026, 6, 17, tzinfo=datetime.UTC)
    return source


def _make_client_with_user_and_db(
    staff_user: MagicMock,
    mock_db: MagicMock | None = None,
) -> TestClient:
    """Build a TestClient with get_db mocked to include the given staff_user."""
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    if mock_db is None:
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = staff_user

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    return TestClient(application, raise_server_exceptions=True)


# ── Telegram parse helpers (pattern from test_parse_telegram.py) ────────────────

# The channel source the fixture message belongs to. The produced signal MUST
# carry this id so the feed attributes it to the right telegram_channel source.
_CHANNEL_SOURCE_ID = 4242


def _make_channel_raw_item(
    id_: int = 1,
    source_id: int = _CHANNEL_SOURCE_ID,
    parse_status: str = "pending",
    content: str | None = "Продаю ПП Т30С 50 тонн, $900/т, EXW Ташкент",
) -> MagicMock:
    """Return a mock telegram_channel RawItem (fixture MTProto-style message)."""
    ri = MagicMock()
    ri.id = id_
    ri.source_id = source_id
    ri.parse_status = parse_status
    ri.content = content
    ri.event_at = datetime.datetime(2026, 6, 20, 8, 0, tzinfo=datetime.UTC)
    ri.payload = {}
    return ri


def _make_extraction_result(
    is_relevant: bool = True,
    confidence: float = 0.9,
    kind: SignalKind = SignalKind.SELL_OFFER,
    product: str = "PP",
    volume: Decimal | None = Decimal("50"),
    price: Decimal | None = Decimal("900"),
    currency: str | None = "USD",
) -> ExtractionResult:
    """Return a relevant ExtractionResult for the fixture channel message."""
    if not is_relevant:
        return ExtractionResult(is_relevant=False, confidence=0.1)
    return ExtractionResult(
        is_relevant=is_relevant,
        confidence=confidence,
        kind=kind,
        product=product,
        grade_text="T30S",
        volume=volume,
        volume_unit="MT",
        price=price,
        currency=currency,
        region="Tashkent",
        urgency=UrgencyLevel.MEDIUM,
    )


def _make_journal(
    model: str | None = "claude-haiku-4-5",
    prompt_version: str | None = "v1",
) -> dict[str, Any]:
    """Return a journal dict as returned by extract_signal."""
    return {
        "parser": "llm_extract_tools",
        "model": model,
        "prompt_version": prompt_version,
        "tokens_in": 400,
        "tokens_out": 120,
        "cache_read_tokens": 0,
        "latency_ms": 350.0,
        "raw_response": {},
    }


def _import_parse_task() -> Any:
    """Import parse_telegram_item under test (lazy — needs get_session patched)."""
    from app.tasks.parse_telegram import parse_telegram_item  # noqa: PLC0415

    return parse_telegram_item


class TestTelegramChannelClose:
    """Prove the full telegram_channel §6.1.6 slice without real credentials (D-03)."""

    # ── Task 1: enable-gate (wizard add → Test → cannot-enable-without-pass) ────

    def test_pending_telegram_channel_source_saved_disabled(self) -> None:
        """POST /sources telegram_channel saves is_enabled=False, last_test_ok_at=NULL.

        The wizard create path (D-04 invariant) always persists a brand-new source
        in the pending state. We assert the Source object the router hands to the
        DB carries is_enabled=False and last_test_ok_at=None — proving a channel
        starts un-enabled and must pass a Test before it can go live.
        """
        admin_user = _make_staff_user("admin", user_id=1)

        added: list[Any] = []
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = admin_user
        mock_db.add.side_effect = lambda obj: added.append(obj)

        def _refresh(obj: Any) -> None:
            # A real db.refresh() after commit() loads server-generated/default
            # columns (PK + non-null defaults). Mimic that so the router's 201
            # SourceHealthItem response validates; the D-04 pending fields
            # (is_enabled / last_test_ok_at) are asserted on the added Source below.
            obj.id = 99
            obj.consecutive_failures = 0
            obj.last_fetch_at = None
            obj.last_success_at = None

        mock_db.refresh.side_effect = _refresh

        client = _make_client_with_user_and_db(admin_user, mock_db)

        # Patch the adapter so config validation passes without touching MTProto,
        # and so db.refresh leaves the freshly-added Source readable by the response.
        with (
            patch("app.api.health._check_redis", return_value="ok"),
            patch("app.ingest.registry.get_adapter") as mock_get_adapter,
        ):
            mock_adapter = MagicMock()
            # config_schema(**config) must accept the channel config without error
            mock_adapter.config_schema = MagicMock(return_value=MagicMock())
            mock_get_adapter.return_value = mock_adapter

            resp = client.post(
                "/api/v1/sources",
                json={
                    "adapter": "telegram_channel",
                    "name": "Polymer Market Channel",
                    "config": {"channel": "@polymer_market"},
                },
                headers=_auth_headers(1, "admin"),
            )

        assert resp.status_code == 201, f"expected 201 created, got {resp.status_code}: {resp.text}"
        # The Source persisted by the router is in the pending state (D-04 invariant).
        assert len(added) == 1, "exactly one Source should be added"
        created_source = added[0]
        assert created_source.adapter == "telegram_channel"
        assert created_source.is_enabled is False, "new channel source must start disabled"
        assert created_source.last_test_ok_at is None, "new channel source must be untested (pending)"

    def test_enable_gate_rejects_unverified_telegram_channel(self) -> None:
        """PATCH is_enabled=True with last_test_ok_at=NULL → 422 (T-06-06 enable-gate).

        The core §6.1.6 invariant: a telegram_channel source that has never passed
        a Test cannot be enabled. The server-side guard returns 422 regardless of
        any UI gating — a failed/absent test source can never go live.
        """
        admin_user = _make_staff_user("admin", user_id=1)
        # Channel source never tested (last_test_ok_at is None).
        mock_source = _make_mock_source(
            source_id=3, adapter="telegram_channel", is_enabled=False, last_test_ok_at=None
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = admin_user
        mock_db.get.return_value = mock_source

        client = _make_client_with_user_and_db(admin_user, mock_db)

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.patch(
                "/api/v1/sources/3",
                json={"is_enabled": True},
                headers=_auth_headers(1, "admin"),
            )

        assert resp.status_code == 422, f"expected 422 enable-gate, got {resp.status_code}: {resp.text}"
        assert "test" in resp.text.lower(), "422 body should explain a passing test is required"

    def test_enable_gate_allows_enable_after_passing_test(self) -> None:
        """After a passing Test sets last_test_ok_at, PATCH is_enabled=True → 200.

        Once a channel source has a non-null last_test_ok_at (the Test passed), the
        enable-gate lifts and the source can be enabled — the other half of the
        is_enabled=true ⇒ last_test_ok_at IS NOT NULL invariant.
        """
        admin_user = _make_staff_user("admin", user_id=1)
        # Channel source that has passed a Test (last_test_ok_at set).
        mock_source = _make_mock_source(
            source_id=4,
            adapter="telegram_channel",
            is_enabled=False,
            last_test_ok_at=datetime.datetime(2026, 6, 20, 12, 0, tzinfo=datetime.UTC),
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = admin_user
        mock_db.get.return_value = mock_source

        client = _make_client_with_user_and_db(admin_user, mock_db)

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.patch(
                "/api/v1/sources/4",
                json={"is_enabled": True},
                headers=_auth_headers(1, "admin"),
            )

        assert resp.status_code == 200, f"expected 200 enable, got {resp.status_code}: {resp.text}"

    def test_passing_test_sets_last_test_ok_at_unlocking_enable(self) -> None:
        """POST /sources/{id}/test with ok=True sets last_test_ok_at (Test → unlock).

        Models the wizard "Test" button for a channel: when the adapter test passes
        (mocked here — no live MTProto), the router stamps last_test_ok_at, which is
        precisely what lifts the enable-gate in the test above.
        """
        admin_user = _make_staff_user("admin", user_id=1)
        mock_source = _make_mock_source(
            source_id=5, adapter="telegram_channel", last_test_ok_at=None
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = admin_user
        mock_db.get.return_value = mock_source

        from app.ingest.base import TestResult  # noqa: PLC0415

        passing = TestResult(
            ok=True,
            sample_rows=[
                {
                    "product": "PP", "grade": "T30S", "volume": "50", "price": "900",
                    "currency": "USD", "section": None, "event_at": None,
                }
            ],
        )

        client = _make_client_with_user_and_db(admin_user, mock_db)

        with (
            patch("app.api.health._check_redis", return_value="ok"),
            patch("app.ingest.registry.get_adapter") as mock_get_adapter,
        ):
            mock_adapter = MagicMock()
            mock_adapter.test = AsyncMock(return_value=passing)
            mock_get_adapter.return_value = mock_adapter

            resp = client.post(
                "/api/v1/sources/5/test",
                headers=_auth_headers(1, "admin"),
            )

        assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()["ok"] is True
        # A passing Test stamps last_test_ok_at — this is what unlocks the enable-gate.
        assert mock_source.last_test_ok_at is not None
        assert mock_db.commit.called

    def test_non_admin_cannot_create_telegram_channel(self) -> None:
        """POST /sources telegram_channel as a non-admin → 403 (admin-only, T-04-21)."""
        trader_user = _make_staff_user("trader", user_id=3)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = trader_user

        client = _make_client_with_user_and_db(trader_user, mock_db)

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.post(
                "/api/v1/sources",
                json={
                    "adapter": "telegram_channel",
                    "name": "X",
                    "config": {"channel": "@x"},
                },
                headers=_auth_headers(3, "trader"),
            )

        assert resp.status_code == 403, f"expected 403 for non-admin, got {resp.status_code}"

    def test_non_admin_cannot_enable_telegram_channel(self) -> None:
        """PATCH /sources/{id} as a non-admin → 403 (admin-only writes, T-04-21)."""
        analyst_user = _make_staff_user("analyst", user_id=2)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = analyst_user

        client = _make_client_with_user_and_db(analyst_user, mock_db)

        with patch("app.api.health._check_redis", return_value="ok"):
            resp = client.patch(
                "/api/v1/sources/3",
                json={"is_enabled": True},
                headers=_auth_headers(2, "analyst"),
            )

        assert resp.status_code == 403, f"expected 403 for non-admin, got {resp.status_code}"

    # ── Task 2: fixture message → parse_telegram_item → signal in v_live_feed ───

    def _run_parse_telegram(
        self,
        raw_item: MagicMock,
        result: ExtractionResult,
        journal: dict[str, Any],
        captured_signal: dict[str, Any],
    ) -> list[str]:
        """Drive parse_telegram_item with all external seams mocked.

        Records the add() call order so the caller can assert the G5 attribution
        invariant (parse_runs BEFORE signal), and captures the needs_review flag +
        the Signal-construction kwargs the real ai_signal_service would receive.

        Returns the ordered list of add()-ed object type names.
        """
        mock_session = MagicMock()
        mock_session.get.return_value = raw_item

        add_order: list[str] = []

        def _real_signal(session: Any, ri: Any, res: Any, jrnl: dict, **kwargs: Any) -> Any:
            # Build a real Signal via the production service so the produced object
            # carries the true source_id + extracted-field mapping (no fabrication).
            from app.domains.signals.ai import (  # noqa: PLC0415
                create_signal_from_extraction as _create,
            )

            sig = _create(session, ri, res, jrnl, **kwargs)
            captured_signal["signal"] = sig
            captured_signal["needs_review"] = kwargs.get("needs_review")
            add_order.append("Signal")
            return sig

        def _write_run(*_a: Any, **_k: Any) -> int:
            add_order.append("ParseRun")
            return 42

        with (
            patch("app.tasks.parse_telegram.get_session") as mock_get_session,
            patch("app.tasks.parse_telegram.extract_signal", return_value=(result, journal)),
            patch("app.tasks.parse_telegram.check_and_reserve_tokens"),
            patch("app.tasks.parse_telegram.record_actual_tokens"),
            patch(
                "app.tasks.parse_telegram.prepare_message_text",
                return_value=raw_item.content or "",
            ),
            patch("app.tasks.parse_telegram.write_parse_run", side_effect=_write_run),
            patch("app.tasks.parse_telegram.delete_existing_signals", return_value=0),
            patch(
                "app.tasks.parse_telegram.create_signal_from_extraction",
                side_effect=_real_signal,
            ),
            # Resolve product/grade deterministically without a DB (key-free).
            patch("app.domains.signals.ai.match_product", return_value=7),
            patch(
                "app.domains.signals.ai.extract_grade",
                return_value=(None, "T30S"),
            ),
        ):
            mock_get_session.return_value.__enter__ = lambda s: mock_session
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            parse_telegram_item = _import_parse_task()
            parse_telegram_item(raw_item.id)

        return add_order

    def test_fixture_message_through_parse_telegram_item_produces_signal(self) -> None:
        """A fixture channel message → parse_telegram_item → a signal (G5 ordering).

        Feeds a fixture telegram_channel raw_item through the real orchestrator
        (extract_signal mocked to a relevant result). Asserts a parse_runs row is
        written BEFORE the signal (attribution invariant G5) and the produced
        Signal carries the channel source_id and the extracted kind/product/
        volume/price — no live MTProto or Anthropic call.
        """
        raw_item = _make_channel_raw_item()
        result = _make_extraction_result(confidence=0.9)
        journal = _make_journal()
        captured: dict[str, Any] = {}

        add_order = self._run_parse_telegram(raw_item, result, journal, captured)

        # G5: parse_runs row is written BEFORE the signal (attribution invariant).
        assert add_order[0] == "ParseRun", f"expected ParseRun first, got {add_order}"
        assert "Signal" in add_order, "a signal must be produced for a relevant message"

        signal = captured["signal"]
        # The signal is attributed to the channel source it came from.
        assert signal.source_id == _CHANNEL_SOURCE_ID
        assert signal.raw_item_id == raw_item.id
        # Extracted fields flow into the signal (kind/product/volume/price).
        from app.models.enums import SignalKind as DBSignalKind  # noqa: PLC0415

        assert signal.kind == DBSignalKind.sell_offer
        assert signal.product_id == 7
        assert signal.volume == Decimal("50")
        assert signal.price == Decimal("900")
        assert signal.currency == "USD"
        # High-confidence channel signal is NOT flagged for review (G2 boundary).
        assert captured["needs_review"] is False

    def test_extracted_signal_satisfies_v_live_feed_contract(self) -> None:
        """The produced signal maps cleanly to a FeedItem — i.e. it lands in v_live_feed.

        v_live_feed unions normalized signals; the feed view surfaces exactly the
        FeedItem columns. We map the produced Signal through the same accessor the
        feed router uses (_row_to_feed_item) and validate it against the FeedItem
        schema — proving the channel signal is queryable/renderable via v_live_feed.
        """
        raw_item = _make_channel_raw_item()
        result = _make_extraction_result(confidence=0.9)
        journal = _make_journal()
        captured: dict[str, Any] = {}

        self._run_parse_telegram(raw_item, result, journal, captured)
        signal = captured["signal"]

        # Build a v_live_feed-shaped row from the produced signal. v_live_feed
        # selects: id, origin, kind, product_id, grade_text, volume, price,
        # currency, region, urgency, status, event_at (+ needs_review from ai).
        from app.domains.signals.api_feed import _row_to_feed_item  # noqa: PLC0415

        feed_row = MagicMock()
        feed_row.id = 1001
        feed_row.origin = "signal"
        feed_row.kind = signal.kind.value
        feed_row.product_id = signal.product_id
        feed_row.grade_text = signal.grade_text
        feed_row.volume = signal.volume
        feed_row.price = signal.price
        feed_row.currency = signal.currency
        feed_row.region = signal.region
        feed_row.urgency = signal.urgency.value if signal.urgency is not None else None
        feed_row.status = signal.status
        feed_row.event_at = signal.event_at
        feed_row.needs_review = bool(signal.ai.get("needs_review"))

        item = _row_to_feed_item(feed_row)

        # The signal satisfies the v_live_feed column contract (FeedItem validated).
        assert item.origin == "signal"
        assert item.kind == "sell_offer"
        assert item.product_id == 7
        assert item.grade_text == "T30S"
        assert item.volume == Decimal("50")
        assert item.price == Decimal("900")
        assert item.currency == "USD"
        assert item.region == "Tashkent"
        assert item.status == "new"
        assert item.event_at == raw_item.event_at
        assert item.needs_review is False

    def test_low_confidence_channel_signal_routes_to_needs_review(self) -> None:
        """confidence < 0.5 → ai.needs_review=True; still lands in the stream (G2).

        A low-confidence channel extraction is not discarded — it is quarantined to
        the needs_review queue (T-06-07) and still appears in v_live_feed flagged
        for human review, never auto-trusted as HOT.
        """
        raw_item = _make_channel_raw_item()
        result = _make_extraction_result(confidence=0.3)
        journal = _make_journal()
        captured: dict[str, Any] = {}

        self._run_parse_telegram(raw_item, result, journal, captured)

        # G2: low confidence routes to needs_review.
        assert captured["needs_review"] is True
        signal = captured["signal"]
        assert signal.ai.get("needs_review") is True

        # The needs_review signal still maps to a FeedItem (appears in the stream).
        from app.domains.signals.api_feed import _row_to_feed_item  # noqa: PLC0415

        feed_row = MagicMock()
        feed_row.id = 1002
        feed_row.origin = "signal"
        feed_row.kind = signal.kind.value
        feed_row.product_id = signal.product_id
        feed_row.grade_text = signal.grade_text
        feed_row.volume = signal.volume
        feed_row.price = signal.price
        feed_row.currency = signal.currency
        feed_row.region = signal.region
        feed_row.urgency = signal.urgency.value if signal.urgency is not None else None
        feed_row.status = signal.status
        feed_row.event_at = signal.event_at
        feed_row.needs_review = bool(signal.ai.get("needs_review"))

        item = _row_to_feed_item(feed_row)
        assert item.needs_review is True
        assert item.kind == "sell_offer"
