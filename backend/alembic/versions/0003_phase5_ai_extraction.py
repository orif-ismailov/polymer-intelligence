"""Add parse_runs.latency_ms + partial index for LLM parse journaling.

Phase 5 AI extraction extension:
- parse_runs.latency_ms (int, NULL): wall-clock LLM call latency in ms.
  Required by the AI-SPEC §1/§2 journaling contract alongside the already-present
  model/prompt_version/tokens_in/tokens_out columns.
- ix_parse_runs_llm_created: partial index on parse_runs.created_at WHERE
  parser='llm_extract' to support per-source 7-day token-spend query (05-04)
  and the needs_review feed query.

No new column is added to the signals table:
  lead_score, classification (HOT/MEDIUM/LOW), needs_review, model,
  prompt_version, and scored_at all live inside the existing signals.ai JSONB
  per db-architecture §4. The ix_signals_ai_gin GIN index already supports
  ai->>'lead_score' and ai->>'needs_review' lookups.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-18

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
Do NOT edit this migration to add/remove columns — add a new revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── parse_runs.latency_ms ─────────────────────────────────────────────────
    # Wall-clock LLM call latency in milliseconds. NULL for rule-based runs
    # (parser='uzex_table_v1') that do not involve a network call.
    # Phase-5 discriminator: parser='llm_extract' is the LLM journal discriminator
    # (vs 'uzex_table_v1' for UZEX rule-based runs).
    op.add_column(
        "parse_runs",
        sa.Column("latency_ms", sa.Integer(), nullable=True),
    )

    # ── ix_parse_runs_llm_created ─────────────────────────────────────────────
    # Partial index for LLM parse runs only (parser='llm_extract').
    # Supports:
    #   1. Per-source 7-day token-spend query in 05-04 task orchestrator:
    #      SELECT SUM(tokens_in + tokens_out) FROM parse_runs
    #      WHERE parser='llm_extract' AND created_at >= now() - interval '7 days'
    #   2. needs_review feed query filtering by LLM runs in the last N days.
    # The partial index is much smaller than a full-table index because most
    # historical rows will be rule-based runs, not LLM runs.
    op.create_index(
        "ix_parse_runs_llm_created",
        "parse_runs",
        ["created_at"],
        postgresql_where=sa.text("parser = 'llm_extract'"),
    )


def downgrade() -> None:
    # Drop index first, then column (reverse dependency order)
    op.drop_index(
        "ix_parse_runs_llm_created",
        table_name="parse_runs",
    )
    op.drop_column("parse_runs", "latency_ms")
