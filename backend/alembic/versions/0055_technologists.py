"""Technologists — a marketplace of independent process experts.

A factory posts «нужен технолог»; every published expert sees it; each interested
expert sends an offer and talks to the factory in their own thread; the factory
accepts one, which reveals both sides' contacts, and later marks the work done
with a 1–5 review. The platform is the meeting place, not the employer: contract
and payment happen off-platform.

* `user_accounts.applied_as` — an access request now says who is asking. A
  technologist is a private person with NO company, so the cabinet has to know
  not to send them to company registration.
* `technologist_profiles` — one per account, moderated; `published_snapshot`
  is the card the catalog serves, so an edit awaiting review never leaks.
* `tech_requests` / `tech_request_invites` / `tech_offers` / `tech_threads` /
  `tech_messages` / `tech_reviews`.

Closed sets are `text` + CHECK (or Python-validated `text[]`), never PG ENUMs:
adding a process is a code change, not a migration.

Revision ID: 0055
Revises: 0054
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def _ts() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def _text_array(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")
    )


def upgrade() -> None:
    op.add_column(
        "user_accounts",
        sa.Column("applied_as", sa.Text(), nullable=False, server_default="company"),
    )
    op.create_check_constraint(
        "ck_user_accounts_applied_as",
        "user_accounts",
        "applied_as IN ('company', 'technologist')",
    )

    op.create_table(
        "technologist_profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_account_id",
            sa.BigInteger(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("photo_key", sa.Text(), nullable=True),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("projects_count", sa.Integer(), nullable=True),
        sa.Column("countries_count", sa.Integer(), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        _text_array("industries"),
        _text_array("processes"),
        _text_array("materials"),
        _text_array("equipment_brands"),
        _text_array("work_formats"),
        _text_array("languages"),
        sa.Column("contact_phone", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reviewed_by", sa.BigInteger(), sa.ForeignKey("staff_users.id"), nullable=True
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("published_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("rating_avg", sa.Numeric(3, 2), nullable=True),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        *_ts(),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_review', 'published', 'rejected', 'suspended')",
            name="ck_technologist_profile_status",
        ),
        sa.CheckConstraint(
            "years_experience IS NULL OR years_experience BETWEEN 0 AND 80",
            name="ck_technologist_profile_years",
        ),
    )
    op.create_index(
        "ix_technologist_profiles_status", "technologist_profiles", ["status", "updated_at"]
    )

    op.create_table(
        "tech_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column("number", sa.Text(), nullable=False, unique=True),
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column(
            "created_by_user_account_id",
            sa.BigInteger(),
            sa.ForeignKey("user_accounts.id"),
            nullable=False,
        ),
        sa.Column("need_type", sa.Text(), nullable=False),
        sa.Column("process", sa.Text(), nullable=False),
        sa.Column("equipment", sa.Text(), nullable=False),
        sa.Column("equipment_model", sa.Text(), nullable=True),
        sa.Column("product", sa.Text(), nullable=False),
        sa.Column("current_material", sa.Text(), nullable=True),
        sa.Column("target_material", sa.Text(), nullable=True),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("capacity", sa.Numeric(14, 3), nullable=True),
        sa.Column("capacity_unit", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("urgency", sa.Text(), nullable=False),
        sa.Column("needed_by", sa.Date(), nullable=True),
        sa.Column("work_format", sa.Text(), nullable=False),
        _text_array("languages"),
        sa.Column("budget_note", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default="form"),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("assigned_offer_id", sa.BigInteger(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        *_ts(),
        sa.CheckConstraint(
            "status IN ('open', 'assigned', 'completed', 'cancelled')",
            name="ck_tech_request_status",
        ),
        sa.CheckConstraint("source IN ('form', 'ai')", name="ck_tech_request_source"),
        sa.CheckConstraint(
            "work_format IN ('online', 'on_site', 'both')", name="ck_tech_request_format"
        ),
        sa.CheckConstraint(
            "urgency IN ('urgent', 'week', 'month', 'date')", name="ck_tech_request_urgency"
        ),
        sa.CheckConstraint(
            "capacity IS NULL OR capacity > 0", name="ck_tech_request_capacity_positive"
        ),
    )
    op.create_index("ix_tech_requests_open", "tech_requests", ["status", "created_at"])
    op.create_index("ix_tech_requests_company", "tech_requests", ["company_id", "status"])

    op.create_table(
        "tech_request_invites",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "request_id",
            sa.BigInteger(),
            sa.ForeignKey("tech_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            sa.ForeignKey("technologist_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_account_id",
            sa.BigInteger(),
            sa.ForeignKey("user_accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("request_id", "profile_id", name="uq_tech_invite_request_profile"),
    )
    op.create_index("ix_tech_invites_profile", "tech_request_invites", ["profile_id"])

    op.create_table(
        "tech_offers",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "request_id",
            sa.BigInteger(),
            sa.ForeignKey("tech_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            sa.ForeignKey("technologist_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("work_format", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="submitted"),
        *_ts(),
        sa.CheckConstraint("price > 0", name="ck_tech_offer_price_positive"),
        sa.CheckConstraint("duration_days > 0", name="ck_tech_offer_duration_positive"),
        sa.CheckConstraint("currency IN ('USD', 'UZS', 'EUR')", name="ck_tech_offer_currency"),
        sa.CheckConstraint(
            "work_format IN ('online', 'on_site', 'both')", name="ck_tech_offer_format"
        ),
        sa.CheckConstraint(
            "status IN ('submitted', 'accepted', 'declined', 'withdrawn')",
            name="ck_tech_offer_status",
        ),
    )
    op.create_index("ix_tech_offers_request", "tech_offers", ["request_id", "status"])
    op.create_index(
        "uq_tech_offers_active",
        "tech_offers",
        ["request_id", "profile_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('submitted', 'accepted')"),
    )
    op.create_foreign_key(
        "fk_tech_requests_assigned_offer",
        "tech_requests",
        "tech_offers",
        ["assigned_offer_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "tech_threads",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "request_id",
            sa.BigInteger(),
            sa.ForeignKey("tech_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            sa.ForeignKey("technologist_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        *_ts(),
        sa.UniqueConstraint("request_id", "profile_id", name="uq_tech_thread_request_profile"),
    )
    op.create_index("ix_tech_threads_profile", "tech_threads", ["profile_id", "updated_at"])

    op.create_table(
        "tech_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "thread_id",
            sa.BigInteger(),
            sa.ForeignKey("tech_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_kind", sa.Text(), nullable=False),
        sa.Column(
            "author_account_id", sa.BigInteger(), sa.ForeignKey("user_accounts.id"), nullable=False
        ),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("file_storage_path", sa.Text(), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "author_kind IN ('company', 'technologist')", name="ck_tech_message_author_kind"
        ),
        sa.CheckConstraint(
            "body <> '' OR file_storage_path IS NOT NULL", name="ck_tech_message_not_empty"
        ),
    )
    op.create_index("ix_tech_messages_thread", "tech_messages", ["thread_id", "id"])

    op.create_table(
        "tech_reviews",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "request_id",
            sa.BigInteger(),
            sa.ForeignKey("tech_requests.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            sa.ForeignKey("technologist_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_account_id",
            sa.BigInteger(),
            sa.ForeignKey("user_accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_tech_review_rating"),
    )
    op.create_index("ix_tech_reviews_profile", "tech_reviews", ["profile_id"])


def downgrade() -> None:
    op.drop_table("tech_reviews")
    op.drop_table("tech_messages")
    op.drop_table("tech_threads")
    op.drop_constraint("fk_tech_requests_assigned_offer", "tech_requests", type_="foreignkey")
    op.drop_table("tech_offers")
    op.drop_table("tech_request_invites")
    op.drop_table("tech_requests")
    op.drop_table("technologist_profiles")
    op.drop_constraint("ck_user_accounts_applied_as", "user_accounts", type_="check")
    op.drop_column("user_accounts", "applied_as")
