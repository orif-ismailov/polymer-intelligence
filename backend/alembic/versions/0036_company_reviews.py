"""Company reviews: «★ 4.8 · 128 отзывов» on a company profile.

    enums  review_status
    tables company_reviews

The Reviews tab has rendered an empty state since the profile sheet shipped, and
the header has carried a «рейтинг появится после сделок» placeholder. This is the
data behind both.

Two decisions worth reading before changing them:

`review_status` has NO `pending`. Everything moderated in this platform — reports,
offers, verification cases, lab orders — is OUR claim about a third party, so a
human signs it off. A review is the author's claim about their own counterparty;
we are not the publisher of record. Abuse is bounded by ELIGIBILITY instead: one
row per (subject, author company) pair, author ≠ subject, and the API requires
both to be verified. `hidden` exists so a takedown is an UPDATE, not a migration.

The aggregate is computed on read, not denormalised onto `companies`. A cached
average is a second source of truth that drifts the first time a row is hidden,
and the directory page already needs a grouped query per page — one more column
in that GROUP BY is free, while keeping a counter honest is not.

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-02

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | None = None
depends_on: str | None = None


_REVIEW_STATUS = ("published", "hidden")


def _enum(name: str) -> postgresql.ENUM:
    """Reference an already-created type inside a column definition."""
    return postgresql.ENUM(name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    postgresql.ENUM(*_REVIEW_STATUS, name="review_status").create(bind)

    op.create_table(
        "company_reviews",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("author_company_id", sa.BigInteger(), nullable=False),
        sa.Column("author_account_id", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _enum("review_status"),
            server_default="published",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "company_id <> author_company_id", name="ck_company_review_not_self"
        ),
        sa.CheckConstraint(
            "rating >= 1 AND rating <= 5", name="ck_company_review_rating_range"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["author_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["author_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "author_company_id", name="uq_company_review_pair"
        ),
    )
    op.create_index(
        "ix_company_reviews_company_status",
        "company_reviews",
        ["company_id", "status"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_company_reviews_company_status", table_name="company_reviews")
    op.drop_table("company_reviews")

    postgresql.ENUM(name="review_status").drop(bind)
