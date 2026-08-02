"""Shared helpers for the W4 verification real-Postgres tests.

Guarded like the other real-DB suites: only run against a localhost `test_polymer`
DB (skip in CI / default suite). Not a pytest module (leading underscore).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).parent.parent

_DB_URL = os.environ.get("DATABASE_URL", "")
IS_REAL_DB = bool(_DB_URL) and "localhost" in _DB_URL and "test_polymer" in _DB_URL

requires_real_db = pytest.mark.skipif(
    not IS_REAL_DB,
    reason=(
        "Verification DB tests require a live localhost test PostgreSQL. "
        "Set DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer"
    ),
)

# Delete order: children before parents (FK-safe).
_TABLES = [
    "domain_events",
    "audit_log",
    "provider_events",
    "rfq_push_log",
    "offer_favorites",
    "substance_suggestions",
    # Lab orders point at deal documents, offer files, deals, offers and
    # partners — they go first (P6).
    "lab_orders",
    "sample_requests",
    # Payments before deals — escrow_payments.deal_id references them.
    "escrow_payments",
    # Deals before contracts/requests/offers — deals.contract_id references them.
    "rfq_responses",
    "deal_documents",
    "deal_messages",
    "deal_status_history",
    "deals",
    "contract_signatures",
    "contracts",
    "contract_templates",
    "integration_call_log",
    "registry_snapshots",
    "signature_evidence",
    "company_person_data",
    "verification_checks",
    "portal_notifications",
    "request_status_history",
    "request_files",
    "requests",
    # Manufacturers module (0034). None of its FKs to companies/seller_offers
    # carry an ondelete, so a factory RFQ left behind by one test makes the NEXT
    # test's `DELETE FROM companies` fail on a foreign-key violation rather than
    # on anything to do with what it was testing.
    "factory_rfq_documents",
    "manufacturer_messages",
    "factory_rfqs",
    "manufacturer_threads",
    "logistics_requests",
    "company_reviews",
    "company_media",
    "seller_offer_files",
    "offer_requests",
    "seller_offers",
    "substances",
    "lab_partners",
    "company_bank_accounts",
    "company_licenses",
    "verification_documents",
    "verification_cases",
    "company_business_roles",
    "company_members",
    "clients",
    "companies",
    "sms_send_log",
    "staff_users",
    "sellers",
    "user_accounts",
    "app_settings",  # reset operator overrides (e.g. verification_auto_approve) per test
]


def make_engine() -> sa.Engine:
    return sa.create_engine(_DB_URL, pool_pre_ping=True)


def migrate_head() -> None:
    """Point settings + alembic at test_polymer and upgrade to head (idempotent)."""
    from alembic.config import Config

    from alembic import command as alembic_command
    from app.core.config import settings

    object.__setattr__(settings, "DATABASE_URL", _DB_URL)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _DB_URL)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    alembic_command.upgrade(cfg, "head")


def clean(engine: sa.Engine) -> None:
    with engine.begin() as conn:
        for table in _TABLES:
            conn.execute(sa.text(f"DELETE FROM {table}"))  # noqa: S608 — fixed table list


def session_factory(engine: sa.Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def make_account(db: Session, phone: str):  # noqa: ANN202
    from app.models.accounts import UserAccount  # noqa: PLC0415

    account = UserAccount(phone=phone)
    db.add(account)
    db.flush()
    return account


def make_staff(db: Session, email: str = "staff@example.com"):  # noqa: ANN202
    from app.models.enums import StaffRole  # noqa: PLC0415
    from app.models.staff import StaffUser  # noqa: PLC0415

    staff = StaffUser(
        email=email, full_name="Test Staff", role=StaffRole.admin, password_hash="x"
    )
    db.add(staff)
    db.flush()
    return staff


def make_company(db: Session, owner, tax_id: str = "301234567", **kwargs):  # noqa: ANN001, ANN202
    """A company owned by `owner` (an active owner member is created)."""
    from app.models.companies import Company, CompanyMember  # noqa: PLC0415
    from app.models.enums import CompanyMemberRole, CompanyMemberStatus  # noqa: PLC0415

    company = Company(
        jurisdiction=kwargs.pop("jurisdiction", "UZ"),
        tax_id=tax_id,
        created_by_user_account_id=owner.id,
        **kwargs,
    )
    db.add(company)
    db.flush()
    db.add(
        CompanyMember(
            company_id=company.id,
            user_account_id=owner.id,
            member_role=CompanyMemberRole.owner,
            status=CompanyMemberStatus.active,
        )
    )
    db.flush()
    return company


def make_member(db: Session, company, account, *, status=None, role=None):  # noqa: ANN001, ANN202
    """Add `account` to `company` (defaults: active member)."""
    from app.models.companies import CompanyMember  # noqa: PLC0415
    from app.models.enums import CompanyMemberRole, CompanyMemberStatus  # noqa: PLC0415

    member = CompanyMember(
        company_id=company.id,
        user_account_id=account.id,
        member_role=role or CompanyMemberRole.member,
        status=status or CompanyMemberStatus.active,
    )
    db.add(member)
    db.flush()
    return member


def make_seller(db: Session, telegram_user_id: int | None = None, **kwargs):  # noqa: ANN003, ANN202
    """A TG-origin marketplace seller."""
    from app.models.marketplace import Seller  # noqa: PLC0415

    seller = Seller(
        telegram_user_id=telegram_user_id,
        company_name=kwargs.pop("company_name", "TG Seller"),
        **kwargs,
    )
    db.add(seller)
    db.flush()
    return seller


def make_seller_offer(db: Session, *, company=None, seller=None, status=None, **kwargs):  # noqa: ANN001, ANN003, ANN202
    """A seller_offers row — company-origin (pass `company`) or TG-origin (pass `seller`)."""
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.models.marketplace import SellerOffer  # noqa: PLC0415

    offer = SellerOffer(
        seller_id=seller.id if seller is not None else None,
        company_id=company.id if company is not None else None,
        created_by_user_account_id=kwargs.pop("created_by", None),
        product_text=kwargs.pop("product_text", "HDPE film"),
        grade_text=kwargs.pop("grade_text", "F0348"),
        status=status or SellerOfferStatus.approved,
        **kwargs,
    )
    db.add(offer)
    db.flush()
    return offer


def make_request(db: Session, *, company=None, account=None, **kwargs):  # noqa: ANN001, ANN003, ANN202
    """A portal-origin (company) purchase request — the RFQ suppliers respond to."""
    import decimal  # noqa: PLC0415

    from app.models.requests import Request  # noqa: PLC0415

    request = Request(
        number=kwargs.pop("number", f"REQ-TEST-{id(db) % 100000}-{kwargs.pop('n', 1)}"),
        company_id=company.id if company is not None else None,
        created_by_user_account_id=account.id if account is not None else None,
        product_text=kwargs.pop("product_text", "HDPE film"),
        volume=kwargs.pop("volume", decimal.Decimal("20")),
        **kwargs,
    )
    db.add(request)
    db.flush()
    return request
