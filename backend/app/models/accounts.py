"""
Portal identity (R1 — ARCHITECTURE Amendment A1): user_accounts, sms_send_log.

A person = one `user_accounts` row keyed by phone number (E.164, unique).
Registration/login is passwordless SMS OTP (Eskiz in prod, console driver in
dev/CI). No password store exists. Company membership is expressed through
`company_members.user_account_id` — one account can own/join many companies.

`telegram_user_id` is a DORMANT nullable bridge to the Mini App world (frozen);
no bridge logic exists in R1–R3.
"""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text
from sqlalchemy import Enum as PgEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import AccountStatus


class UserAccount(Base):
    """A portal person, keyed by phone number (passwordless OTP auth)."""

    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    phone: Mapped[str] = mapped_column(Text, nullable=False, unique=True)          # E.164, e.g. +998901234567
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(
        String(2), nullable=False, default="ru", server_default="ru"
    )
    status: Mapped[AccountStatus] = mapped_column(
        PgEnum(AccountStatus, name="account_status", create_type=False),
        nullable=False,
        default=AccountStatus.active,
        server_default="active",
    )
    telegram_user_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, unique=True
    )                                                                             # dormant Mini App bridge (frozen)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SmsSendLog(Base):
    """Every SMS send attempt — cost tracking + OTP abuse forensics.

    Codes are NEVER stored here (only the fact that a message was sent). The
    (phone, created_at) index backs the daily send-cap query in otp_service.
    """

    __tablename__ = "sms_send_log"
    __table_args__ = (
        Index("ix_sms_send_log_phone_created", "phone", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)                     # 'otp'
    provider: Mapped[str] = mapped_column(Text, nullable=False)                    # 'console' | 'eskiz'
    provider_msg_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)                      # 'ok' | 'error'
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
