"""Technologist profiles: the expert's own editor, staff moderation, the catalog.

**The catalog serves `published_snapshot`, never the live row.** The snapshot is
written only when staff approve, so:

* an expert editing a live profile stays listed as the approved version — the
  edit returns the row to `draft` (or `pending_review` once submitted), and a
  factory never reads a change nobody reviewed;
* a REJECTED edit leaves the expert listed as before; only a profile that was
  never approved has no card to show;
* suspension is the one state that unlists an approved expert.

So "is this expert in the catalog" is `snapshot IS NOT NULL AND status <>
'suspended'` — `is_listed` and `_listed_clause` are twins and must stay so, or
the catalog lists someone the profile page 404s (the trap
`logistics_service.is_visible_to` documents).

A technologist is a PERSON: everything here is keyed on the account, and an
account that applied as a company has no profile at all.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.time import utcnow
from app.domains.accounts.models import UserAccount
from app.domains.technologists.models import (
    PROFILE_DRAFT,
    PROFILE_PENDING,
    PROFILE_PUBLISHED,
    PROFILE_REJECTED,
    PROFILE_SUSPENDED,
    TechnologistProfile,
)
from app.domains.technologists.schemas import TechnologistCardOut, TechnologistProfileIn
from app.models.enums import AccountStatus
from app.services import notification_service
from app.services.audit_service import write_audit

logger = logging.getLogger(__name__)

#: What `submit` refuses without. Contacts are not here: they are only ever
#: shown to a factory that accepted the expert, and the account phone exists.
REQUIRED_FIELDS: tuple[str, ...] = (
    "full_name",
    "title",
    "country",
    "years_experience",
    "processes",
    "languages",
    "work_formats",
)

#: The public card, field by field — what the snapshot copies. `photo_key` is an
#: internal handle: the card turns it into a proxy URL, never ships it raw.
_CARD_FIELDS: tuple[str, ...] = (
    "full_name",
    "title",
    "country",
    "city",
    "photo_key",
    "years_experience",
    "projects_count",
    "countries_count",
    "bio",
    "industries",
    "processes",
    "materials",
    "equipment_brands",
    "work_formats",
    "languages",
)


class NotATechnologist(Exception):
    """The account did not apply as a technologist, or is not active."""


class ProfileIncomplete(Exception):
    """`args[0]` is the list of missing field names."""


class InvalidProfileTransition(Exception):
    """The requested move is not allowed from the profile's current status."""


class ProfileNotFound(Exception):
    """No such profile in the catalog (or not listed)."""


# ── Reading ───────────────────────────────────────────────────────────────────


def is_listed(profile: TechnologistProfile) -> bool:
    """In the catalog? Twin of `_listed_clause`."""
    return profile.published_snapshot is not None and profile.status != PROFILE_SUSPENDED


def _listed_clause() -> ColumnElement[bool]:
    return sa.and_(
        TechnologistProfile.published_snapshot.is_not(None),
        TechnologistProfile.status != PROFILE_SUSPENDED,
    )


def missing_fields(profile: TechnologistProfile) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        value = getattr(profile, field)
        if value is None or value == [] or value == "":
            missing.append(field)
    return missing


def photo_url(profile_id: int, photo_key: str | None) -> str | None:
    """Root-relative proxy path — see `storage_service.presign_company_logo` for
    why a presigned S3 URL would be a broken image in every browser."""
    if not photo_key:
        return None
    return f"/api/v1/public/technologists/{profile_id}/photo"


def _card_dict(profile: TechnologistProfile) -> dict[str, object]:
    return {field: getattr(profile, field) for field in _CARD_FIELDS}


def public_card(profile: TechnologistProfile) -> TechnologistCardOut:
    """The approved card, from the snapshot. Rating is live — it is not the
    expert's to edit, so it needs no review."""
    snap = dict(profile.published_snapshot or {})
    photo_key = snap.pop("photo_key", None)
    return TechnologistCardOut.model_validate(
        {
            **{k: v for k, v in snap.items() if k in TechnologistCardOut.model_fields},
            "id": profile.id,
            "photo_url": photo_url(profile.id, photo_key if isinstance(photo_key, str) else None),
            "rating_avg": profile.rating_avg,
            "rating_count": profile.rating_count,
        }
    )


def get_listed(db: Session, profile_id: int) -> TechnologistProfile:
    profile = db.get(TechnologistProfile, profile_id)
    if profile is None or not is_listed(profile):
        raise ProfileNotFound(str(profile_id))
    return profile


def list_published(
    db: Session,
    *,
    process: str | None = None,
    material: str | None = None,
    language: str | None = None,
    country: str | None = None,
    q: str | None = None,
    limit: int = 24,
    offset: int = 0,
) -> tuple[list[TechnologistProfile], int]:
    """The catalog page and its total. Every filter reads the SNAPSHOT."""
    snap = TechnologistProfile.published_snapshot
    stmt = sa.select(TechnologistProfile).where(_listed_clause())
    if process:
        stmt = stmt.where(snap["processes"].contains([process]))
    if material:
        stmt = stmt.where(snap["materials"].contains([material]))
    if language:
        stmt = stmt.where(snap["languages"].contains([language]))
    if country:
        stmt = stmt.where(sa.func.upper(snap["country"].astext) == country.upper())
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            sa.or_(
                snap["full_name"].astext.ilike(like),
                snap["title"].astext.ilike(like),
                snap["bio"].astext.ilike(like),
            )
        )
    total = db.execute(sa.select(sa.func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(
            TechnologistProfile.rating_avg.desc().nulls_last(),
            TechnologistProfile.rating_count.desc(),
            TechnologistProfile.reviewed_at.desc().nulls_last(),
            TechnologistProfile.id.desc(),
        )
        .limit(max(1, min(limit, 100)))
        .offset(max(0, offset))
    ).scalars()
    return list(rows), int(total)


# ── The expert's own profile ─────────────────────────────────────────────────


def _require_technologist(account: UserAccount) -> None:
    if account.applied_as != "technologist" or account.status != AccountStatus.active:
        raise NotATechnologist(str(account.id))


def find_own(db: Session, account: UserAccount) -> TechnologistProfile | None:
    return (
        db.query(TechnologistProfile)
        .filter(TechnologistProfile.user_account_id == account.id)
        .one_or_none()
    )


def get_or_create_own(db: Session, account: UserAccount) -> TechnologistProfile:
    """The expert's profile, created as an empty draft on first read.

    Pre-filled from the application: the name and phone the person applied with
    are the obvious starting values, and retyping them is a form's worth of
    friction for nothing.
    """
    _require_technologist(account)
    profile = find_own(db, account)
    if profile is not None:
        return profile
    profile = TechnologistProfile(
        user_account_id=account.id,
        full_name=account.name,
        contact_phone=account.phone,
        status=PROFILE_DRAFT,
    )
    db.add(profile)
    db.flush()
    return profile


def update_own(
    db: Session, account: UserAccount, data: TechnologistProfileIn
) -> TechnologistProfile:
    """Save the editor. A change to the PUBLIC card returns the profile to draft
    (the approved snapshot keeps serving); a contacts-only change does not —
    nothing a factory reads changed, so there is nothing to review."""
    profile = get_or_create_own(db, account)
    if profile.status == PROFILE_SUSPENDED:
        raise InvalidProfileTransition("suspended")

    before = _card_dict(profile)
    for field, value in data.model_dump().items():
        setattr(profile, field, value)
    if _card_dict(profile) != before and profile.status != PROFILE_DRAFT:
        profile.status = PROFILE_DRAFT
    db.flush()
    return profile


def set_photo(db: Session, account: UserAccount, content: bytes, filename: str) -> TechnologistProfile:
    """Replace the portrait. A card change like any other — back to draft."""
    from app.services import storage_service  # noqa: PLC0415

    profile = get_or_create_own(db, account)
    if profile.status == PROFILE_SUSPENDED:
        raise InvalidProfileTransition("suspended")
    profile.photo_key = storage_service.store_technologist_photo(profile.id, content, filename)
    profile.status = PROFILE_DRAFT
    db.flush()
    return profile


def submit_own(db: Session, account: UserAccount) -> TechnologistProfile:
    """Send the profile to staff. Idempotent for a profile already waiting."""
    profile = get_or_create_own(db, account)
    if profile.status == PROFILE_PENDING:
        return profile
    if profile.status not in (PROFILE_DRAFT, PROFILE_REJECTED):
        raise InvalidProfileTransition(profile.status)
    missing = missing_fields(profile)
    if missing:
        raise ProfileIncomplete(missing)

    profile.status = PROFILE_PENDING
    profile.submitted_at = utcnow()
    profile.rejection_reason = None
    write_audit(
        db,
        None,
        "technologist.submit",
        "technologist_profiles",
        str(profile.id),
        {"account_id": account.id, "listed": is_listed(profile)},
    )
    db.flush()
    return profile


# ── Staff moderation ─────────────────────────────────────────────────────────


def _decided(
    db: Session, profile: TechnologistProfile, staff_user_id: int, decision: str, reason: str | None
) -> None:
    profile.reviewed_at = utcnow()
    profile.reviewed_by = staff_user_id
    write_audit(
        db,
        staff_user_id,
        f"technologist.{decision}",
        "technologist_profiles",
        str(profile.id),
        {"reason": reason} if reason else None,
    )
    title_key, body_key = notification_service.keys_for(
        notification_service.KIND_TECHNOLOGIST_DECIDED
    )
    notification_service.notify_account(
        db,
        profile.user_account_id,
        kind=notification_service.KIND_TECHNOLOGIST_DECIDED,
        title_key=title_key,
        body_key=body_key,
        params={"decision": decision, "reason": reason or ""},
        entity="technologist",
        entity_id=str(profile.id),
        dedup=False,
    )
    db.flush()


def approve(db: Session, profile: TechnologistProfile, staff_user_id: int) -> None:
    if profile.status != PROFILE_PENDING:
        raise InvalidProfileTransition(profile.status)
    profile.status = PROFILE_PUBLISHED
    profile.rejection_reason = None
    profile.published_snapshot = _card_dict(profile)
    _decided(db, profile, staff_user_id, "approve", None)


def reject(db: Session, profile: TechnologistProfile, staff_user_id: int, reason: str) -> None:
    """Refuse the submitted version. An approved snapshot, if any, stays up."""
    if profile.status != PROFILE_PENDING:
        raise InvalidProfileTransition(profile.status)
    profile.status = PROFILE_REJECTED
    profile.rejection_reason = reason
    _decided(db, profile, staff_user_id, "reject", reason)


def suspend(db: Session, profile: TechnologistProfile, staff_user_id: int, reason: str) -> None:
    """Take a listed expert out of the catalog. Their offers stay on record."""
    if profile.status == PROFILE_SUSPENDED:
        raise InvalidProfileTransition(profile.status)
    profile.status = PROFILE_SUSPENDED
    profile.rejection_reason = reason
    _decided(db, profile, staff_user_id, "suspend", reason)


def list_for_staff(
    db: Session, *, status: str | None = None, limit: int = 50, offset: int = 0
) -> list[TechnologistProfile]:
    stmt = sa.select(TechnologistProfile)
    if status:
        stmt = stmt.where(TechnologistProfile.status == status)
    stmt = stmt.order_by(
        TechnologistProfile.submitted_at.desc().nulls_last(), TechnologistProfile.id.desc()
    )
    return list(db.execute(stmt.limit(limit).offset(offset)).scalars())
