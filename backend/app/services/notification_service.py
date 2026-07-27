"""
Portal notification service (R2 — ARCHITECTURE Amendment A2).

In-portal notifications addressed to ``user_accounts`` rows. Written inside the
producing transaction (directly, or by the ``domain_events`` outbox consumers in
``app/tasks/events.py``) and read by the portal notification centre
(``GET /portal/notifications``, polling model).

Design invariants (R2-PLAN W2 T2.3):
  * **Never pre-render text** — a notification carries ``title_key`` / ``body_key``
    (i18n message keys) + ``params`` (interpolation values); the portal renders in
    the reader's language at display time.
  * **Kind-level dedup** — ``notify_account`` skips inserting when an identical
    *unread* notification (same account, kind, entity, entity_id) already exists,
    so a re-delivered / repeated event does not spam the bell. A read notification
    never suppresses a fresh one.
  * **Company fan-out** — ``notify_company`` addresses every *active* member of a
    company (used by the verification / offer-moderation consumers).

Service axiom (DEC-dep-owns-commit): every function flushes to obtain ids but
NEVER commits — the caller (router / outbox consumer) owns the transaction.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.companies import CompanyMember
from app.models.enums import CompanyMemberStatus
from app.models.notifications import PortalNotification

logger = logging.getLogger(__name__)

# ── Notification kinds (plain Text by design — extensible, no enum) ───────────
# The i18n keys are derived uniformly as ``notifications.<kind>.title|body`` so a
# producer only picks the kind and the portal (W5.5) renders from the matching
# ru/uz/en messages. Keep this list and the portal locale files in sync.
KIND_REQUEST_STATUS = "request_status"
KIND_INQUIRY_APPROVED = "inquiry_approved"
KIND_INQUIRY_REPLY = "inquiry_reply"
KIND_VERIFICATION_DECIDED = "verification_decided"
KIND_OFFER_MODERATED = "offer_moderated"
KIND_NEWS_BREAKING = "news_breaking"
# Deals (R4 / P2)
KIND_RFQ_RESPONSE_NEW = "rfq_response_new"
KIND_RFQ_RESPONSE_ACCEPTED = "rfq_response_accepted"
KIND_RFQ_RESPONSE_NOT_SELECTED = "rfq_response_not_selected"
KIND_DEAL_OPENED = "deal_opened"
KIND_DEAL_STATUS = "deal_status"
KIND_DEAL_MESSAGE = "deal_message"
KIND_DEAL_DOCUMENT = "deal_document"


def keys_for(kind: str) -> tuple[str, str]:
    """(title_key, body_key) for a kind — the uniform ``notifications.<kind>.*``."""
    return f"notifications.{kind}.title", f"notifications.{kind}.body"


def notify_account(
    db: Session,
    account_id: int,
    *,
    kind: str,
    title_key: str,
    body_key: str,
    params: dict[str, object] | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    dedup: bool = True,
    cooldown_seconds: int | None = None,
) -> PortalNotification | None:
    """Insert a notification for one account (flush-only). Returns the row, or
    ``None`` when dedup or the cooldown suppresses it.

    Args:
        db: Active session (caller commits).
        account_id: Target ``user_accounts.id``.
        kind: Extensible notification kind (plain Text, no enum).
        title_key/body_key: i18n message keys (never rendered text).
        params: Interpolation values stored as JSONB.
        entity/entity_id: Optional deep-link target for the click-through.
        dedup: When True (default), skip if an identical *unread* (account, kind,
            entity, entity_id) row already exists.
        cooldown_seconds: When set, also skip if a matching row was created
            within this window REGARDLESS of whether it was read. Unread-dedup
            alone is not enough for a chat: the moment the reader opens the bell
            the next line typed would ring it again.
    """
    if dedup and _has_unread_duplicate(db, account_id, kind, entity, entity_id):
        logger.info(
            "notification.dedup_skip",
            extra={"account_id": account_id, "kind": kind, "entity_id": entity_id},
        )
        return None
    if cooldown_seconds is not None and _within_cooldown(
        db, account_id, kind, entity, entity_id, cooldown_seconds
    ):
        logger.info(
            "notification.cooldown_skip",
            extra={"account_id": account_id, "kind": kind, "entity_id": entity_id},
        )
        return None

    notif = PortalNotification(
        user_account_id=account_id,
        kind=kind,
        title_key=title_key,
        body_key=body_key,
        params=params or {},
        entity=entity,
        entity_id=entity_id,
    )
    db.add(notif)
    db.flush()
    logger.info(
        "notification.created",
        extra={"id": notif.id, "account_id": account_id, "kind": kind},
    )
    return notif


def notify_company(
    db: Session,
    company_id: int,
    *,
    kind: str,
    title_key: str,
    body_key: str,
    params: dict[str, object] | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    dedup: bool = True,
    cooldown_seconds: int | None = None,
    exclude_account_id: int | None = None,
) -> list[PortalNotification]:
    """Notify every *active* member of a company. Flush-only. Returns the rows
    actually created (deduped recipients are skipped).

    `exclude_account_id` drops the person who caused the event — nobody needs a
    bell for their own action.
    """
    created: list[PortalNotification] = []
    for account_id in active_member_account_ids(db, company_id):
        if account_id == exclude_account_id:
            continue
        notif = notify_account(
            db,
            account_id,
            kind=kind,
            title_key=title_key,
            body_key=body_key,
            params=params,
            entity=entity,
            entity_id=entity_id,
            dedup=dedup,
            cooldown_seconds=cooldown_seconds,
        )
        if notif is not None:
            created.append(notif)
    return created


def active_member_account_ids(db: Session, company_id: int) -> list[int]:
    """The ``user_accounts.id`` of every active member of a company."""
    rows = db.execute(
        select(CompanyMember.user_account_id).where(
            CompanyMember.company_id == company_id,
            CompanyMember.status == CompanyMemberStatus.active,
        )
    ).all()
    return [r[0] for r in rows]


def mark_read(
    db: Session,
    account_id: int,
    *,
    ids: Sequence[int] | None = None,
    mark_all: bool = False,
) -> int:
    """Mark notifications read for an account (flush-only). Returns rows updated.

    Always account-scoped: an id owned by another account is a silent no-op
    (cross-account isolation). ``mark_all`` marks every unread row for the account.
    """
    query = db.query(PortalNotification).filter(
        PortalNotification.user_account_id == account_id,
        PortalNotification.read_at.is_(None),
    )
    if not mark_all:
        if not ids:
            return 0
        query = query.filter(PortalNotification.id.in_(list(ids)))

    updated: int = query.update(
        {PortalNotification.read_at: utcnow()}, synchronize_session=False
    )
    db.flush()
    logger.info(
        "notification.mark_read",
        extra={"account_id": account_id, "count": updated, "all": mark_all},
    )
    return updated


def unread_count(db: Session, account_id: int) -> int:
    """Number of unread notifications for an account."""
    count: int | None = db.execute(
        select(func.count(PortalNotification.id)).where(
            PortalNotification.user_account_id == account_id,
            PortalNotification.read_at.is_(None),
        )
    ).scalar_one()
    return count or 0


def list_notifications(
    db: Session,
    account_id: int,
    *,
    unread_only: bool = False,
    cursor: int | None = None,
    limit: int = 20,
) -> list[PortalNotification]:
    """A page of the account's notifications, newest first (id DESC).

    Keyset pagination: pass the last id of the previous page as ``cursor`` to get
    the next page (``id < cursor``) — stable under concurrent inserts.
    """
    query = db.query(PortalNotification).filter(
        PortalNotification.user_account_id == account_id
    )
    if unread_only:
        query = query.filter(PortalNotification.read_at.is_(None))
    if cursor is not None:
        query = query.filter(PortalNotification.id < cursor)
    return (
        query.order_by(PortalNotification.id.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )


def _within_cooldown(
    db: Session,
    account_id: int,
    kind: str,
    entity: str | None,
    entity_id: str | None,
    seconds: int,
) -> bool:
    """True if a matching row (read or not) was created within `seconds`."""
    import datetime  # noqa: PLC0415

    since = utcnow() - datetime.timedelta(seconds=seconds)
    query = db.query(PortalNotification.id).filter(
        PortalNotification.user_account_id == account_id,
        PortalNotification.kind == kind,
        PortalNotification.created_at >= since,
    )
    query = query.filter(
        PortalNotification.entity.is_(None)
        if entity is None
        else PortalNotification.entity == entity
    )
    query = query.filter(
        PortalNotification.entity_id.is_(None)
        if entity_id is None
        else PortalNotification.entity_id == entity_id
    )
    return db.query(query.exists()).scalar() or False


def _has_unread_duplicate(
    db: Session,
    account_id: int,
    kind: str,
    entity: str | None,
    entity_id: str | None,
) -> bool:
    """True if an identical unread (account, kind, entity, entity_id) row exists."""
    query = db.query(PortalNotification.id).filter(
        PortalNotification.user_account_id == account_id,
        PortalNotification.kind == kind,
        PortalNotification.read_at.is_(None),
    )
    query = query.filter(
        PortalNotification.entity.is_(None)
        if entity is None
        else PortalNotification.entity == entity
    )
    query = query.filter(
        PortalNotification.entity_id.is_(None)
        if entity_id is None
        else PortalNotification.entity_id == entity_id
    )
    return db.query(query.exists()).scalar() or False
