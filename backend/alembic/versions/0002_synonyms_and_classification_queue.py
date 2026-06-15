"""Add product_synonyms + manual_classification_queue tables.

Schema v1.2 additions (not in locked DDL v1.1):
- product_synonyms: synonym dictionary for polymer product relevance routing
- manual_classification_queue: queue for unrecognized goods (NOT a source_failure)

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
Do NOT edit this migration to add/remove columns — add a new revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── product_synonyms ──────────────────────────────────────────────────────
    # Admin-top-up-able synonym dictionary for polymer relevance routing.
    # UNIQUE(synonym_norm) prevents duplicate normalized forms.

    op.create_table(
        "product_synonyms",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("product_id", sa.SmallInteger(), nullable=False),
        sa.Column("synonym", sa.Text(), nullable=False),
        sa.Column("synonym_norm", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.Text(),
            nullable=False,
            server_default="seed",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("synonym_norm", name="uq_product_synonyms_norm"),
    )

    # Index for O(log n) synonym_norm lookups (used by match_product on every call)
    op.create_index(
        "ix_product_synonyms_norm",
        "product_synonyms",
        ["synonym_norm"],
    )

    # ── manual_classification_queue ────────────────────────────────────────────
    # Queue for unrecognized raw_items — never triggers source_failure.
    # UNIQUE(raw_item_id) prevents duplicate queue entries per item.

    op.create_table(
        "manual_classification_queue",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("raw_item_id", sa.BigInteger(), nullable=False),
        sa.Column("product_text", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["raw_item_id"], ["raw_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("raw_item_id", name="uq_manual_classification_raw_item"),
    )

    # Index for pending-item worker queries (status + created_at for chronological processing)
    op.create_index(
        "ix_manual_classification_queue_status_created",
        "manual_classification_queue",
        ["status", "created_at"],
    )


def downgrade() -> None:
    # Drop indexes first, then tables in reverse dependency order

    op.drop_index(
        "ix_manual_classification_queue_status_created",
        table_name="manual_classification_queue",
    )
    op.drop_table("manual_classification_queue")

    op.drop_index(
        "ix_product_synonyms_norm",
        table_name="product_synonyms",
    )
    op.drop_table("product_synonyms")
