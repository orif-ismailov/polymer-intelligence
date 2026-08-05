"""Laboratory analysis requests: broadcast to every lab, with a thread per lab.

    enums  lab_request_status
    tables lab_requests, lab_request_threads, lab_request_messages

`labaratory_request.png` steps 1–2. A buyer states the material and the methods
once; every verified laboratory sees it; each interested lab opens its own
conversation. The shape is `0038_logistics_broadcast` applied to a second
directory, for the same reason: a buyer with material to test does not know which
of ten laboratories runs that method.

**This is NOT `lab_orders` and does not touch it.** That table (P6, 0028) is
staff-driven, hangs off an offer or a deal, is worked by partner laboratories we
phone, and is the only path that can set `seller_offers.lab_verified`. Partner
labs have no account, so they cannot answer a broadcast at all — only a company
with a CONFIRMED `laboratory` role can, which is why this flow addresses
`companies` rather than `lab_partners`. The two coexist.

Contacts are COLLECTED here rather than snapshotted from the account, unlike
`logistics_requests.contact_phone`: the sheet asks for name, email and phone
explicitly, and `user_accounts` has a nullable name and no email column, so
there would be nothing to snapshot.

No money column. The mockup is explicit that payment happens off-platform
(«оплата напрямую лаборатории, IMEX AI не принимает и не хранит платежи»).

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-03

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | None = None
depends_on: str | None = None


_LAB_REQUEST_STATUS = (
    "submitted",
    "viewed",
    "in_progress",
    "quoted",
    "closed",
    "rejected",
)


def _enum(name: str) -> postgresql.ENUM:
    """Reference an already-created type inside a column definition."""
    return postgresql.ENUM(name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    postgresql.ENUM(*_LAB_REQUEST_STATUS, name="lab_request_status").create(bind)

    op.create_table(
        "lab_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("buyer_company_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_text", sa.Text(), nullable=False),
        sa.Column("grade_text", sa.Text(), nullable=True),
        sa.Column("study_type", sa.Text(), nullable=True),
        sa.Column("methods", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sample_qty", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column(
            "is_urgent", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("desired_date", sa.Date(), nullable=True),
        sa.Column("contact_name", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.Text(), nullable=True),
        sa.Column("contact_phone", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _enum("lab_request_status"),
            server_default="submitted",
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
        sa.ForeignKeyConstraint(["buyer_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["created_by_user_account_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("number"),
    )
    op.create_index("ix_lab_requests_open", "lab_requests", ["status", "created_at"])
    op.create_index(
        "ix_lab_requests_buyer_status", "lab_requests", ["buyer_company_id", "status"]
    )

    op.create_table(
        "lab_request_threads",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("lab_request_id", sa.BigInteger(), nullable=False),
        sa.Column("laboratory_company_id", sa.BigInteger(), nullable=False),
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
            ["lab_request_id"], ["lab_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["laboratory_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["created_by_user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "lab_request_id",
            "laboratory_company_id",
            name="uq_lab_thread_request_laboratory",
        ),
    )
    op.create_index("ix_lab_threads_request", "lab_request_threads", ["lab_request_id"])
    op.create_index(
        "ix_lab_threads_laboratory",
        "lab_request_threads",
        ["laboratory_company_id", "updated_at"],
    )

    op.create_table(
        "lab_request_messages",
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
            name="ck_lab_message_not_empty",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["lab_request_threads.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_account_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["author_company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_messages_thread", "lab_request_messages", ["thread_id", "id"])


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_lab_messages_thread", table_name="lab_request_messages")
    op.drop_table("lab_request_messages")
    op.drop_index("ix_lab_threads_laboratory", table_name="lab_request_threads")
    op.drop_index("ix_lab_threads_request", table_name="lab_request_threads")
    op.drop_table("lab_request_threads")
    op.drop_index("ix_lab_requests_buyer_status", table_name="lab_requests")
    op.drop_index("ix_lab_requests_open", table_name="lab_requests")
    op.drop_table("lab_requests")

    postgresql.ENUM(name="lab_request_status").drop(bind)
