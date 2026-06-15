"""
Internal users and audit log: staff_users, audit_log.

DDL source: docs/polymer-intelligence-db-architecture.md §9.

IMPORTANT: The staff_users table and staff_role ENUM are created here (plan 01-02)
as the schema foundations for REQ-roles. Plan 01-03 enforces the authorization
boundaries on top of this schema. Do NOT change column definitions without a
migration + updating the plan 01-03 auth contract.

staff_users columns for plan 01-03:
- email (UNIQUE, login identity)
- password_hash (text NOT NULL, argon2 hash)
- role (staff_role ENUM: admin, analyst, trader, viewer)
- is_active (boolean, used to disable accounts)
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import StaffRole


class StaffUser(Base):
    """Internal staff account (dashboard + Telegram DM alerts).

    Role enforcement is done in plan 01-03 (REQ-roles).
    Passwords hashed with argon2 (argon2-cffi, per DEC-auth-split).
    """

    __tablename__ = "staff_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[StaffRole] = mapped_column(
        PgEnum(StaffRole, name="staff_role", create_type=False),
        nullable=False,
        default=StaffRole.viewer,
        server_default="viewer",
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)             # argon2 hash (plan 01-03)
    telegram_user_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )                                                                             # for DM alerts
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditLog(Base):
    """Immutable audit trail for staff actions.

    All status changes, approvals, and admin actions are logged here.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)                    # 'request.status_change', 'report.approve'
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
