"""
Offline tests for migration 0003: parse_runs.latency_ms + ix_parse_runs_llm_created.

Tests validate:
1. The revision/down_revision chain (0003 → 0002).
2. upgrade() and downgrade() are callable.
3. The ParseRun ORM model has a latency_ms attribute mapped to an Integer column.
4. No new column was added to the signals table (lead_score/needs_review live in ai JSONB).

These are OFFLINE tests — no live database is required. They mirror the pattern
from test_synonyms_migration.py but skip the DB-connect portion (test_synonyms_migration.py
is already the live-DB integration test template; this test is structure-only).

For the live upgrade drill (alembic upgrade head + \\d parse_runs in Postgres):
see the human-check in 05-01-PLAN.md Task 2 — deferred to deploy time per the
established phase UAT deferral pattern.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory


# ── Helpers ───────────────────────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).parent.parent


def _get_alembic_script_dir() -> ScriptDirectory:
    """Return an Alembic ScriptDirectory for the backend."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


# ── Revision chain tests ──────────────────────────────────────────────────────


class TestMigration0003RevisionChain:
    """Verify the 0003 revision chain is intact."""

    def test_revision_is_0003(self) -> None:
        """0003 module has revision = '0003'."""
        import backend.alembic.versions as _versions_pkg  # noqa: F401 — ensure path

        # Import directly from the file path to avoid __init__ side effects
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migration_0003",
            BACKEND_DIR / "alembic" / "versions" / "0003_phase5_ai_extraction.py",
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        assert module.revision == "0003", (
            f"Expected revision '0003', got {module.revision!r}"
        )

    def test_down_revision_is_0002(self) -> None:
        """0003 module has down_revision = '0002'."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migration_0003",
            BACKEND_DIR / "alembic" / "versions" / "0003_phase5_ai_extraction.py",
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        assert module.down_revision == "0002", (
            f"Expected down_revision '0002', got {module.down_revision!r}"
        )

    def test_upgrade_and_downgrade_are_callable(self) -> None:
        """upgrade() and downgrade() functions exist and are callable."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migration_0003",
            BACKEND_DIR / "alembic" / "versions" / "0003_phase5_ai_extraction.py",
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        assert callable(module.upgrade), "upgrade() must be callable"
        assert callable(module.downgrade), "downgrade() must be callable"

    def test_revision_walk_includes_0003_and_0002(self) -> None:
        """Alembic script walk includes both 0003 and 0002 (chain intact)."""
        script_dir = _get_alembic_script_dir()
        revisions = {r.revision for r in script_dir.walk_revisions()}
        assert "0003" in revisions, f"Revision 0003 not found. Available: {revisions}"
        assert "0002" in revisions, f"Revision 0002 not found. Available: {revisions}"

    def test_0003_is_not_head_after_0004(self) -> None:
        """0003 is no longer head once 0004 is added; 0004 is the head."""
        script_dir = _get_alembic_script_dir()
        heads = script_dir.get_heads()
        assert "0004" in heads, (
            f"Revision 0004 is not the head. Current heads: {heads}"
        )
        assert "0003" not in heads, (
            f"Revision 0003 should no longer be head after 0004. Current heads: {heads}"
        )


class TestMigration0004RevisionChain:
    """Verify the 0004 follow-up migration (budget_deferred enum + index fix)."""

    @staticmethod
    def _load_0004():  # type: ignore[no-untyped-def]
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migration_0004",
            BACKEND_DIR
            / "alembic"
            / "versions"
            / "0004_phase5_budget_deferred_and_index_fix.py",
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module

    def test_revision_is_0004(self) -> None:
        module = self._load_0004()
        assert module.revision == "0004", (
            f"Expected revision '0004', got {module.revision!r}"
        )

    def test_down_revision_is_0003(self) -> None:
        module = self._load_0004()
        assert module.down_revision == "0003", (
            f"Expected down_revision '0003', got {module.down_revision!r}"
        )

    def test_upgrade_and_downgrade_are_callable(self) -> None:
        module = self._load_0004()
        assert callable(module.upgrade), "upgrade() must be callable"
        assert callable(module.downgrade), "downgrade() must be callable"

    def test_revision_walk_includes_0004(self) -> None:
        script_dir = _get_alembic_script_dir()
        revisions = {r.revision for r in script_dir.walk_revisions()}
        assert "0004" in revisions, (
            f"Revision 0004 not found. Available: {revisions}"
        )


# ── ORM model tests ───────────────────────────────────────────────────────────


class TestParseRunORMModel:
    """Verify the ParseRun ORM model has the latency_ms attribute."""

    def test_parse_run_has_latency_ms_attribute(self) -> None:
        """ParseRun model has a latency_ms attribute."""
        from app.models.sources import ParseRun

        assert hasattr(ParseRun, "latency_ms"), (
            "ParseRun model must have a latency_ms attribute (added in migration 0003)"
        )

    def test_latency_ms_maps_to_integer_column(self) -> None:
        """ParseRun.latency_ms is mapped to an Integer column."""
        from app.models.sources import ParseRun

        # Access the SQLAlchemy mapped property
        mapper = ParseRun.__mapper__
        latency_col = mapper.columns.get("latency_ms")
        assert latency_col is not None, (
            "latency_ms column not found in ParseRun mapper.columns"
        )
        assert isinstance(latency_col.type, sa.Integer), (
            f"latency_ms must be Integer, got {type(latency_col.type).__name__}"
        )

    def test_latency_ms_is_nullable(self) -> None:
        """ParseRun.latency_ms is nullable (NULL for rule-based runs)."""
        from app.models.sources import ParseRun

        mapper = ParseRun.__mapper__
        latency_col = mapper.columns.get("latency_ms")
        assert latency_col is not None
        assert latency_col.nullable is True, (
            "latency_ms must be nullable (rule-based runs have no latency)"
        )


# ── Schema boundary tests ─────────────────────────────────────────────────────


class TestSchemaNoSignalsColumnChange:
    """Verify migration 0003 does NOT add new columns to the signals table.

    lead_score, needs_review, model, prompt_version, scored_at all live inside
    the existing signals.ai JSONB (db-architecture §4). The GIN index
    ix_signals_ai_gin already supports ai->>'lead_score' lookups.
    """

    def test_migration_0003_does_not_alter_signals_table(self) -> None:
        """upgrade() source code does not reference 'signals' table."""
        migration_path = (
            BACKEND_DIR / "alembic" / "versions" / "0003_phase5_ai_extraction.py"
        )
        source = migration_path.read_text(encoding="utf-8")

        # The only permitted reference to 'signals' is in comments explaining
        # WHY we are NOT touching the signals table.
        # Find lines that call op.* functions on 'signals':
        import re
        op_signals = re.findall(
            r'\bop\.\w+\([^)]*["\']signals["\']',
            source,
        )
        assert len(op_signals) == 0, (
            f"migration 0003 contains op.*('signals'...) calls: {op_signals}. "
            "New columns for AI enrichment live in signals.ai JSONB, not new columns."
        )

    def test_migration_0003_only_touches_parse_runs(self) -> None:
        """upgrade() source code only modifies parse_runs table.

        Check op.add_column and op.drop_column calls; exclude op.create_index and
        op.drop_index which use index names as first arg (not table names).
        """
        migration_path = (
            BACKEND_DIR / "alembic" / "versions" / "0003_phase5_ai_extraction.py"
        )
        source = migration_path.read_text(encoding="utf-8")

        # Extract table names only from add_column/drop_column/create_table/drop_table
        import re
        op_table_modifiers = re.findall(
            r'\bop\.(?:add_column|drop_column|create_table|drop_table|alter_column)\s*\(\s*["\'](\w+)["\']',
            source,
        )
        non_parse_runs = [t for t in op_table_modifiers if t not in ("parse_runs",)]
        assert len(non_parse_runs) == 0, (
            f"migration 0003 modifies unexpected tables: {non_parse_runs}. "
            "Only parse_runs should be modified in this migration."
        )
