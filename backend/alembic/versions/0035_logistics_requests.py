"""Logistics service requests: a buyer's cargo + route ask to one carrier.

    enums  logistics_request_status
    tables logistics_requests

The logistics directory has been readable since 0032 but had nothing to act on:
a carrier publishes no offers, so the profile's «Написать» resolved to an empty
product tab and there was no way to ask it for anything. This is that ask.

Modelled on `factory_rfqs` (0034) and lighter on purpose. A factory RFQ prices a
published offer and carries documents and commercial terms; a carrier quotes a
LANE, so the payload is the cargo and the two ends of the route, with no
`offer_id` to hang it on and no document slots
(`docs/new-design/logistics_request.png`).

`packaging_type` is text with a preset list on the client rather than a PG enum —
the same call `factory_rfqs.incoterms` and `qty_unit` make. Nothing filters or
aggregates on it, and adding «Big-bag» should not be a migration.

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-02

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | None = None
depends_on: str | None = None


_LOGISTICS_REQUEST_STATUS = (
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

    postgresql.ENUM(
        *_LOGISTICS_REQUEST_STATUS, name="logistics_request_status"
    ).create(bind)

    op.create_table(
        "logistics_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("buyer_company_id", sa.BigInteger(), nullable=False),
        sa.Column("logistics_company_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("cargo_name", sa.Text(), nullable=False),
        sa.Column("volume", sa.Numeric(14, 3), nullable=False),
        sa.Column(
            "volume_unit", sa.Text(), server_default="MT", nullable=False
        ),
        sa.Column("packaging_type", sa.Text(), nullable=True),
        sa.Column("special_requirements", sa.Text(), nullable=True),
        sa.Column("from_country", sa.Text(), nullable=False),
        sa.Column("from_city", sa.Text(), nullable=True),
        sa.Column("to_country", sa.Text(), nullable=False),
        sa.Column("to_city", sa.Text(), nullable=True),
        sa.Column("contact_phone", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _enum("logistics_request_status"),
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
        sa.CheckConstraint(
            "buyer_company_id <> logistics_company_id",
            name="ck_logistics_request_parties_distinct",
        ),
        sa.CheckConstraint("volume > 0", name="ck_logistics_request_volume_positive"),
        sa.ForeignKeyConstraint(["buyer_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["logistics_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(
            ["created_by_user_account_id"], ["user_accounts.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("number"),
    )
    op.create_index(
        "ix_logistics_requests_buyer_status",
        "logistics_requests",
        ["buyer_company_id", "status"],
    )
    op.create_index(
        "ix_logistics_requests_carrier_status",
        "logistics_requests",
        ["logistics_company_id", "status"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_logistics_requests_carrier_status", table_name="logistics_requests")
    op.drop_index("ix_logistics_requests_buyer_status", table_name="logistics_requests")
    op.drop_table("logistics_requests")

    postgresql.ENUM(name="logistics_request_status").drop(bind)
