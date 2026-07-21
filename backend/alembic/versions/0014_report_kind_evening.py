"""Add 'evening' to the report_kind enum (Phase 8c — Evening Market Brief).

The news engine now generates two scheduled briefs a day: a morning report (08:00
Tashkent) and an evening report (18:00). Evening reports are tagged kind='evening'
so the dashboard/webapp can label the session.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-21

Additive enum change only — no data rewrite. PostgreSQL 12+ allows ALTER TYPE ... ADD
VALUE inside a transaction. Enum values cannot be dropped, so downgrade is a no-op.
IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE report_kind ADD VALUE IF NOT EXISTS 'evening'")


def downgrade() -> None:
    # PostgreSQL cannot remove a value from an enum type; nothing to undo.
    pass
