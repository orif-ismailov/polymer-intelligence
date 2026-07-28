"""
Offline tests for migration 0024: escrow payments (P3 W1 — T1.1).

1. Revision chain 0024 → 0023 and 0024 is the single alembic head.
2. `escrow_payments` carries the invariants the money path depends on: exactly
   one payment per deal, the mode frozen at creation, and a staff id + timestamp
   per marked transition (the stub-mode evidence trail).
3. `provider_events` is a webhook INBOX: unique per (provider, external_id), so a
   bank retrying a callback cannot be applied twice. It is created here rather
   than in P7 because the idempotency guarantee belongs to the schema, not to
   whichever adapter arrives later.
4. NO bank account numbers anywhere — the platform never stores them.

(`app.*` is imported inside the tests: the conftest env patch is a session
fixture and does not exist at collection time.)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0024_escrow.py"


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0024", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


def _metadata():  # noqa: ANN202
    import app.models  # noqa: F401, PLC0415
    from app.core.db import Base  # noqa: PLC0415

    return Base.metadata


class TestRevisionChain:
    def test_revision_and_down_revision(self) -> None:
        module = _load_migration()
        assert module.revision == "0024"
        assert module.down_revision == "0023"

    def test_upgrade_downgrade_callable(self) -> None:
        module = _load_migration()
        assert callable(module.upgrade)
        assert callable(module.downgrade)

    def test_0024_is_single_head(self) -> None:
        script = _script_dir()
        assert script.get_heads() == ["0029"], (
            f"expected a single head 0027, got {script.get_heads()}"
        )


class TestEscrowStatusEnum:
    def test_values(self) -> None:
        from app.models.enums import EscrowStatus  # noqa: PLC0415

        assert [m.value for m in EscrowStatus] == [
            "pending",
            "funded",
            "released",
            "refunded",
        ]


class TestEscrowPaymentsTable:
    def test_registered(self) -> None:
        assert "escrow_payments" in _metadata().tables

    def test_one_payment_per_deal(self) -> None:
        table = _metadata().tables["escrow_payments"]
        uniques = {
            tuple(c.name for c in con.columns)
            for con in table.constraints
            if type(con).__name__ == "UniqueConstraint"
        }
        unique_indexes = {
            tuple(c.name for c in ix.columns) for ix in table.indexes if ix.unique
        }
        assert ("deal_id",) in uniques | unique_indexes, (
            "a deal must never have two escrow payments — the whole money path "
            "resolves the payment BY deal"
        )

    def test_deal_link_is_required(self) -> None:
        table = _metadata().tables["escrow_payments"]
        assert table.c.deal_id.nullable is False
        fks = [fk for fk in table.foreign_keys if fk.column.table.name == "deals"]
        assert fks, "escrow_payments must reference deals"

    def test_amount_is_exact(self) -> None:
        # Money is Numeric, never float: a rounded escrow amount is a wrong amount.
        table = _metadata().tables["escrow_payments"]
        assert "NUMERIC" in str(table.c.amount.type).upper()
        assert table.c.amount.nullable is False
        assert table.c.currency.nullable is False

    def test_mode_is_frozen_at_creation(self) -> None:
        # Which rail the payment was opened on decides how it can be marked; a
        # later flip of the runtime setting must not rewrite history.
        table = _metadata().tables["escrow_payments"]
        assert table.c.mode.nullable is False
        assert table.c.mode.server_default is not None
        assert "stub" in str(table.c.mode.server_default.arg)

    def test_status_defaults_to_pending(self) -> None:
        table = _metadata().tables["escrow_payments"]
        assert table.c.status.nullable is False
        assert "pending" in str(table.c.status.server_default.arg)

    def test_each_marked_transition_records_who_and_when(self) -> None:
        table = _metadata().tables["escrow_payments"]
        for stage in ("funded", "released", "refunded"):
            assert f"{stage}_at" in table.c, f"{stage}_at missing"
            assert f"{stage}_marked_by" in table.c, f"{stage}_marked_by missing"
            assert table.c[f"{stage}_at"].nullable is True
            assert table.c[f"{stage}_marked_by"].nullable is True

    def test_no_bank_account_details_are_stored(self) -> None:
        """The platform never holds counterparty account numbers (P3 T1.1)."""
        columns = set(_metadata().tables["escrow_payments"].c.keys())
        forbidden = {"account_number", "iban", "bank_account", "card_number", "mfo"}
        assert not (columns & forbidden), f"banking details leaked into the schema: {columns & forbidden}"

    def test_provider_ref_is_nullable(self) -> None:
        # The bank's own operation id — absent in stub mode, present in live.
        assert _metadata().tables["escrow_payments"].c.provider_ref.nullable is True


class TestProviderEventsInbox:
    def test_registered(self) -> None:
        assert "provider_events" in _metadata().tables

    def test_unique_per_provider_and_external_id(self) -> None:
        table = _metadata().tables["provider_events"]
        uniques = {
            tuple(c.name for c in con.columns)
            for con in table.constraints
            if type(con).__name__ == "UniqueConstraint"
        }
        unique_indexes = {
            tuple(c.name for c in ix.columns) for ix in table.indexes if ix.unique
        }
        assert ("provider", "external_id") in uniques | unique_indexes, (
            "a retried webhook must collide instead of being applied twice"
        )

    def test_processing_is_tracked(self) -> None:
        table = _metadata().tables["provider_events"]
        assert table.c.processed.nullable is False
        assert "false" in str(table.c.processed.server_default.arg).lower()
        assert table.c.processed_at.nullable is True
        assert table.c.error.nullable is True

    def test_payload_is_kept_verbatim(self) -> None:
        # The raw callback body is evidence; it is stored as JSONB, not parsed away.
        table = _metadata().tables["provider_events"]
        assert "JSON" in str(table.c.payload.type).upper()


class TestEventTypes:
    def test_escrow_events_are_known_to_the_dispatcher(self) -> None:
        """An event type absent from ALL_EVENT_TYPES is logged unroutable and
        dropped — every escrow notification in W2 would silently never fire."""
        from app.services import event_types  # noqa: PLC0415

        for name in ("ESCROW_OPENED", "ESCROW_FUNDED", "ESCROW_RELEASED", "ESCROW_REFUNDED"):
            assert hasattr(event_types, name), name
            assert getattr(event_types, name) in event_types.ALL_EVENT_TYPES, name
