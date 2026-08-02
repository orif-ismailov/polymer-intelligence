"""Company cover image + the media table its capability thumbnails live in.

    tables  company_media
    columns companies.cover_storage_path

Two different shapes for two different needs, and the split is the point:

* the cover is 1:1 with the company, so it is a COLUMN — a table for a
  single-valued relationship buys nothing and costs a join;
* «Наши возможности» thumbnails are many per company, so they are ROWS.

`company_media` is deliberately not slotted. Keying rows on
`(company_id, kind, slot)` would make `slot` mirror an index into the JSONB
capability array, so the two would have to be kept in step in two places and
every reorder would orphan a row. Instead the JSONB stays the ordering authority
and stores `{capability_key: media_id}`; a media row is bytes with an owner.

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-02

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "companies", sa.Column("cover_storage_path", sa.Text(), nullable=True)
    )

    op.create_table(
        "company_media",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # ON DELETE CASCADE: unlike the other new tables, media is owned outright
        # by the company and has no meaning without it.
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_company_media_company", "company_media", ["company_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_company_media_company", table_name="company_media")
    op.drop_table("company_media")
    op.drop_column("companies", "cover_storage_path")
