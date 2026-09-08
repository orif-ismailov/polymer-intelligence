"""Cabinet auth: staff-issued login + password, replacing phone-OTP.

Access to the cabinet is now granted deliberately, per counterparty, as part of a
deal: staff issue a login and a password by hand and the pair is printed in the
contract the two parties sign. Self-registration survives as an APPLICATION — the
public form creates a `pending` row with no credentials and no session — so the only
door into the cabinet is a credential somebody decided to hand out.

Four schema moves, each load-bearing:

1. **`account_status` gains `pending`.** A real state rather than "password_hash IS
   NULL", because `deps.get_current_account` refuses anything that is not `active`:
   every one of the ~140 routes behind that guard fails closed for an applicant
   without knowing this state exists, and the staff queue is one indexed lookup.
   The column's server_default moves `active` → `pending` for the same reason — an
   INSERT that forgets to say produces an applicant, not an account.

2. **`login` is unique through a PARTIAL, CASE-FOLDED index**, not a column
   constraint. Partial (`WHERE login IS NOT NULL`) so the credential-less rows do not
   collide with each other; `lower(login)` because `staff_users.email` learned that an
   account created as `Ivan` could otherwise never be signed into as `ivan`, and the
   index must hold that line against a seeder's raw INSERT too.

3. **`phone` LOSES its UNIQUE constraint.** It is contact information now, not
   identity. The registration form is anonymous and unverified, and while a unique
   index stands, the database answers "this number already applied" on behalf of the
   endpoint — an enumeration oracle no amount of care in the handler can take back.
   The column stays NOT NULL: laboratory/logistics fall back to `account.phone` as the
   contact, and the showcase seeder publishes it as a company's contact number.

4. **`sms_send_log` is dropped** along with the whole SMS rail. OTP was its only
   consumer.

EXISTING ROWS are left with `login = NULL, password_hash = NULL` and their current
status. They lose nothing they hold — companies, contracts and live sessions are
untouched — but they cannot start a NEW session until staff issue credentials, because
the login lookup is `WHERE lower(login) = :login` and never matches NULL. That is the
cutover, and it is deliberate. `login` is NOT backfilled from `phone`: a phone-shaped
login would quietly restore the phone enumeration this migration just removed.

Revision ID: 0048
Revises: 0047
Create Date: 2026-09-08

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. account_status += 'pending' ────────────────────────────────────────
    # ALTER TYPE … ADD VALUE cannot run inside a transaction block; Alembic wraps
    # each migration in one, so it is suspended here (same as 0004, 0028, 0041).
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE account_status ADD VALUE IF NOT EXISTS 'pending' BEFORE 'active'"
        )

    # ── 2. credentials ────────────────────────────────────────────────────────
    op.add_column("user_accounts", sa.Column("login", sa.Text(), nullable=True))
    op.add_column("user_accounts", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "user_accounts",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "user_accounts", sa.Column("password_set_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column(
        "user_accounts",
        sa.Column("credentials_issued_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "user_accounts", sa.Column("credentials_issued_by", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "fk_user_accounts_credentials_issued_by",
        "user_accounts",
        "staff_users",
        ["credentials_issued_by"],
        ["id"],
    )
    # Case-folded so `Ivan` and `ivan` cannot both exist; partial so the rows that
    # have no credentials yet do not all collide on NULL.
    op.execute(
        "CREATE UNIQUE INDEX uq_user_accounts_login "
        "ON user_accounts (lower(login)) WHERE login IS NOT NULL"
    )

    # ── 3. what the applicant typed ───────────────────────────────────────────
    op.add_column("user_accounts", sa.Column("applied_company_name", sa.Text(), nullable=True))
    op.add_column("user_accounts", sa.Column("application_note", sa.Text(), nullable=True))

    # ── 4. phone stops being identity ─────────────────────────────────────────
    # Named by Postgres when 0017 declared an unnamed sa.UniqueConstraint("phone").
    op.drop_constraint("user_accounts_phone_key", "user_accounts", type_="unique")
    op.alter_column("user_accounts", "status", server_default="pending")

    # ── 5. the SMS rail is gone ───────────────────────────────────────────────
    op.drop_index("ix_sms_send_log_phone_created", table_name="sms_send_log")
    op.drop_table("sms_send_log")


def downgrade() -> None:
    # `account_status`'s 'pending' value CANNOT be removed — Postgres has no
    # ALTER TYPE … DROP VALUE (the same wall 0042 hit retiring `staff_role`). Any
    # row still holding it must be moved to another status before this runs, or
    # the restored server_default will be the least of the problems.
    op.create_table(
        "sms_send_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_msg_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sms_send_log_phone_created", "sms_send_log", ["phone", "created_at"])

    op.alter_column("user_accounts", "status", server_default="active")
    op.create_unique_constraint("user_accounts_phone_key", "user_accounts", ["phone"])

    op.drop_column("user_accounts", "application_note")
    op.drop_column("user_accounts", "applied_company_name")
    op.execute("DROP INDEX IF EXISTS uq_user_accounts_login")
    op.drop_constraint(
        "fk_user_accounts_credentials_issued_by", "user_accounts", type_="foreignkey"
    )
    op.drop_column("user_accounts", "credentials_issued_by")
    op.drop_column("user_accounts", "credentials_issued_at")
    op.drop_column("user_accounts", "password_set_at")
    op.drop_column("user_accounts", "must_change_password")
    op.drop_column("user_accounts", "password_hash")
    op.drop_column("user_accounts", "login")
