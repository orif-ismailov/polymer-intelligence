"""
Internal users, their page access, and the audit log:
staff_users, staff_page_access, audit_log.

DDL source: docs/polymer-intelligence-db-architecture.md §9.

IMPORTANT: Do NOT change column definitions without a migration.

staff_users columns:
- email (UNIQUE, login identity)
- password_hash (text NOT NULL, argon2 hash)
- is_admin (boolean — administrators bypass the page matrix entirely)
- is_active (boolean, used to disable accounts)

Authorization has two layers. `is_admin` answers "may this account do anything",
and everyone else is granted access one dashboard page at a time through
`staff_page_access` (migration 0044). The four-role `staff_role` enum both
replaced (migration 0042) was unusable: nothing but the seeder ever wrote it, so
a role could only be changed with SQL.

There is no row for "no access" — a page a user holds no row for is a page they
cannot reach. That makes a page added later closed by default to everyone but an
administrator, which is the safe direction to be wrong in.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base


class StaffUser(Base):
    """Internal staff account (dashboard + Telegram DM alerts).

    Passwords hashed with argon2 (argon2-cffi, per DEC-auth-split).
    """

    __tablename__ = "staff_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
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

    page_access: Mapped[list[StaffPageAccess]] = relationship(
        "StaffPageAccess",
        back_populates="staff_user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class StaffPageAccess(Base):
    """One grant: this staff user may read (or write) this dashboard page.

    ONLY GRANTS ARE STORED. There is no `none` level and no row meaning "denied"
    — absence is the denial. That is what makes a page added to the catalog
    later closed to every non-administrator until somebody opens it, instead of
    silently widening everyone's reach on deploy.

    `page` is a key from `app.core.pages.PAGES`, validated at the API boundary
    rather than by a foreign key: the catalog ships with the code that reads it,
    and a lookup table would let the two disagree about which pages exist.

    Administrators never have rows here — `is_admin` short-circuits the check, so
    their reach cannot fall behind the catalog.
    """

    __tablename__ = "staff_page_access"
    __table_args__ = (
        UniqueConstraint("staff_user_id", "page", name="uq_staff_page_access"),
        # A CHECK rather than a PG ENUM: two stable values, and Postgres has no
        # ALTER TYPE ... DROP VALUE, which is what made `staff_role` expensive to
        # retire in 0042.
        CheckConstraint("access IN ('read', 'write')", name="ck_staff_page_access_level"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False
    )
    page: Mapped[str] = mapped_column(Text, nullable=False)                       # app.core.pages key
    access: Mapped[str] = mapped_column(Text, nullable=False)                     # 'read' | 'write'
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    staff_user: Mapped[StaffUser] = relationship(
        "StaffUser", back_populates="page_access"
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
