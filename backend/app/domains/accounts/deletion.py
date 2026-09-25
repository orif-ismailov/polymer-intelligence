"""Account self-deletion — the path both app stores require (Apple: in-app; Google:
in-app + a public web page, served by the portal at `/account-deletion`).

**What "deleted" means here, precisely**, because the privacy policy promises it:

* The `user_accounts` ROW stays, as a tombstone. Roughly forty foreign keys point at
  it — contracts, contract signatures, deals, ЭСФ/Didox documents, verification
  cases, offers, chat messages — and those are the COMPANY's records, which tax and
  contract law require us to retain. Deleting the row would either cascade into them
  or fail on them; neither is acceptable.
* Every personal field on the row is scrubbed: phone becomes a non-identifying
  placeholder (the column is NOT NULL), login / password hash / name / Telegram
  bridge / application company + note become NULL. With no login and no hash the row
  cannot be signed into by any path, and `status='deleted'` (0056) makes every
  guard — `get_current_account`, `/auth/refresh`, `authenticate` — refuse it anyway.
* The account's company memberships are removed. The companies themselves, their
  verification history, deals, contracts and signed documents are NOT touched: they
  belong to the legal entity, not to the person. A company whose only member
  deleted their account is left memberless for staff to re-assign.
* Personal conveniences with no legal weight go: favourites and in-cabinet
  notifications.
* A technologist's public card is withdrawn (`suspended`, snapshot cleared) and its
  personal/contact fields scrubbed; the portrait object is returned to the caller for
  deletion from S3 AFTER the commit. Offers, threads and reviews exchanged with
  factories stay — they are the counterparty's record too.

What is deliberately NOT scrubbed: `company_person_data` / `signature_evidence`
(the E-IMZO certificate data a signature was verified against — evidence for a
signed legal document) and `audit_log`.

The caller verifies the password, rate-limits, commits, revokes the session and
clears the cookie; this module only rewrites the database.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domains.accounts.models import UserAccount
from app.domains.companies.models import CompanyMember
from app.domains.marketplace.models import OfferFavorite
from app.domains.notifications.models import PortalNotification
from app.domains.technologists.models import PROFILE_SUSPENDED, TechnologistProfile
from app.models.enums import AccountStatus
from app.services.audit_service import write_audit

logger = logging.getLogger(__name__)


def tombstone_phone(account_id: int) -> str:
    """The placeholder `phone` of a deleted account.

    Not E.164 on purpose: nothing may mistake it for a number to call, and the
    laboratory/logistics fall-backs that print `account.phone` as a contact then
    show an obviously dead value rather than a plausible one.
    """
    return f"deleted-{account_id}"


def delete_account(db: Session, account: UserAccount) -> list[str]:
    """Turn `account` into a scrubbed, un-signable tombstone. Returns S3 keys to discard.

    The caller has already verified the password and commits. Idempotent in effect:
    a second call finds nothing left to remove.
    """
    memberships = db.execute(
        sa.delete(CompanyMember)
        .where(CompanyMember.user_account_id == account.id)
        .returning(CompanyMember.company_id)
    ).scalars().all()
    db.execute(sa.delete(OfferFavorite).where(OfferFavorite.user_account_id == account.id))
    db.execute(
        sa.delete(PortalNotification).where(PortalNotification.user_account_id == account.id)
    )

    discard: list[str] = []
    profile = db.execute(
        sa.select(TechnologistProfile).where(TechnologistProfile.user_account_id == account.id)
    ).scalar_one_or_none()
    if profile is not None:
        if profile.photo_key:
            discard.append(profile.photo_key)
        profile.status = PROFILE_SUSPENDED
        profile.published_snapshot = None
        profile.full_name = None
        profile.bio = None
        profile.city = None
        profile.photo_key = None
        profile.contact_phone = None
        profile.contact_email = None

    account.status = AccountStatus.deleted
    account.phone = tombstone_phone(account.id)
    account.name = None
    account.login = None
    account.password_hash = None
    account.must_change_password = False
    account.telegram_user_id = None
    account.applied_company_name = None
    account.application_note = None

    # No staff actor: the person acted on themselves. The details carry no personal
    # data — only what was removed, so the row explains the tombstone.
    write_audit(
        db=db,
        staff_user_id=None,
        action="portal_account.self_deleted",
        entity="user_accounts",
        entity_id=str(account.id),
        details={
            "companies_left": sorted(set(memberships)),
            "technologist_profile_id": profile.id if profile is not None else None,
        },
    )
    db.flush()
    logger.info("portal_account.self_deleted", extra={"account_id": account.id})
    return discard
