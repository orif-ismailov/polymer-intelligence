"""Initial schema — all 20 tables, 14 ENUMs, and v_live_feed view.

Reproduces the locked PostgreSQL 16 DDL verbatim from
docs/polymer-intelligence-db-architecture.md v1.1.

Revision ID: 0001
Revises: (none — this is the root migration)
Create Date: 2026-06-13

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
Do NOT edit this migration to add/remove columns — add a new revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. Create ENUM types (must precede tables) ────────────────────────────
    source_kind = postgresql.ENUM(
        "exchange", "telegram_channel", "website", "webapp",
        "manual", "external_index", "rss",
        name="source_kind",
    )
    source_kind.create(op.get_bind())

    parse_status = postgresql.ENUM(
        "pending", "parsed", "failed", "skipped", "irrelevant",
        name="parse_status",
    )
    parse_status.create(op.get_bind())

    counterparty_role = postgresql.ENUM(
        "buyer", "seller", "trader", "producer", "unknown",
        name="counterparty_role",
    )
    counterparty_role.create(op.get_bind())

    signal_kind = postgresql.ENUM(
        "buy_request", "sell_offer", "deal", "price_quote", "news",
        name="signal_kind",
    )
    signal_kind.create(op.get_bind())

    price_basis = postgresql.ENUM(
        "EXW", "FCA", "FOB", "CIF", "CPT", "DAP", "DDP", "unknown",
        name="price_basis",
    )
    price_basis.create(op.get_bind())

    urgency = postgresql.ENUM(
        "low", "medium", "high",
        name="urgency",
    )
    urgency.create(op.get_bind())

    request_status = postgresql.ENUM(
        "new", "viewed", "in_progress", "offer_sent",
        "matched", "closed", "cancelled",
        name="request_status",
    )
    request_status.create(op.get_bind())

    price_point_kind = postgresql.ENUM(
        "deal_avg", "offer_avg", "index", "futures",
        name="price_point_kind",
    )
    price_point_kind.create(op.get_bind())

    alert_kind = postgresql.ENUM(
        "new_hot_request", "large_volume", "price_spike", "below_market_offer",
        "new_buyer", "source_failure", "custom",
        name="alert_kind",
    )
    alert_kind.create(op.get_bind())

    delivery_channel = postgresql.ENUM(
        "telegram_dm", "telegram_channel", "webapp", "dashboard",
        name="delivery_channel",
    )
    delivery_channel.create(op.get_bind())

    delivery_status = postgresql.ENUM(
        "queued", "sent", "failed",
        name="delivery_status",
    )
    delivery_status.create(op.get_bind())

    report_kind = postgresql.ENUM(
        "morning", "intraday", "weekly", "custom",
        name="report_kind",
    )
    report_kind.create(op.get_bind())

    report_status = postgresql.ENUM(
        "draft", "pending_approval", "approved", "published", "rejected",
        name="report_status",
    )
    report_status.create(op.get_bind())

    staff_role = postgresql.ENUM(
        "admin", "analyst", "trader", "viewer",
        name="staff_role",
    )
    staff_role.create(op.get_bind())

    # ── 2. Reference tables ───────────────────────────────────────────────────

    op.create_table(
        "products",
        sa.Column("id", sa.SmallInteger(), sa.Identity(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name_ru", sa.Text(), nullable=False),
        sa.Column("name_uz", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=False, server_default="polymer"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "product_grades",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("product_id", sa.SmallInteger(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("producer", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "code", name="uq_product_grades_product_code"),
    )

    op.create_table(
        "fx_rates",
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("ccy", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(18, 6), nullable=False),
        sa.PrimaryKeyConstraint("rate_date", "ccy"),
    )

    # ── 3. Sources and raw data layer ─────────────────────────────────────────

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("kind", postgresql.ENUM(name="source_kind", create_type=False), nullable=False),
        sa.Column("adapter", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_test_ok_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_fetch_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "raw_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("content_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("event_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "parse_status",
            postgresql.ENUM(name="parse_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("parse_attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "content_hash", name="uq_raw_items_source_content"),
    )

    op.create_table(
        "parse_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("raw_item_id", sa.BigInteger(), nullable=False),
        sa.Column("parser", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["raw_item_id"], ["raw_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 4. Counterparties ─────────────────────────────────────────────────────

    op.create_table(
        "counterparties",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name="counterparty_role", create_type=False),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("tax_id", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "counterparty_aliases",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("alias_norm", sa.Text(), nullable=False),
        sa.Column(
            "source_kind",
            postgresql.ENUM(name="source_kind", create_type=False),
            nullable=True,
        ),
        sa.Column("confidence", sa.REAL(), nullable=False, server_default="1.0"),
        sa.ForeignKeyConstraint(
            ["counterparty_id"], ["counterparties.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias_norm", "counterparty_id", name="uq_counterparty_aliases_norm"),
    )

    # ── 5. Staff users and audit log ──────────────────────────────────────────
    # staff_users is created before signals/requests because processed_by/assigned_to
    # logically reference it (we use Integer without FK in models to avoid circularity,
    # but the table must exist).

    op.create_table(
        "staff_users",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name="staff_role", create_type=False),
            nullable=False,
            server_default="viewer",
        ),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # ── 6. Signals ────────────────────────────────────────────────────────────

    op.create_table(
        "signals",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(name="signal_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("raw_item_id", sa.BigInteger(), nullable=True),
        sa.Column("product_id", sa.SmallInteger(), nullable=True),
        sa.Column("grade_id", sa.Integer(), nullable=True),
        sa.Column("grade_text", sa.Text(), nullable=True),
        sa.Column("volume", sa.Numeric(14, 3), nullable=True),
        sa.Column("volume_unit", sa.Text(), nullable=False, server_default="MT"),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column(
            "price_basis",
            postgresql.ENUM(name="price_basis", create_type=False),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("destination", sa.Text(), nullable=True),
        sa.Column("counterparty_id", sa.Integer(), nullable=True),
        sa.Column("counterparty_text", sa.Text(), nullable=True),
        sa.Column("ai", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "urgency",
            postgresql.ENUM(name="urgency", create_type=False),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="new"),
        sa.Column("processed_by", sa.Integer(), nullable=True),
        sa.Column("event_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("extra", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["grade_id"], ["product_grades.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["raw_item_id"], ["raw_items.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 7. Clients and requests ───────────────────────────────────────────────

    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("contact_name", sa.Text(), nullable=True),
        sa.Column("language", sa.String(2), nullable=False, server_default="ru"),
        sa.Column("counterparty_id", sa.Integer(), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
    )

    op.create_table(
        "requests",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.SmallInteger(), nullable=False),
        sa.Column("grade_text", sa.Text(), nullable=True),
        sa.Column("polymer_type", sa.Text(), nullable=True),
        sa.Column("volume", sa.Numeric(14, 3), nullable=False),
        sa.Column("volume_unit", sa.Text(), nullable=False, server_default="MT"),
        sa.Column("target_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column(
            "incoterms",
            postgresql.ENUM(name="price_basis", create_type=False),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("destination_country", sa.String(2), nullable=False, server_default="UZ"),
        sa.Column("port_or_city", sa.Text(), nullable=True),
        sa.Column("desired_date", sa.Date(), nullable=True),
        sa.Column("validity_days", sa.SmallInteger(), nullable=False, server_default="30"),
        sa.Column(
            "urgency",
            postgresql.ENUM(name="urgency", create_type=False),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="request_status", create_type=False),
            nullable=False,
            server_default="new",
        ),
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        sa.Column("ai", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number"),
    )

    op.create_table(
        "request_files",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("telegram_file_id", sa.Text(), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "request_status_history",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column(
            "from_status",
            postgresql.ENUM(name="request_status", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            postgresql.ENUM(name="request_status", create_type=False),
            nullable=False,
        ),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 8. Price points ───────────────────────────────────────────────────────

    op.create_table(
        "price_points",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(name="price_point_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.SmallInteger(), nullable=False),
        sa.Column("grade_id", sa.Integer(), nullable=True),
        sa.Column("market", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False, server_default="MT"),
        sa.Column("price_avg", sa.Numeric(14, 2), nullable=False),
        sa.Column("price_min", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_max", sa.Numeric(14, 2), nullable=True),
        sa.Column("volume_total", sa.Numeric(14, 3), nullable=True),
        sa.Column("deals_count", sa.Integer(), nullable=True),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["grade_id"], ["product_grades.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "kind", "source_id", "product_id", "grade_id", "market", "observed_on",
            name="uq_price_points_kind_source_product_grade_market_date",
        ),
    )

    # ── 9. Alert rules, alerts, deliveries ───────────────────────────────────

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(name="alert_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("condition", postgresql.JSONB(), nullable=False),
        sa.Column("channels", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(name="alert_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("rule_id", sa.Integer(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=False, server_default="info"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("signal_id", sa.BigInteger(), nullable=True),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["rule_id"], ["alert_rules.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_alerts_dedupe_key"),
    )

    op.create_table(
        "deliveries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("alert_id", sa.BigInteger(), nullable=True),
        sa.Column("report_id", sa.Integer(), nullable=True),
        sa.Column(
            "channel",
            postgresql.ENUM(name="delivery_channel", create_type=False),
            nullable=False,
        ),
        sa.Column("recipient", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="delivery_status", create_type=False),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 10. Reports ───────────────────────────────────────────────────────────

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(name="report_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("data_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "status",
            postgresql.ENUM(name="report_status", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("generated_by", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["staff_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 11. Audit log ─────────────────────────────────────────────────────────

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("staff_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["staff_user_id"], ["staff_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 12. Indexes ───────────────────────────────────────────────────────────

    op.create_index(
        "ix_raw_items_parse_status_pending",
        "raw_items",
        ["parse_status", "fetched_at"],
        postgresql_where=sa.text("parse_status = 'pending'"),
    )
    op.create_index(
        "ix_raw_items_source_fetched",
        "raw_items",
        ["source_id", "fetched_at"],
    )
    op.create_index(
        "ix_counterparty_aliases_alias_norm",
        "counterparty_aliases",
        ["alias_norm"],
    )
    op.create_index(
        "ix_signals_kind_event_at",
        "signals",
        ["kind", "event_at"],
    )
    op.create_index(
        "ix_signals_product_event_at",
        "signals",
        ["product_id", "event_at"],
    )
    op.create_index(
        "ix_signals_counterparty_id_notnull",
        "signals",
        ["counterparty_id"],
        postgresql_where=sa.text("counterparty_id IS NOT NULL"),
    )
    op.create_index(
        "ix_signals_status_new",
        "signals",
        ["status"],
        postgresql_where=sa.text("status = 'new'"),
    )
    op.create_index(
        "ix_signals_ai_gin",
        "signals",
        ["ai"],
        postgresql_using="gin",
        postgresql_ops={"ai": "jsonb_path_ops"},
    )
    op.create_index(
        "ix_requests_status_created_at",
        "requests",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_requests_client_created_at",
        "requests",
        ["client_id", "created_at"],
    )
    op.create_index(
        "ix_price_points_product_market_observed",
        "price_points",
        ["product_id", "market", "observed_on"],
    )
    op.create_index(
        "ix_deliveries_status_queued",
        "deliveries",
        ["status"],
        postgresql_where=sa.text("status = 'queued'"),
    )

    # ── 13. v_live_feed view ──────────────────────────────────────────────────
    # Verbatim from docs/polymer-intelligence-db-architecture.md §5.
    op.execute(
        """
        CREATE VIEW v_live_feed AS
            SELECT id, 'signal' AS origin, kind::text, product_id, grade_text, volume,
                   price, currency, region, urgency, status, event_at
            FROM signals
            UNION ALL
            SELECT id, 'request', 'buy_request', product_id, grade_text, volume,
                   target_price, currency, destination_country, urgency,
                   status::text, created_at
            FROM requests
        """
    )


def downgrade() -> None:
    # ── Drop view first ───────────────────────────────────────────────────────
    op.execute("DROP VIEW IF EXISTS v_live_feed")

    # ── Drop indexes ──────────────────────────────────────────────────────────
    op.drop_index("ix_deliveries_status_queued", table_name="deliveries")
    op.drop_index("ix_price_points_product_market_observed", table_name="price_points")
    op.drop_index("ix_requests_client_created_at", table_name="requests")
    op.drop_index("ix_requests_status_created_at", table_name="requests")
    op.drop_index("ix_signals_ai_gin", table_name="signals")
    op.drop_index("ix_signals_status_new", table_name="signals")
    op.drop_index("ix_signals_counterparty_id_notnull", table_name="signals")
    op.drop_index("ix_signals_product_event_at", table_name="signals")
    op.drop_index("ix_signals_kind_event_at", table_name="signals")
    op.drop_index("ix_counterparty_aliases_alias_norm", table_name="counterparty_aliases")
    op.drop_index("ix_raw_items_source_fetched", table_name="raw_items")
    op.drop_index("ix_raw_items_parse_status_pending", table_name="raw_items")

    # ── Drop tables in reverse FK dependency order ────────────────────────────
    op.drop_table("audit_log")
    op.drop_table("reports")
    op.drop_table("deliveries")
    op.drop_table("alerts")
    op.drop_table("alert_rules")
    op.drop_table("price_points")
    op.drop_table("request_status_history")
    op.drop_table("request_files")
    op.drop_table("requests")
    op.drop_table("clients")
    op.drop_table("signals")
    op.drop_table("staff_users")
    op.drop_table("counterparty_aliases")
    op.drop_table("counterparties")
    op.drop_table("parse_runs")
    op.drop_table("raw_items")
    op.drop_table("sources")
    op.drop_table("fx_rates")
    op.drop_table("product_grades")
    op.drop_table("products")

    # ── Drop ENUM types in reverse creation order ─────────────────────────────
    bind = op.get_bind()
    for enum_name in [
        "staff_role",
        "report_status",
        "report_kind",
        "delivery_status",
        "delivery_channel",
        "alert_kind",
        "price_point_kind",
        "request_status",
        "urgency",
        "price_basis",
        "signal_kind",
        "counterparty_role",
        "parse_status",
        "source_kind",
    ]:
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
