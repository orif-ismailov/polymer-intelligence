"""Portal parity (R2 W1 T1.1): dual-origin requests & inquiries + notifications.

Extends the R1 dual-origin bridge (0017 did it for seller_offers) to the buy side
so the portal can create purchase requests and per-offer inquiries on behalf of a
company account, alongside the frozen Telegram Mini App origin:

  requests        + company_id, created_by_user_account_id; client_id → NULLABLE;
                  CHECK ck_request_origin (client OR account present).
  offer_requests  + company_id, created_by_user_account_id; client_id → NULLABLE;
                  CHECK ck_inquiry_origin (client OR account present).

Plus the new in-portal notification centre:

  portal_notifications  id, user_account_id (FK), kind (plain Text — extensible),
                        title_key/body_key (i18n keys, never pre-rendered text),
                        params (JSONB), entity/entity_id (deep-link), read_at,
                        created_at; index (user_account_id, read_at, id) for the
                        unread-count query + newest-first feed.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-25

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. Dual-origin on requests (buy-side purchase requests) ───────────────
    op.add_column("requests", sa.Column("company_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "requests", sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "fk_requests_company", "requests", "companies", ["company_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_requests_created_by_account",
        "requests",
        "user_accounts",
        ["created_by_user_account_id"],
        ["id"],
    )
    op.alter_column("requests", "client_id", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint(
        "ck_request_origin",
        "requests",
        "client_id IS NOT NULL OR created_by_user_account_id IS NOT NULL",
    )

    # ── 2. Dual-origin on offer_requests (per-offer inquiries) ────────────────
    op.add_column("offer_requests", sa.Column("company_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "offer_requests",
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_offer_requests_company", "offer_requests", "companies", ["company_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_offer_requests_created_by_account",
        "offer_requests",
        "user_accounts",
        ["created_by_user_account_id"],
        ["id"],
    )
    op.alter_column("offer_requests", "client_id", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint(
        "ck_inquiry_origin",
        "offer_requests",
        "client_id IS NOT NULL OR created_by_user_account_id IS NOT NULL",
    )

    # ── 3. portal_notifications ───────────────────────────────────────────────
    op.create_table(
        "portal_notifications",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title_key", sa.Text(), nullable=False),
        sa.Column("body_key", sa.Text(), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("entity", sa.Text(), nullable=True),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_portal_notifications_account_unread",
        "portal_notifications",
        ["user_account_id", "read_at", "id"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    # ── Reverse portal_notifications ──────────────────────────────────────────
    op.drop_index("ix_portal_notifications_account_unread", table_name="portal_notifications")
    op.drop_table("portal_notifications")

    # ── Reverse offer_requests dual-origin ────────────────────────────────────
    op.drop_constraint("ck_inquiry_origin", "offer_requests", type_="check")
    null_clients = bind.execute(
        sa.text("SELECT count(*) FROM offer_requests WHERE client_id IS NULL")
    ).scalar_one()
    if null_clients:
        raise RuntimeError(
            f"Cannot downgrade: {null_clients} offer_requests rows have NULL client_id "
            "(portal-origin inquiries). Reassign or delete them before downgrading 0018."
        )
    op.alter_column("offer_requests", "client_id", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("fk_offer_requests_created_by_account", "offer_requests", type_="foreignkey")
    op.drop_constraint("fk_offer_requests_company", "offer_requests", type_="foreignkey")
    op.drop_column("offer_requests", "created_by_user_account_id")
    op.drop_column("offer_requests", "company_id")

    # ── Reverse requests dual-origin ──────────────────────────────────────────
    op.drop_constraint("ck_request_origin", "requests", type_="check")
    null_clients = bind.execute(
        sa.text("SELECT count(*) FROM requests WHERE client_id IS NULL")
    ).scalar_one()
    if null_clients:
        raise RuntimeError(
            f"Cannot downgrade: {null_clients} requests rows have NULL client_id "
            "(portal-origin requests). Reassign or delete them before downgrading 0018."
        )
    op.alter_column("requests", "client_id", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("fk_requests_created_by_account", "requests", type_="foreignkey")
    op.drop_constraint("fk_requests_company", "requests", type_="foreignkey")
    op.drop_column("requests", "created_by_user_account_id")
    op.drop_column("requests", "company_id")
