"""
Laboratory orders and the partner directory (P6 W2 — T2.1/T2.2, FR-L1/L2).

The platform does not run the analysis. A partner laboratory does, over the
phone, on its own schedule (TZ §5) — so every status here is moved by an
operator and there is no SLA, no timer and no automatic escalation. What this
module owns is the orchestration: who asked, what for, who is handling it, and
the document that came back.

    submitted → accepted → sample_awaited → in_analysis → done
        └───────────┴──────────────┴─────────────┴──────► rejected

Three rules hold the machine honest:

1. **`done` is not a status you can just set.** It needs the passport, so the
   only door to it is `complete_with_result`, which stores the file and points
   the order at it in the same transaction. The schema says the same thing
   (`ck_lab_order_done_has_result`) — this is the readable half of that CHECK.
2. **`lab_verified` is set here and nowhere else.** That flag is the difference
   between "the seller uploaded a passport" (a badge anyone can earn by
   uploading a PDF) and "we sent the material to a laboratory". If a second
   caller ever sets it, the badge stops meaning anything.
3. **Rejecting requires a reason.** A queue of unexplained rejections is a queue
   nobody can answer a customer's question from.

Service axiom (DEC-dep-owns-commit): flush only — the router owns the commit.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import to_display_tz, utcnow
from app.domains.marketplace.models import SellerOffer, SellerOfferFile
from app.models.accounts import UserAccount
from app.models.companies import Company
from app.models.deals import Deal, DealDocument
from app.models.enums import DealDocumentKind, LabOrderStatus, OfferFileKind
from app.models.lab import LabOrder, LabPartner
from app.models.staff import StaffUser
from app.services import (
    audit_service,
    event_service,
    event_types,
    notification_service,
    storage_service,
)

logger = logging.getLogger(__name__)


# ── State machine (data) ──────────────────────────────────────────────────────

_TRANSITIONS: dict[LabOrderStatus, set[LabOrderStatus]] = {
    LabOrderStatus.submitted: {LabOrderStatus.accepted, LabOrderStatus.rejected},
    LabOrderStatus.accepted: {LabOrderStatus.sample_awaited, LabOrderStatus.rejected},
    LabOrderStatus.sample_awaited: {LabOrderStatus.in_analysis, LabOrderStatus.rejected},
    LabOrderStatus.in_analysis: {LabOrderStatus.done, LabOrderStatus.rejected},
    # Terminal. Re-testing the same material is a NEW order, not a status edit —
    # the old order's passport must keep pointing at the analysis it came from.
    LabOrderStatus.done: set(),
    LabOrderStatus.rejected: set(),
}

#: Statuses that may not be entered without an explanation.
REASON_REQUIRED: frozenset[LabOrderStatus] = frozenset({LabOrderStatus.rejected})

#: Statuses that require the result document, and therefore cannot be reached
#: through `transition` at all.
RESULT_REQUIRED: frozenset[LabOrderStatus] = frozenset({LabOrderStatus.done})

#: The passport is a document, not a photo. The generic allow-list also passes
#: JPEG and spreadsheets, neither of which is a laboratory passport.
RESULT_MIME = "application/pdf"


def can_transition(frm: LabOrderStatus, to: LabOrderStatus) -> bool:
    """Whether the machine allows this pair at all (reason/result rules aside)."""
    return to in _TRANSITIONS[frm]


def available_transitions(frm: LabOrderStatus) -> list[LabOrderStatus]:
    """Statuses reachable from `frm`, in enum order.

    The dashboard builds its buttons from this, so the UI never offers a move the
    API would refuse and never re-implements the machine in TypeScript (the rule
    `escrow_service.available_marks` established).
    """
    return [status for status in LabOrderStatus if status in _TRANSITIONS[frm]]


# ── Domain exceptions (no `Error` suffix — house style) ───────────────────────


class InvalidLabTransition(Exception):
    """The requested lab-order status transition is not allowed."""


class ReasonRequired(Exception):
    """Rejecting a lab order requires a reason."""


class LabResultRequired(Exception):
    """`done` needs the passport — use `complete_with_result`."""


class LabOrderTargetMissing(Exception):
    """An order must be about an offer or a deal."""


class LabOrderNotAllowed(Exception):
    """The company may not order an analysis of this offer/deal."""


class InvalidResultFile(Exception):
    """The uploaded result is not a PDF (or is too large)."""


class LabResultLocked(Exception):
    """This file is a lab order's result — the seller may not remove it."""


# ── Number generation ─────────────────────────────────────────────────────────


def generate_lab_number(db: Session) -> str:
    """Next LAB-YYYY-NNNNNN for the current year in Asia/Tashkent.

    Per-year PostgreSQL sequence with the same first-use race guard as
    `deal_service.generate_deal_number`: the advisory lock serializes the first
    CREATE SEQUENCE of the year, which is otherwise not concurrency safe. The
    year is server-derived and validated digits-only before interpolation.
    """
    year = to_display_tz(utcnow(), "Asia/Tashkent").strftime("%Y")
    if not year.isdigit():  # pragma: no cover — defensive
        raise RuntimeError(f"Unexpected non-digit year: {year!r}")

    seq_name = f"lab_order_seq_{year}"
    db.execute(sa.text("SELECT pg_advisory_xact_lock(:k)"), {"k": int(year) + 1})
    db.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))  # noqa: S608
    nextval: int = db.execute(sa.text(f"SELECT nextval('{seq_name}')")).scalar()  # type: ignore[assignment]
    return f"LAB-{year}-{nextval:06d}"


# ── Partner directory ─────────────────────────────────────────────────────────


def list_partners(db: Session, *, active_only: bool = False) -> list[LabPartner]:
    query = db.query(LabPartner)
    if active_only:
        query = query.filter(LabPartner.is_active.is_(True))
    return query.order_by(LabPartner.name).all()


def get_partner(db: Session, partner_id: int) -> LabPartner | None:
    return db.get(LabPartner, partner_id)


def create_partner(
    db: Session,
    *,
    name: str,
    contacts: dict[str, str] | None = None,
    company_id: int | None = None,
    note: str | None = None,
    staff_user_id: int | None,
) -> LabPartner:
    partner = LabPartner(
        name=name.strip(),
        contacts=contacts or {},
        company_id=company_id,
        note=note,
    )
    db.add(partner)
    db.flush()
    audit_service.write_audit(
        db, staff_user_id, "lab_partner.create", "lab_partners", str(partner.id),
        {"name": partner.name, "company_id": company_id},
    )
    return partner


def update_partner(
    db: Session,
    partner: LabPartner,
    *,
    staff_user_id: int | None,
    name: str | None = None,
    contacts: dict[str, str] | None = None,
    company_id: int | None = None,
    note: str | None = None,
) -> LabPartner:
    """Patch a directory entry. Only what was passed is touched."""
    changed: dict[str, object] = {}
    if name is not None:
        partner.name = name.strip()
        changed["name"] = partner.name
    if contacts is not None:
        partner.contacts = contacts
        changed["contacts"] = contacts
    if company_id is not None:
        partner.company_id = company_id
        changed["company_id"] = company_id
    if note is not None:
        partner.note = note
        changed["note"] = note
    db.flush()
    audit_service.write_audit(
        db, staff_user_id, "lab_partner.update", "lab_partners", str(partner.id), changed
    )
    return partner


def set_partner_active(
    db: Session, partner: LabPartner, active: bool, *, staff_user_id: int | None
) -> LabPartner:
    """Retire (or restore) a laboratory. Never a delete: a finished order points
    at the lab that ran it, and that answer has to survive the partnership."""
    partner.is_active = active
    db.flush()
    audit_service.write_audit(
        db,
        staff_user_id,
        "lab_partner.activate" if active else "lab_partner.deactivate",
        "lab_partners",
        str(partner.id),
        {"name": partner.name},
    )
    return partner


# ── Orders ────────────────────────────────────────────────────────────────────


def get(db: Session, order_id: int) -> LabOrder | None:
    return db.get(LabOrder, order_id)


def list_for_company(db: Session, company_id: int) -> list[LabOrder]:
    return (
        db.query(LabOrder)
        .filter(LabOrder.company_id == company_id)
        .order_by(LabOrder.id.desc())
        .all()
    )


def list_queue(
    db: Session,
    *,
    status: LabOrderStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[LabOrder]:
    """The operator's queue: oldest first, because it is a work list.

    Everything else in the dashboard is newest-first; a queue is the exception —
    the order that has been waiting longest is the one to pick up.
    """
    query = db.query(LabOrder)
    if status is not None:
        query = query.filter(LabOrder.status == status)
    return query.order_by(LabOrder.id).limit(limit).offset(offset).all()


def create_order(
    db: Session,
    *,
    company: Company,
    account: UserAccount,
    offer: SellerOffer | None = None,
    deal: Deal | None = None,
    substance_id: int | None = None,
    sample_volume: str | None = None,
    comment: str | None = None,
) -> LabOrder:
    """Register a request for an analysis. Does NOT commit.

    The caller must own what it is asking about: the offer must belong to
    `company`, or `company` must be a party to the deal. Both are checked here
    rather than in the router so the rule cannot be forgotten by a second caller
    (the Trade Room and the offer form are two separate entry points).
    """
    if offer is None and deal is None:
        raise LabOrderTargetMissing("offer or deal required")
    if offer is not None and offer.company_id != company.id:
        raise LabOrderNotAllowed(f"offer {offer.id} is not {company.id}'s")
    if deal is not None and deal.party_role(company.id) is None:
        raise LabOrderNotAllowed(f"company {company.id} is not a party to deal {deal.id}")

    order = LabOrder(
        number=generate_lab_number(db),
        company_id=company.id,
        created_by_user_account_id=account.id,
        offer_id=offer.id if offer is not None else None,
        deal_id=deal.id if deal is not None else None,
        substance_id=substance_id,
        sample_volume=(sample_volume or "").strip() or None,
        comment=(comment or "").strip() or None,
        status=LabOrderStatus.submitted,
    )
    db.add(order)
    db.flush()

    event_service.emit(
        db, event_types.LAB_ORDER_SUBMITTED, "lab_order", order.id, _payload(order)
    )
    audit_service.write_audit(
        db, None, "lab_order.create", "lab_orders", str(order.id),
        {
            "company_id": company.id,
            "account_id": account.id,
            "offer_id": order.offer_id,
            "deal_id": order.deal_id,
            "number": order.number,
        },
    )
    logger.info(
        "lab_service.create_order",
        extra={"order_id": order.id, "number": order.number, "company_id": company.id},
    )
    return order


def transition(
    db: Session,
    order: LabOrder,
    to_status: LabOrderStatus,
    *,
    staff_user: StaffUser | None,
    note: str | None = None,
) -> LabOrder:
    """Move an order along. Staff only — the process is manual by nature.

    `done` is deliberately unreachable here: it needs the passport, and letting
    it through would produce a row the schema CHECK rejects. A typed error in
    the operator's face beats an IntegrityError.
    """
    frm = order.status
    if to_status in RESULT_REQUIRED:
        raise LabResultRequired(str(to_status))
    if not can_transition(frm, to_status):
        raise InvalidLabTransition(f"{frm} → {to_status}")

    clean_note = (note or "").strip() or None
    if to_status in REASON_REQUIRED and clean_note is None:
        raise ReasonRequired(str(to_status))

    order.status = to_status
    if to_status == LabOrderStatus.rejected:
        order.rejected_reason = clean_note
    elif clean_note is not None:
        order.operator_note = clean_note
    if staff_user is not None:
        order.handled_by = staff_user.id
    db.flush()

    _notify_customer(db, order, status=to_status.value)
    audit_service.write_audit(
        db,
        staff_user.id if staff_user else None,
        "lab_order.transition",
        "lab_orders",
        str(order.id),
        {"from": frm.value, "to": to_status.value, "note": clean_note},
    )
    logger.info(
        "lab_service.transition",
        extra={"order_id": order.id, "from": frm.value, "to": to_status.value},
    )
    return order


def assign_partner(
    db: Session, order: LabOrder, partner: LabPartner, *, staff_user: StaffUser | None
) -> LabOrder:
    """Record which laboratory is doing the work. Not a status change."""
    order.lab_partner_id = partner.id
    if staff_user is not None:
        order.handled_by = staff_user.id
    db.flush()
    audit_service.write_audit(
        db,
        staff_user.id if staff_user else None,
        "lab_order.assign_partner",
        "lab_orders",
        str(order.id),
        {"partner_id": partner.id, "partner_name": partner.name},
    )
    return order


def complete_with_result(
    db: Session,
    order: LabOrder,
    *,
    staff_user: StaffUser | None,
    content: bytes,
    filename: str,
) -> LabOrder:
    """Finish an order by attaching the passport it produced. Does NOT commit.

    The file goes where the order pointed: an offer order attaches a
    `lab_passport` offer file and flips `lab_verified`; a deal order goes through
    `deal_service.add_document`, which is the deals context's own door — it emits
    that context's event and rings both parties' bells rather than this module
    writing into someone else's domain by hand.

    Attaching the result does NOT send the offer back to moderation, unlike a
    seller uploading a passport themselves: staff produced this document and have
    already seen it, and re-queueing would un-publish a live offer as a reward
    for finishing the analysis.
    """
    if not can_transition(order.status, LabOrderStatus.done):
        raise InvalidLabTransition(f"{order.status} → {LabOrderStatus.done}")

    mime = _validated_pdf(content, filename)

    if order.offer_id is not None:
        offer = db.get(SellerOffer, order.offer_id)
        if offer is None:  # pragma: no cover — FK guarantees it
            raise LabOrderTargetMissing(str(order.id))
        stored = storage_service.upload_offer_file(
            db, offer.id, content, filename, OfferFileKind.lab_passport
        )
        order.result_offer_file_id = stored.id
        # The one flag this module owns. Independent confirmation, not "a PDF is
        # attached" — see the module docstring.
        offer.lab_verified = True
    else:
        document = _attach_to_deal(db, order, content, filename)
        order.result_deal_document_id = document.id

    order.status = LabOrderStatus.done
    order.completed_at = utcnow()
    if staff_user is not None:
        order.handled_by = staff_user.id
    db.flush()

    _notify_customer(db, order, status=LabOrderStatus.done.value)
    event_service.emit(
        db, event_types.LAB_ORDER_COMPLETED, "lab_order", order.id, _payload(order)
    )
    audit_service.write_audit(
        db,
        staff_user.id if staff_user else None,
        "lab_order.complete",
        "lab_orders",
        str(order.id),
        {
            "offer_file_id": order.result_offer_file_id,
            "deal_document_id": order.result_deal_document_id,
            "mime": mime,
            "size": len(content),
        },
    )
    logger.info(
        "lab_service.complete_with_result",
        extra={"order_id": order.id, "offer_id": order.offer_id, "deal_id": order.deal_id},
    )
    return order


def _attach_to_deal(
    db: Session, order: LabOrder, content: bytes, filename: str
) -> DealDocument:
    """Put the passport into the Trade Room through the deals context's own door.

    Attributed to the account that ORDERED the analysis, acting for the company
    that ordered it: `deal_documents` records which party a document belongs to,
    and it belongs to them — staff merely carried it. Who actually uploaded it is
    in the audit row.
    """
    from app.services import deal_service  # noqa: PLC0415 — cross-context, lazy

    deal = db.get(Deal, order.deal_id)
    account = db.get(UserAccount, order.created_by_user_account_id)
    if deal is None or account is None:  # pragma: no cover — FKs guarantee it
        raise LabOrderTargetMissing(str(order.id))
    return deal_service.add_document(
        db,
        deal,
        account,
        DealDocumentKind.lab_passport,
        content,
        filename,
        company_id=order.company_id,
    )


def _validated_pdf(content: bytes, filename: str) -> str:
    """Size + magic-byte check, PDF only. Runs BEFORE anything is written."""
    try:
        mime = storage_service.validate_upload(content, filename)
    except ValueError as exc:
        raise InvalidResultFile(str(exc)) from exc
    if mime != RESULT_MIME:
        raise InvalidResultFile("invalid_file_type")
    return mime


# ── The seller's own passport upload ──────────────────────────────────────────


def assert_result_unlocked(db: Session, file_id: int) -> None:
    """Refuse to remove a file that is a lab order's result.

    The operator uploaded it and it is the evidence behind the "Laboratory
    Verified" badge; letting the seller delete it would leave the badge standing
    on nothing.
    """
    exists = (
        db.query(LabOrder.id).filter(LabOrder.result_offer_file_id == file_id).first()
    )
    if exists is not None:
        raise LabResultLocked(str(file_id))


def clear_lab_verification(db: Session, offer: SellerOffer) -> bool:
    """Drop `lab_verified` when the offer no longer carries any passport.

    Only reachable for a self-uploaded passport — a platform result cannot be
    deleted (`assert_result_unlocked`). Returns whether anything changed.
    """
    if not offer.lab_verified:
        return False
    still_there = (
        db.query(SellerOfferFile.id)
        .filter(
            SellerOfferFile.offer_id == offer.id,
            SellerOfferFile.kind == OfferFileKind.lab_passport,
        )
        .first()
    )
    if still_there is not None:
        return False
    offer.lab_verified = False
    db.flush()
    return True


# ── Notifications / payloads ──────────────────────────────────────────────────


def _notify_customer(db: Session, order: LabOrder, *, status: str) -> None:
    """Ring the ordering company's bell.

    `dedup=False`: "your sample is awaited" and "your passport is ready" are
    different sentences about one order, and the default unread-dedup would
    swallow the second.
    """
    title_key, body_key = notification_service.keys_for(
        notification_service.KIND_LAB_ORDER_STATUS
    )
    notification_service.notify_company(
        db,
        order.company_id,
        kind=notification_service.KIND_LAB_ORDER_STATUS,
        title_key=title_key,
        body_key=body_key,
        params={"number": order.number, "status": status, "lab_order_id": order.id},
        entity="lab_order",
        entity_id=str(order.id),
        dedup=False,
    )


def _payload(order: LabOrder) -> dict[str, object]:
    """Event body. Carries enough for a consumer to render a card with no query."""
    return {
        "lab_order_id": order.id,
        "number": order.number,
        "company_id": order.company_id,
        "offer_id": order.offer_id,
        "deal_id": order.deal_id,
        "status": order.status.value,
    }
