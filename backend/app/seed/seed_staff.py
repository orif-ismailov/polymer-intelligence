"""
Staff user seed: creates the bootstrap administrator.

Security contract:
- Passwords are NEVER stored as plaintext. This script:
  1. Reads the password from an environment variable (SEED_{ROLE}_PASSWORD).
  2. Falls back to a documented dev-only default if the env var is not set.
  3. Hashes the password with argon2-cffi before inserting.
- The data/staff_users.json file contains ONLY metadata (email, full_name,
  is_admin, env var name, and a dev-only default). It NEVER contains production
  passwords.
- Production deployments must set SEED_{ROLE}_PASSWORD env vars before seeding.

Usage:
    python -m app.seed.seed_staff                    # uses env vars / dev defaults
    SEED_ADMIN_PASSWORD=mysecret python -m app.seed.seed_staff

The seed is idempotent: uses INSERT ... ON CONFLICT (email) DO NOTHING so re-running
is safe. Existing password hashes are not touched.

This seeds ONE administrator, not a user per role. Staff accounts are created from
the dashboard (`/admin/users`) by an administrator; the seed exists only so a fresh
database can be logged into at all.

WARNING: The dev_default passwords in staff_users.json are for local development ONLY.
Change them before any production deployment. Set environment variables instead.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.staff import StaffUser

_DATA_FILE = Path(__file__).parent / "data" / "staff_users.json"


def seed_staff(db: Session | None = None) -> list[StaffUser]:
    """Seed the bootstrap administrator.

    Args:
        db: An optional SQLAlchemy session. If None, a new SessionLocal is created
            and managed internally.

    Returns:
        A list of StaffUser instances that were created (not including existing ones
        that were skipped due to ON CONFLICT).
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        return _do_seed(db)
    finally:
        if close_db:
            db.close()


def _do_seed(db: Session) -> list[StaffUser]:
    """Internal seed implementation."""
    with open(_DATA_FILE, encoding="utf-8") as f:
        records = json.load(f)

    created: list[StaffUser] = []

    for record in records:
        email: str = record["email"]
        full_name: str = record["full_name"]
        is_admin: bool = record["is_admin"]
        password_env: str = record["password_env"]
        dev_default: str = record["password_dev_default"]

        # Read the password from env. The fallback is a literal in
        # `staff_users.json` — a known string, in a public repo, that opens an
        # ADMIN account. A comment saying "never rely on dev_default in
        # production" is not a control: seeding is automatic on a fresh deploy,
        # so the one environment where nobody watches it run is exactly the one
        # that would get it. Outside development the seeder now refuses instead.
        plain_password = os.environ.get(password_env)
        if not plain_password:
            if settings.APP_ENV != "development":
                raise RuntimeError(
                    f"{password_env} is required to seed {email} when APP_ENV="
                    f"{settings.APP_ENV!r} — the built-in fallback is a public "
                    "literal and must never become a real admin password"
                )
            plain_password = dev_default

        # Check if this user already exists (idempotent seed)
        existing: StaffUser | None = (
            db.query(StaffUser).filter(StaffUser.email == email).first()
        )
        if existing is not None:
            # Skip — user already seeded; do NOT overwrite the password hash
            continue

        # Hash the password with argon2 before storing (T-03-01: never plaintext)
        password_hash = hash_password(plain_password)

        user = StaffUser(
            email=email,
            full_name=full_name,
            is_admin=is_admin,
            password_hash=password_hash,
            is_active=True,
        )
        db.add(user)
        created.append(user)

    if created:
        db.commit()
        for user in created:
            db.refresh(user)

    return created


def verify_seed(db: Session | None = None) -> bool:
    """Verify that at least one active administrator exists.

    This is the lockout check in seed form: a database with no active admin
    cannot be administered from the dashboard at all.

    Args:
        db: An optional SQLAlchemy session.

    Returns:
        True if an active administrator is present.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        return (
            db.query(StaffUser)
            .filter(StaffUser.is_admin.is_(True), StaffUser.is_active.is_(True))
            .count()
            > 0
        )
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    print("Seeding staff users...")
    created = seed_staff()
    if created:
        for user in created:
            print(f"  Created: {user.email} (admin={user.is_admin})")
    else:
        print("  All staff users already seeded (idempotent).")
    print("Done.")
