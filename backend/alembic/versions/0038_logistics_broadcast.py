"""Logistics requests become a broadcast, with a private thread per carrier.

    tables  logistics_request_threads, logistics_request_messages
    columns logistics_requests.logistics_company_id  (DROPPED)

0035 shipped this addressed to ONE carrier, which asked the buyer a question
they cannot answer: a shipper with cargo to move does not know which of ten
carriers runs that lane. The request is now stated once and every verified
logistics company sees it, which is also what gives a carrier something to put
on its otherwise-empty «Заявки» page.

Each interested carrier opens its own conversation. The unique key is
`(request, carrier)` rather than the company pair `manufacturer_threads` uses:
the subject here is the request, and the same two companies may be discussing
several jobs at once. Private per carrier so a buyer negotiates separately and
nobody reads a competitor's terms.

NOT REVERSIBLE. `downgrade()` re-adds `logistics_company_id` as NULLABLE and
leaves it empty — the values are gone, and a fabricated carrier on an existing
request would be worse than an absent one. The NOT NULL and the
`buyer <> logistics` CHECK cannot come back while any row is broadcast.

No `visibility` column, deliberately. `requests` has that triple
(`visibility` / `visible_company_ids`) and it is dead from the UI — the buyer
wizard folds the choice into `comment` free text — so a second unused mechanism
would cost a migration and buy nothing. Every logistics request is visible to
every confirmed carrier; restricting one is a migration with a screen behind it.

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-03

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── Drop the targeting ────────────────────────────────────────────────────
    op.drop_index("ix_logistics_requests_carrier_status", table_name="logistics_requests")
    op.drop_constraint(
        "ck_logistics_request_parties_distinct", "logistics_requests", type_="check"
    )
    op.drop_column("logistics_requests", "logistics_company_id")

    # The pool query: open requests, newest first.
    op.create_index(
        "ix_logistics_requests_open", "logistics_requests", ["status", "created_at"]
    )

    # ── Per-carrier conversations ─────────────────────────────────────────────
    op.create_table(
        "logistics_request_threads",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("logistics_request_id", sa.BigInteger(), nullable=False),
        sa.Column("carrier_company_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["logistics_request_id"], ["logistics_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["carrier_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["created_by_user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "logistics_request_id",
            "carrier_company_id",
            name="uq_logistics_thread_request_carrier",
        ),
    )
    op.create_index(
        "ix_logistics_threads_request", "logistics_request_threads", ["logistics_request_id"]
    )
    op.create_index(
        "ix_logistics_threads_carrier",
        "logistics_request_threads",
        ["carrier_company_id", "updated_at"],
    )

    op.create_table(
        "logistics_request_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("thread_id", sa.BigInteger(), nullable=False),
        sa.Column("author_account_id", sa.BigInteger(), nullable=False),
        sa.Column("author_company_id", sa.BigInteger(), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("file_storage_path", sa.Text(), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "body <> '' OR file_storage_path IS NOT NULL",
            name="ck_logistics_message_not_empty",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["logistics_request_threads.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_account_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["author_company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_logistics_messages_thread", "logistics_request_messages", ["thread_id", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_logistics_messages_thread", table_name="logistics_request_messages")
    op.drop_table("logistics_request_messages")
    op.drop_index("ix_logistics_threads_carrier", table_name="logistics_request_threads")
    op.drop_index("ix_logistics_threads_request", table_name="logistics_request_threads")
    op.drop_table("logistics_request_threads")

    op.drop_index("ix_logistics_requests_open", table_name="logistics_requests")
    # Nullable and empty — see the module docstring. The NOT NULL and the
    # parties-distinct CHECK cannot be restored over broadcast rows.
    op.add_column(
        "logistics_requests", sa.Column("logistics_company_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "logistics_requests_logistics_company_id_fkey",
        "logistics_requests",
        "companies",
        ["logistics_company_id"],
        ["id"],
    )
    op.create_index(
        "ix_logistics_requests_carrier_status",
        "logistics_requests",
        ["logistics_company_id", "status"],
    )
