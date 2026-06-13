"""
Alerts and delivery: alert_rules, alerts, deliveries.

DDL source: docs/polymer-intelligence-db-architecture.md §7.

Alert flow:
1. evaluate_alert_rules(signal_id|request_id) matches rules
2. Creates alert with dedupe_key to prevent duplicate alerts
3. Creates delivery entries for each target channel
4. send_delivery task dispatches to Telegram/webapp/dashboard
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import AlertKind, DeliveryChannel, DeliveryStatus


class AlertRule(Base):
    """Configurable alert rule (JSONB condition, evaluated on signal/request creation)."""

    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[AlertKind] = mapped_column(
        PgEnum(AlertKind, name="alert_kind", create_type=False),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[dict] = mapped_column(JSONB, nullable=False)               # {"product":"PP","volume_gte":200,...}
    channels: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )                                                                             # [{"type":"telegram_dm","chat_id":...}]
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)       # REFERENCES staff_users(id)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Alert(Base):
    """A triggered alert instance.

    dedupe_key prevents duplicate alerts for the same event.
    Format: 'rule:{rule_id}:{entity}:{id}'
    """

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_alerts_dedupe_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[AlertKind] = mapped_column(
        PgEnum(AlertKind, name="alert_kind", create_type=False),
        nullable=False,
    )
    rule_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("alert_rules.id"), nullable=True
    )
    severity: Mapped[str] = mapped_column(
        Text, nullable=False, default="info", server_default="info"
    )                                                                             # info / warning / critical
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    signal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("signals.id"), nullable=True
    )
    request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("requests.id"), nullable=True
    )
    dedupe_key: Mapped[str | None] = mapped_column(Text, nullable=True)          # dedup protection
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Delivery(Base):
    """Delivery record for an alert or report notification."""

    __tablename__ = "deliveries"
    __table_args__ = (
        Index(
            "ix_deliveries_status_queued",
            "status",
            postgresql_where="status = 'queued'",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    alert_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("alerts.id"), nullable=True
    )
    report_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )                                                                             # REFERENCES reports(id)
    channel: Mapped[DeliveryChannel] = mapped_column(
        PgEnum(DeliveryChannel, name="delivery_channel", create_type=False),
        nullable=False,
    )
    recipient: Mapped[str] = mapped_column(Text, nullable=False)                 # chat_id / channel_id / user_id
    status: Mapped[DeliveryStatus] = mapped_column(
        PgEnum(DeliveryStatus, name="delivery_status", create_type=False),
        nullable=False,
        default=DeliveryStatus.queued,
        server_default="queued",
    )
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
