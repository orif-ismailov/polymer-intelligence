"""Phase 5 follow-ups: budget_deferred enum value + correct LLM partial-index predicate.

Two corrections to the Phase-5 AI extraction layer:

1. Add 'budget_deferred' to the parse_status ENUM.
   The G4 budget-degrade path (parse_telegram_item) marks a raw_item as
   'budget_deferred' when BudgetExceeded is raised: the rule-based fallback
   writes a needs_review signal and the item awaits nightly LLM catch-up.
   The original 0001 ENUM did not include this value, so every BudgetExceeded
   commit raised DataError. (CR-01)

   NOTE: `ALTER TYPE ... ADD VALUE` cannot run inside a transaction block, so
   this statement runs inside an Alembic autocommit_block().

2. Recreate ix_parse_runs_llm_created with a predicate that matches the value
   the code actually writes. Migration 0003 used `parser = 'llm_extract'`
   (exact equality) but the extractor writes 'llm_extract_tools' /
   'llm_extract_native' and the spend queries use `parser LIKE 'llm_extract%'`.
   The exact-equality index therefore indexed zero rows and could not serve the
   LIKE queries. Replace it with `parser LIKE 'llm_extract%'`. (CR-04)
   0003 is treated as immutable (its own header forbids editing it), so the
   index is corrected here in a new revision.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-19

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. parse_status ENUM: add 'budget_deferred' (CR-01) ───────────────────
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block. Alembic
    # wraps each migration in a transaction, so we suspend it here.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE parse_status ADD VALUE IF NOT EXISTS 'budget_deferred'")

    # ── 2. Recreate ix_parse_runs_llm_created with the correct predicate (CR-04) ─
    # 0003 created the index WHERE parser = 'llm_extract', which never matches
    # the written discriminators ('llm_extract_tools' / 'llm_extract_native').
    op.drop_index("ix_parse_runs_llm_created", table_name="parse_runs")
    op.create_index(
        "ix_parse_runs_llm_created",
        "parse_runs",
        ["created_at"],
        postgresql_where=sa.text("parser LIKE 'llm_extract%'"),
    )


def downgrade() -> None:
    # ── Revert the index to the 0003 predicate ────────────────────────────────
    op.drop_index("ix_parse_runs_llm_created", table_name="parse_runs")
    op.create_index(
        "ix_parse_runs_llm_created",
        "parse_runs",
        ["created_at"],
        postgresql_where=sa.text("parser = 'llm_extract'"),
    )

    # NOTE: PostgreSQL cannot DROP a value from an ENUM type. The
    # 'budget_deferred' value added in upgrade() is intentionally left in place
    # on downgrade (irreversible enum addition). Any rows in that state must be
    # migrated to another status before relying on the value being absent.
