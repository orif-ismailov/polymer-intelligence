"""
Request service — REQ-YYYY-MM-DD-NNNNN number generation, status machine,
request creation, status transitions, and notify enqueue.

Dev-spec §3 status machine:
  new → viewed → in_progress → {offer_sent, matched, closed, cancelled}
  offer_sent → {matched, closed, cancelled}
  matched → {closed}
  closed, cancelled → {} (terminal)

Security:
  T-03-07: Repudiation — transition_status writes audit_log via write_audit
           when changed_by is a staff user id.
  T-03-08: Spoofing — create_request takes a Client ORM object from the
           get_current_client dependency; it NEVER reads client_id from body.
  T-03-09: Tampering — VALID_TRANSITIONS enforces the status machine
           server-side; ValueError raised for disallowed transitions.
  T-03-10: Repudiation — all staff-initiated transitions are traced.

Service-never-commits axiom (DEC-dep-owns-commit):
  All functions call db.flush() to obtain generated IDs but NEVER call
  commit(). The router (or the get_current_client dep) owns the commit.
"""

from __future__ import annotations

import logging
from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import to_display_tz, utcnow
from app.models.enums import RequestStatus
from app.models.requests import Request, RequestStatusHistory
from app.schemas.webapp import RequestCreate
from app.services.audit_service import write_audit

logger = logging.getLogger(__name__)


def _enqueue_notify_soft(request_id: int) -> None:
    """Enqueue the status-change notification, fail-soft.

    The notification is a best-effort side effect: a Redis/broker outage must NOT
    break the user-facing request creation or status transition (e.g. opening a
    request detail auto-transitions new->viewed). ``retry=False`` makes the publish
    fail fast — one attempt, bounded by the broker socket-connect timeout in
    ``celery_app.py`` — and any failure is logged rather than raised.
    """
    from app.tasks.notify import send_status_change_notification  # noqa: PLC0415

    try:
        send_status_change_notification.apply_async(
            args=[request_id], queue="notify", retry=False
        )
    except Exception as exc:
        # Concise (no traceback): this can fire on every request while Redis is down.
        logger.warning(
            "notify enqueue failed (broker unavailable); request %s committed "
            "without a status-change notification: %s",
            request_id,
            exc,
        )


# ── Status machine ────────────────────────────────────────────────────────────

#: Valid transitions per dev-spec §3.
VALID_TRANSITIONS: dict[RequestStatus, set[RequestStatus]] = {
    RequestStatus.new: {RequestStatus.viewed},
    RequestStatus.viewed: {RequestStatus.in_progress},
    RequestStatus.in_progress: {
        RequestStatus.offer_sent,
        RequestStatus.matched,
        RequestStatus.closed,
        RequestStatus.cancelled,
    },
    RequestStatus.offer_sent: {
        RequestStatus.matched,
        RequestStatus.closed,
        RequestStatus.cancelled,
    },
    RequestStatus.matched: {RequestStatus.closed},
    RequestStatus.closed: set(),
    RequestStatus.cancelled: set(),
}

#: D-10 client-facing status key map (internal → client display key).
CLIENT_STATUS_MAP: dict[RequestStatus, str] = {
    RequestStatus.new: "new",
    RequestStatus.viewed: "in_review",
    RequestStatus.in_progress: "in_review",
    RequestStatus.offer_sent: "offer_received",
    RequestStatus.matched: "matched",
    RequestStatus.closed: "closed",
    RequestStatus.cancelled: "cancelled",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def client_facing_status(status: RequestStatus) -> str:
    """Return the D-10 client-facing key for the given internal status.

    Mapping (from UI-SPEC and dev-spec §3):
      new          → "new"
      viewed       → "in_review"
      in_progress  → "in_review"
      offer_sent   → "offer_received"
      matched      → "matched"
      closed       → "closed"
      cancelled    → "cancelled"
    """
    return CLIENT_STATUS_MAP[status]


def generate_request_number(db: Session) -> str:
    """Generate the next REQ-YYYY-MM-DD-NNNNN number for today in Asia/Tashkent.

    Uses a per-date PostgreSQL sequence (req_seq_{YYYYMMDD}) for concurrency-safe
    atomically incrementing counters.  The sequence is created on first use via
    CREATE SEQUENCE IF NOT EXISTS — idempotent.

    Date is always the display-timezone date (Asia/Tashkent) so that midnight
    UTC does not shift the date label mid-business-day.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        A string in the format "REQ-YYYY-MM-DD-NNNNN" (e.g. "REQ-2026-06-16-00001").

    Security note:
        The sequence name is built from a YYYYMMDD string derived SERVER-SIDE
        from the current time — there is no user-supplied input in this path,
        so SQL injection is not a concern.  The string is still validated as
        digits-only before embedding.
    """
    # Get today's date in Asia/Tashkent (DEC-tz-handling)
    today: date = to_display_tz(utcnow(), "Asia/Tashkent").date()
    yyyymmdd = today.strftime("%Y%m%d")  # "20260616"

    # Validate: must be all digits (defensive; this is a server-derived string)
    if not yyyymmdd.isdigit():
        raise RuntimeError(f"Unexpected non-digit date string: {yyyymmdd!r}")

    seq_name = f"req_seq_{yyyymmdd}"

    # CREATE SEQUENCE IF NOT EXISTS is idempotent; safe under concurrent load
    db.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))  # noqa: S608

    # nextval is atomic — concurrency-safe counter
    result = db.execute(sa.text(f"SELECT nextval('{seq_name}')"))
    nextval: int = result.scalar()  # type: ignore[assignment]

    yyyy = today.strftime("%Y")
    mm = today.strftime("%m")
    dd = today.strftime("%d")

    number = f"REQ-{yyyy}-{mm}-{dd}-{nextval:05d}"

    logger.debug(
        "request_service.generate_request_number",
        extra={"number": number, "seq_name": seq_name},
    )
    return number


# ── Core service functions ─────────────────────────────────────────────────────

def create_request(
    db: Session,
    client: object,  # Client ORM object from get_current_client dep
    data: RequestCreate,
) -> Request:
    """Generate REQ number, insert Request + history row, enqueue notify.

    Does NOT commit — caller (router) commits.

    Args:
        db: Active SQLAlchemy session.
        client: The authenticated Client ORM object (from get_current_client dep).
                Identity MUST come from the dependency, NEVER from the request body
                (T-03-08 spoofing mitigation).
        data: Validated RequestCreate schema (D-02 minimum already enforced).

    Returns:
        The newly created Request ORM object (flushed but not committed).

    Raises:
        ValueError: propagated from generate_request_number on unexpected date format.
    """
    # 1. Generate the REQ number (per-date atomic sequence)
    number = generate_request_number(db)

    # 2. Build and add the Request row
    req = Request(
        number=number,
        client_id=client.id,  # type: ignore[attr-defined]
        status=RequestStatus.new,
        product_id=data.product_id,
        grade_text=data.grade_text,
        polymer_type=data.polymer_type,
        volume=data.volume,
        volume_unit=data.volume_unit,
        target_price=data.target_price,
        currency=data.currency,
        incoterms=data.incoterms,
        destination_country=data.destination_country,
        port_or_city=data.port_or_city,
        desired_date=data.desired_date,
        validity_days=data.validity_days,
        urgency=data.urgency,
        comment=data.comment,
    )
    db.add(req)
    db.flush()  # populate req.id before history row

    # 3. Write the initial history row (from_status=None, to_status=new)
    hist = RequestStatusHistory(
        request_id=req.id,
        from_status=None,
        to_status=RequestStatus.new,
        changed_by=None,
        comment=None,
    )
    db.add(hist)
    db.flush()

    # 4. Enqueue the notify task (best-effort — must not fail request creation)
    _enqueue_notify_soft(req.id)

    logger.info(
        "request_service.create",
        extra={"number": number, "client_id": client.id},  # type: ignore[attr-defined]
    )
    return req


def transition_status(
    db: Session,
    request: Request,
    to_status: RequestStatus,
    changed_by: int | None = None,
    comment: str | None = None,
) -> Request:
    """Validate and apply a status transition; write history and optional audit row.

    Does NOT commit — caller commits.

    Args:
        db: Active SQLAlchemy session.
        request: The Request ORM object to transition.
        to_status: The target RequestStatus.
        changed_by: Staff user id if triggered by a staff action (audit trail);
                    None for client/system-initiated transitions.
        comment: Optional comment for the history row.

    Returns:
        The mutated Request ORM object.

    Raises:
        ValueError: if to_status is not in VALID_TRANSITIONS[request.status].
                    Message format: "invalid transition {from} -> {to}"
                    (T-03-09 tampering mitigation).
    """
    old_status = request.status

    # T-03-09: enforce machine server-side
    if to_status not in VALID_TRANSITIONS[old_status]:
        raise ValueError(
            f"invalid transition {old_status.value} -> {to_status.value}"
        )

    # Apply the transition
    request.status = to_status

    # Write history row
    hist = RequestStatusHistory(
        request_id=request.id,
        from_status=old_status,
        to_status=to_status,
        changed_by=changed_by,
        comment=comment,
    )
    db.add(hist)
    db.flush()

    # T-03-10: write audit row for staff-initiated transitions
    if changed_by is not None:
        write_audit(
            db=db,
            staff_user_id=changed_by,
            action="request.status_change",
            entity="requests",
            entity_id=str(request.id),
            details={"from": old_status.value, "to": to_status.value},
        )

    # Enqueue the notify task (best-effort — must not fail the status transition)
    _enqueue_notify_soft(request.id)

    logger.info(
        "request_service.transition_status",
        extra={
            "request_id": request.id,
            "from": old_status.value,
            "to": to_status.value,
            "changed_by": changed_by,
        },
    )
    return request


# ── Phase 4 action functions ───────────────────────────────────────────────────
#
# Three new service functions added in Phase 4 (Plan 04-04).
# All follow the service-never-commits axiom: db.flush() only, never db.commit().
# The router owns the commit, ensuring audit rows share the action's transaction.


def add_note(
    db: Session,
    request_id: int,
    note_text: str,
    staff_user_id: int,
) -> None:
    """Record a team note against a request and write an audit_log entry.

    Does NOT commit — caller (router) commits.

    Args:
        db: Active SQLAlchemy session.
        request_id: The request to annotate.
        note_text: The note content.
        staff_user_id: The acting staff user (from verified JWT, never body).
    """
    # Write audit row (details carries the note text for the audit trail)
    write_audit(
        db=db,
        staff_user_id=staff_user_id,
        action="request.add_note",
        entity="requests",
        entity_id=str(request_id),
        details={"note": note_text},
    )
    # write_audit calls db.flush() internally; no additional flush needed.

    logger.info(
        "request_service.add_note",
        extra={"request_id": request_id, "staff_user_id": staff_user_id},
    )


def assign_owner(
    db: Session,
    request: Request,
    staff_user_id: int,
    changed_by: int,
) -> Request:
    """Assign a staff owner to a request and write an audit_log entry.

    Sets request.assigned_to = staff_user_id and writes an audit row.
    Does NOT commit — caller (router) commits.

    Args:
        db: Active SQLAlchemy session.
        request: The Request ORM object to update.
        staff_user_id: The staff user being assigned as owner.
        changed_by: The acting staff user id (from verified JWT, never body).

    Returns:
        The mutated Request ORM object.
    """
    old_assigned = request.assigned_to
    request.assigned_to = staff_user_id

    write_audit(
        db=db,
        staff_user_id=changed_by,
        action="request.assign_owner",
        entity="requests",
        entity_id=str(request.id),
        details={"assigned_to": staff_user_id, "previously": old_assigned},
    )
    # write_audit calls db.flush() internally.

    logger.info(
        "request_service.assign_owner",
        extra={
            "request_id": request.id,
            "assigned_to": staff_user_id,
            "changed_by": changed_by,
        },
    )
    return request


def log_contact_buyer(
    db: Session,
    request: Request,
    staff_user_id: int,
) -> Request:
    """Log a Contact Buyer action, auto-advancing status if new/viewed.

    If the request status is `new` or `viewed`, calls `transition_status` to
    move it to `in_progress` (with audit + history).  Then writes a dedicated
    "request.contact_buyer" audit entry.

    Does NOT commit — caller (router) commits.

    Args:
        db: Active SQLAlchemy session.
        request: The Request ORM object.
        staff_user_id: The acting staff user id (from verified JWT, never body).

    Returns:
        The (possibly mutated) Request ORM object.
    """
    # D-12: Contact Buyer auto-advances status to in_progress when new/viewed.
    # Reuse transition_status (never duplicate transition logic — Pitfall 5).
    if request.status in {RequestStatus.new, RequestStatus.viewed}:
        transition_status(
            db=db,
            request=request,
            to_status=RequestStatus.in_progress,
            changed_by=staff_user_id,
        )

    # Write the contact_buyer audit entry (separate from the status-change audit).
    write_audit(
        db=db,
        staff_user_id=staff_user_id,
        action="request.contact_buyer",
        entity="requests",
        entity_id=str(request.id),
        details={},
    )
    # write_audit calls db.flush() internally.

    logger.info(
        "request_service.log_contact_buyer",
        extra={"request_id": request.id, "staff_user_id": staff_user_id},
    )
    return request


# ── Notify task import note ───────────────────────────────────────────────────
#
# The real send_status_change_notification task is registered in
# backend/app/tasks/notify.py (added in 03-03). We use a lazy import inside
# create_request/transition_status bodies so this module never imports it at
# module level — keeping the import graph clean and pytest collection socket-free.
#
# In tests, patch "app.tasks.notify.send_status_change_notification" since the
# import happens inside the function body (not at module level).
