"""
Portal identity (R1 — ARCHITECTURE Amendment A1; credentials rail added in 0048).

A person = one `user_accounts` row. **`login` is the identity, not the phone.** Staff
issue a login and a password by hand — the pair is printed in the contract the two
parties sign — and `company_members.user_account_id` expresses membership, so one
account can own or join many companies.

Registration is an APPLICATION: the public form creates a `pending` row with no
credentials and no session, and staff turn it into an account by issuing credentials.
That is why `login` and `password_hash` are nullable while `phone` is not — a row can
legitimately exist before anyone has decided to let its owner in.

`phone` is contact information now, NOT identity, and deliberately carries no UNIQUE
constraint (dropped in 0048): the registration form is anonymous and unverified, so a
unique index would answer "this number already applied" on behalf of the endpoint, and
no amount of care in the handler could take that answer back.

`telegram_user_id` is a DORMANT nullable bridge to the Mini App world (frozen); no
bridge logic exists in R1–R3.
"""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as PgEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import AccountStatus


class UserAccount(Base):
    """A portal person: a staff-issued `login` + argon2 password, or an application."""

    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    phone: Mapped[str] = mapped_column(Text, nullable=False)                       # E.164, contact only
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(
        String(2), nullable=False, default="ru", server_default="ru"
    )
    status: Mapped[AccountStatus] = mapped_column(
        PgEnum(AccountStatus, name="account_status", create_type=False),
        nullable=False,
        default=AccountStatus.pending,
        server_default="pending",
    )
    telegram_user_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, unique=True
    )                                                                              # dormant Mini App bridge (frozen)

    # ── Credentials (0048) ────────────────────────────────────────────────────
    # Nullable because an application has none yet. Uniqueness of `login` is a
    # PARTIAL, CASE-FOLDED index (uq_user_accounts_login) rather than a column
    # constraint: partial so the credential-less rows do not collide with each
    # other, case-folded because `staff_users.email` learned that an account
    # created as `Ivan` could otherwise never be signed into as `ivan`.
    login: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)         # argon2; never in a schema
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    password_set_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    credentials_issued_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Which staff member handed out the authority. No `ondelete` — a person's
    #: history must not detach from their name (the reasoning `audit_log` uses).
    credentials_issued_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("staff_users.id"), nullable=True
    )

    # ── What the applicant typed (0048) ───────────────────────────────────────
    # Two columns rather than one JSONB blob: staff read both on every application
    # and the queue searches them. JSONB here is for foreign payloads, not our form.
    applied_company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Who is asking (0055): `company` — a person who will register a company, or
    #: `technologist` — a private expert who never will. The cabinet routes on it:
    #: a technologist with no company is not an unfinished registration.
    applied_as: Mapped[str] = mapped_column(
        Text, nullable=False, default="company", server_default="company"
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
