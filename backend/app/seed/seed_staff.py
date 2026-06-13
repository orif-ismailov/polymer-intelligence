"""
Staff user seed: creates one staff_users row per role (admin/analyst/trader/viewer).

Security contract:
- Passwords are NEVER stored as plaintext. This script:
  1. Reads the password from an environment variable (SEED_{ROLE}_PASSWORD).
  2. Falls back to a documented dev-only default if the env var is not set.
  3. Hashes the password with argon2-cffi before inserting.
- The data/staff_users.json file contains ONLY metadata (email, role, full_name,
  env var name, and a dev-only default). It NEVER contains production passwords.
- Production deployments must set SEED_{ROLE}_PASSWORD env vars before seeding.

Usage:
    python -m app.seed.seed_staff                    # uses env vars / dev defaults
    SEED_ADMIN_PASSWORD=mysecret python -m app.seed.seed_staff

The seed is idempotent: uses INSERT ... ON CONFLICT (email) DO NOTHING so re-running
is safe. Existing password hashes are not touched.

WARNING: The dev_default passwords in staff_users.json are for local development ONLY.
Change them before any production deployment. Set environment variables instead.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.enums import StaffRole
from app.models.staff import StaffUser

_DATA_FILE = Path(__file__).parent / "data" / "staff_users.json"


def seed_staff(db: Session | None = None) -> list[StaffUser]:
    """Seed one staff_users row per role.

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
        role_str: str = record["role"]
        password_env: str = record["password_env"]
        dev_default: str = record["password_dev_default"]

        # Read password from env; fall back to dev default
        # In production: set the env var — never rely on dev_default
        plain_password = os.environ.get(password_env, dev_default)

        role = StaffRole(role_str)

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
            role=role,
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
    """Verify that all four staff roles have at least one active user seeded.

    Args:
        db: An optional SQLAlchemy session.

    Returns:
        True if all four roles are present and active.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        for role in StaffRole:
            count = (
                db.query(StaffUser)
                .filter(StaffUser.role == role, StaffUser.is_active.is_(True))
                .count()
            )
            if count == 0:
                return False
        return True
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    print("Seeding staff users...")
    created = seed_staff()
    if created:
        for user in created:
            print(f"  Created: {user.email} (role={user.role.value})")
    else:
        print("  All staff users already seeded (idempotent).")
    print("Done.")
