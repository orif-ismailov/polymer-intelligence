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
) -> PortalNotification | None:
    """Insert a notification for one account (flush-only). Returns the row, or
    ``None`` when kind-level dedup suppresses an identical unread duplicate.

    Args:
        db: Active session (caller commits).
        account_id: Target ``user_accounts.id``.
        kind: Extensible notification kind (plain Text, no enum).
        title_key/body_key: i18n message keys (never rendered text).
        params: Interpolation values stored as JSONB.
        entity/entity_id: Optional deep-link target for the click-through.
        dedup: When True (default), skip if an identical *unread* (account, kind,
            entity, entity_id) row already exists.
    """
    if dedup and _has_unread_duplicate(db, account_id, kind, entity, entity_id):
        logger.info(
            "notification.dedup_skip",
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
) -> list[PortalNotification]:
    """Notify every *active* member of a company. Flush-only. Returns the rows
    actually created (deduped recipients are skipped)."""
    created: list[PortalNotification] = []
    for account_id in active_member_account_ids(db, company_id):
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
