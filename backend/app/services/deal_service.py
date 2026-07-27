"""Deal lifecycle service (R4 / P2 — T1.2). The core of the Deal Lifecycle track.

State machine (data, see `VALID_TRANSITIONS`):

    negotiation ─► contract_pending ─► contract_signed ─► payment_pending
         │                │                                    │
         │                └─► negotiation (contract declined)   ▼
         │                                                paid_escrow ─► shipped
         └─────────────── cancelled ◄──────────────────┘         │          │
                                                                 ▼          ▼
                                            disputed ◄────── delivered ─► completed

Two rules are enforced on every move and they are separate concerns:

  * **Which** transitions exist — `VALID_TRANSITIONS`.
  * **Who** may drive one — `allowed_actors`. A seller declares the shipment, a
    buyer confirms delivery, either side may cancel or dispute, and only
    `system` may assert the statuses that follow from an event (contract
    activated, escrow funded, funds released). Only staff leaves a dispute.

FR-D8: a unilateral cancel is allowed strictly BEFORE `paid_escrow`. Once money
is in escrow the way out is a dispute, which staff resolve by restoring a
previous status or cancelling.

Every transition takes `SELECT … FOR UPDATE` on the deal row and writes the
history row, the audit entry and the domain event in the caller's transaction —
so a deal can never change status without its timeline saying so.
"""

from __future__ import annotations

import datetime
import decimal
import logging

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import to_display_tz, utcnow
from app.models.accounts import UserAccount
from app.models.companies import Company, CompanyMember
from app.models.contracts import Contract
from app.models.deals import Deal, DealDocument, DealMessage, DealStatusHistory, RfqResponse
from app.models.enums import (
    CompanyMemberRole,
    CompanyMemberStatus,
    CompanyStatus,
    DealActorKind,
    DealDocumentKind,
    DealStatus,
    RfqResponseStatus,
)
from app.models.marketplace import OfferRequest, SellerOffer
from app.models.requests import Request
from app.services import (
    audit_service,
    event_service,
    event_types,
    notification_service,
    storage_service,
)

logger = logging.getLogger(__name__)

#: Roles that may act on behalf of a company inside a deal. A plain `member` is
#: read-only here — same split the rest of the portal uses for company-wide acts.
DEAL_ACTOR_ROLES: frozenset[CompanyMemberRole] = frozenset(
    {CompanyMemberRole.owner, CompanyMemberRole.manager}
)

#: Chat/document attachments cap (the generic upload limit).
MAX_DEAL_FILE_BYTES: int = storage_service.MAX_SIZE_BYTES

#: How long one chat notification silences the next for the same deal. A busy
#: Trade Room would otherwise ring the counterparty's bell on every line typed.
CHAT_NOTIFY_COOLDOWN_SECONDS: int = 600


# ── State machine (data) ──────────────────────────────────────────────────────

VALID_TRANSITIONS: dict[DealStatus, set[DealStatus]] = {
    DealStatus.negotiation: {DealStatus.contract_pending, DealStatus.cancelled},
    # A declined/cancelled contract rolls the deal back rather than killing it —
    # the parties may simply redraft.
    DealStatus.contract_pending: {
        DealStatus.contract_signed,
        DealStatus.negotiation,
        DealStatus.cancelled,
    },
    DealStatus.contract_signed: {DealStatus.payment_pending, DealStatus.cancelled},
    DealStatus.payment_pending: {
        DealStatus.paid_escrow,
        DealStatus.disputed,
        DealStatus.cancelled,
    },
    DealStatus.paid_escrow: {DealStatus.shipped, DealStatus.disputed},
    DealStatus.shipped: {DealStatus.delivered, DealStatus.disputed},
    DealStatus.delivered: {DealStatus.completed, DealStatus.disputed},
    # Staff resolution: restore any status a dispute can be entered from, or
    # cancel. (The plan omitted payment_pending here while allowing entry from
    # it — that would strand a deal with no route back.)
    DealStatus.disputed: {
        DealStatus.cancelled,
        DealStatus.payment_pending,
        DealStatus.paid_escrow,
        DealStatus.shipped,
        DealStatus.delivered,
    },
    DealStatus.completed: set(),
    DealStatus.cancelled: set(),
}

#: Who may drive a transition INTO a status (outside dispute resolution).
_ACTOR_RULES: dict[DealStatus, frozenset[DealActorKind]] = {
    DealStatus.negotiation: frozenset({DealActorKind.system}),
    DealStatus.contract_pending: frozenset({DealActorKind.system}),
    DealStatus.contract_signed: frozenset({DealActorKind.system}),
    # P3 replaces this with an automatic step; until then staff may move a signed
    # deal to payment_pending by hand.
    DealStatus.payment_pending: frozenset({DealActorKind.staff, DealActorKind.system}),
    DealStatus.paid_escrow: frozenset({DealActorKind.system}),
    DealStatus.shipped: frozenset({DealActorKind.seller}),
    DealStatus.delivered: frozenset({DealActorKind.buyer}),
    DealStatus.completed: frozenset({DealActorKind.system}),
    DealStatus.cancelled: frozenset(
        {DealActorKind.buyer, DealActorKind.seller, DealActorKind.staff}
    ),
    DealStatus.disputed: frozenset(
        {DealActorKind.buyer, DealActorKind.seller, DealActorKind.staff}
    ),
}

#: Statuses whose transitions must carry a reason (they end or freeze the deal).
_REASON_REQUIRED: frozenset[DealStatus] = frozenset(
    {DealStatus.cancelled, DealStatus.disputed}
)


def allowed_actors(frm: DealStatus, to: DealStatus) -> frozenset[DealActorKind]:
    """Actor kinds permitted to move a deal `frm` → `to`.

    Leaving a dispute is staff-only regardless of the destination: that is the
    whole point of the dispute state, and it is why staff appear in the rules
    for statuses the parties themselves drive.
    """
    if frm is DealStatus.disputed:
        return frozenset({DealActorKind.staff})
    return _ACTOR_RULES[to]


# ── Domain exceptions (no `Error` suffix — house style) ───────────────────────


class CompanyNotVerified(Exception):
    """A deal party is not a verified company."""


class InvalidDealTransition(Exception):
    """The requested deal status transition is not allowed."""


class ActorNotAllowed(Exception):
    """This actor kind may not drive this transition."""


class ReasonRequired(Exception):
    """Cancelling or disputing a deal requires a reason."""


class NotDealParticipant(Exception):
    """The account is not an acting member of either party company."""


class DealRequiresCompany(Exception):
    """Both sides of a deal must be portal companies (a TG-origin party has none)."""


class ResponseNotOpen(Exception):
    """The RFQ response is no longer in a state that can be accepted/withdrawn."""


class ResponseAlreadyAccepted(Exception):
    """Another response to this RFQ has already been accepted (one deal per RFQ)."""


class DealAlreadyOpen(Exception):
    """A live deal for this context already exists."""


class DocumentAlreadyRevoked(Exception):
    """The document is already revoked (revocation is not repeatable)."""


# ── Number generation ─────────────────────────────────────────────────────────


def generate_deal_number(db: Session) -> str:
    """Next DEAL-YYYY-NNNNNN for the current year in Asia/Tashkent.

    Per-year PostgreSQL sequence, same pattern (and same first-use race guard)
    as `request_service.generate_request_number`: the advisory lock serializes
    the first CREATE SEQUENCE of the year, which is otherwise not concurrency
    safe and 500s one of two simultaneous callers.

    The sequence name is built from a SERVER-derived year, validated digits-only
    before interpolation — no user input reaches this SQL.
    """
    year = to_display_tz(utcnow(), "Asia/Tashkent").strftime("%Y")
    if not year.isdigit():  # pragma: no cover — defensive
        raise RuntimeError(f"Unexpected non-digit year: {year!r}")

    seq_name = f"deal_seq_{year}"
    db.execute(sa.text("SELECT pg_advisory_xact_lock(:k)"), {"k": int(year)})
    db.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))  # noqa: S608
    nextval: int = db.execute(sa.text(f"SELECT nextval('{seq_name}')")).scalar()  # type: ignore[assignment]
    return f"DEAL-{year}-{nextval:06d}"


# ── Guards ────────────────────────────────────────────────────────────────────


def _assert_verified(company: Company) -> None:
    if company.status != CompanyStatus.verified:
        raise CompanyNotVerified(str(company.id))


def acting_company(
    db: Session, deal: Deal, account: UserAccount, company_id: int | None = None
) -> Company:
    """The party company `account` acts for in this deal, or NotDealParticipant.

    Requires an ACTIVE owner/manager membership: a plain member of a party
    company can read the deal but not speak or act inside it.

    `company_id` pins which side to act as. One person can belong to both
    companies in a deal (a broker running both ends, or test data), and then
    "whichever membership we found first" would silently pick a side. The API
    always passes it — the company in the URL is the hat the user is wearing.
    """
    sides = [deal.buyer_company_id, deal.seller_company_id]
    if company_id is not None:
        if company_id not in sides:
            raise NotDealParticipant(str(company_id))
        sides = [company_id]

    row = (
        db.query(CompanyMember)
        .filter(
            CompanyMember.user_account_id == account.id,
            CompanyMember.status == CompanyMemberStatus.active,
            CompanyMember.member_role.in_(list(DEAL_ACTOR_ROLES)),
            CompanyMember.company_id.in_(sides),
        )
        .first()
    )
    if row is None:
        raise NotDealParticipant(str(deal.id))
    company = db.get(Company, row.company_id)
    if company is None:  # pragma: no cover — FK guarantees it
        raise NotDealParticipant(str(deal.id))
    return company


def actor_kind_for(deal: Deal, company: Company) -> DealActorKind:
    """'buyer' / 'seller' for a party company."""
    role = deal.party_role(company.id)
    if role == "buyer":
        return DealActorKind.buyer
    if role == "seller":
        return DealActorKind.seller
    raise NotDealParticipant(str(company.id))


def is_participant_account(db: Session, deal: Deal, account: UserAccount) -> bool:
    """True when the account is any active member of either party (read access)."""
    return (
        db.query(CompanyMember.id)
        .filter(
            CompanyMember.user_account_id == account.id,
            CompanyMember.status == CompanyMemberStatus.active,
            CompanyMember.company_id.in_([deal.buyer_company_id, deal.seller_company_id]),
        )
        .first()
        is not None
    )


# ── Notifications (in-transaction; the bell shares the deal's fate) ───────────


def _notify(
    db: Session,
    company_id: int,
    kind: str,
    deal: Deal,
    *,
    extra: dict[str, object] | None = None,
    cooldown_seconds: int | None = None,
    exclude_account_id: int | None = None,
) -> None:
    """Ring a company's bell about a deal.

    Written inline rather than through the outbox: this is the deals context
    notifying its own participants, so it belongs in the same transaction — a
    rolled-back deal must not leave a notification about a deal that is not
    there. (The outbox is for genuinely cross-context effects; see
    `app/tasks/portal_notify.py`.)
    """
    title_key, body_key = notification_service.keys_for(kind)
    params: dict[str, object] = {"number": deal.number, "deal_id": deal.id}
    params.update(extra or {})
    notification_service.notify_company(
        db,
        company_id,
        kind=kind,
        title_key=title_key,
        body_key=body_key,
        params=params,
        entity="deal",
        entity_id=str(deal.id),
        cooldown_seconds=cooldown_seconds,
        exclude_account_id=exclude_account_id,
    )


# ── Opening a deal ────────────────────────────────────────────────────────────


def _total_amount(
    price: decimal.Decimal | None, qty: decimal.Decimal | None
) -> decimal.Decimal | None:
    """Deal value = unit price x quantity, to 2 dp. None when either is unknown."""
    if price is None or qty is None:
        return None
    return (price * qty).quantize(decimal.Decimal("0.01"))


def _open(
    db: Session,
    *,
    buyer: Company,
    seller: Company,
    account: UserAccount,
    request_id: int | None = None,
    offer_id: int | None = None,
    amount: decimal.Decimal | None = None,
    currency: str = "UZS",
) -> Deal:
    """Insert the Deal + its opening history row and emit DEAL_OPENED."""
    if buyer.id == seller.id:
        raise DealRequiresCompany("buyer == seller")
    _assert_verified(buyer)
    _assert_verified(seller)

    deal = Deal(
        number=generate_deal_number(db),
        buyer_company_id=buyer.id,
        seller_company_id=seller.id,
        request_id=request_id,
        offer_id=offer_id,
        status=DealStatus.negotiation,
        amount=amount,
        currency=(currency or "UZS").upper()[:3],
        created_by_user_account_id=account.id,
    )
    db.add(deal)
    db.flush()

    db.add(
        DealStatusHistory(
            deal_id=deal.id,
            from_status=None,                       # the opening row has nothing before it
            to_status=DealStatus.negotiation,
            actor_kind=DealActorKind.buyer
            if deal.party_role(buyer.id) == "buyer"
            else DealActorKind.system,
            actor_id=account.id,
        )
    )
    db.flush()

    event_service.emit(
        db,
        event_types.DEAL_OPENED,
        "deal",
        deal.id,
        {
            "buyer_company_id": buyer.id,
            "seller_company_id": seller.id,
            "request_id": request_id,
            "offer_id": offer_id,
        },
    )
    audit_service.write_audit(
        db, None, "deal.open", "deals", str(deal.id),
        {"account_id": account.id, "buyer": buyer.id, "seller": seller.id, "number": deal.number},
    )
    for company_id in (buyer.id, seller.id):
        _notify(db, company_id, notification_service.KIND_DEAL_OPENED, deal)
    logger.info(
        "deal_service.open", extra={"deal_id": deal.id, "number": deal.number}
    )
    return deal


def open_deal_from_response(
    db: Session, request: Request, response: RfqResponse, account: UserAccount
) -> Deal:
    """Accept an RFQ response: open the deal, retire the competing responses.

    Concurrency: the buyer's `requests` row is locked FOR UPDATE first, so two
    simultaneous accepts on the same RFQ serialize and the second sees the
    first's `accepted` response and is rejected. One RFQ yields one deal.
    """
    if request.company_id is None:
        raise DealRequiresCompany("rfq has no buyer company")
    if response.request_id != request.id:
        raise ResponseNotOpen("response belongs to another request")

    # Serialize accepts on the RFQ before reading the responses.
    db.execute(select(Request).where(Request.id == request.id).with_for_update()).scalar_one()

    if response.status != RfqResponseStatus.submitted:
        raise ResponseNotOpen(str(response.status))
    already = (
        db.query(RfqResponse.id)
        .filter(
            RfqResponse.request_id == request.id,
            RfqResponse.status == RfqResponseStatus.accepted,
        )
        .first()
    )
    if already is not None:
        raise ResponseAlreadyAccepted(str(request.id))

    buyer = db.get(Company, request.company_id)
    seller = db.get(Company, response.company_id)
    if buyer is None or seller is None:  # pragma: no cover — FK guarantees both
        raise DealRequiresCompany("missing party company")

    deal = _open(
        db,
        buyer=buyer,
        seller=seller,
        account=account,
        request_id=request.id,
        amount=_total_amount(response.price, response.qty),
        currency=response.currency,
    )

    response.status = RfqResponseStatus.accepted
    response.deal_id = deal.id
    db.flush()
    event_service.emit(
        db, event_types.RFQ_RESPONSE_ACCEPTED, "rfq_response", response.id,
        {"request_id": request.id, "company_id": response.company_id, "deal_id": deal.id},
    )
    _notify(db, response.company_id, notification_service.KIND_RFQ_RESPONSE_ACCEPTED, deal)

    losers = (
        db.query(RfqResponse)
        .filter(
            RfqResponse.request_id == request.id,
            RfqResponse.id != response.id,
            RfqResponse.status == RfqResponseStatus.submitted,
        )
        .all()
    )
    for loser in losers:
        loser.status = RfqResponseStatus.not_selected
        event_service.emit(
            db, event_types.RFQ_RESPONSE_NOT_SELECTED, "rfq_response", loser.id,
            {"request_id": request.id, "company_id": loser.company_id},
        )
        # Deliberately keyed to the RFQ, not the deal: a supplier who lost has no
        # business following a deal they are not part of.
        title_key, body_key = notification_service.keys_for(
            notification_service.KIND_RFQ_RESPONSE_NOT_SELECTED
        )
        notification_service.notify_company(
            db,
            loser.company_id,
            kind=notification_service.KIND_RFQ_RESPONSE_NOT_SELECTED,
            title_key=title_key,
            body_key=body_key,
            params={"request_id": request.id},
            entity="request",
            entity_id=str(request.id),
        )
    db.flush()

    audit_service.write_audit(
        db, None, "deal.accept_response", "rfq_responses", str(response.id),
        {"account_id": account.id, "deal_id": deal.id, "not_selected": [x.id for x in losers]},
    )
    return deal


def open_deal_from_inquiry(
    db: Session, inquiry: OfferRequest, account: UserAccount
) -> Deal:
    """Open a deal from an approved company-origin inquiry (seller-driven).

    Both sides must be portal companies: a Telegram-origin inquiry has no buyer
    company to make a party of, so it cannot become a deal (`DealRequiresCompany`).
    """
    if inquiry.company_id is None:
        raise DealRequiresCompany("inquiry has no buyer company")
    offer = db.get(SellerOffer, inquiry.offer_id)
    if offer is None or offer.company_id is None:
        raise DealRequiresCompany("offer has no seller company")

    live = (
        db.query(Deal.id)
        .filter(
            Deal.offer_id == offer.id,
            Deal.buyer_company_id == inquiry.company_id,
            Deal.status.notin_([DealStatus.cancelled, DealStatus.completed]),
        )
        .first()
    )
    if live is not None:
        raise DealAlreadyOpen(str(live[0]))

    buyer = db.get(Company, inquiry.company_id)
    seller = db.get(Company, offer.company_id)
    if buyer is None or seller is None:  # pragma: no cover — FK guarantees both
        raise DealRequiresCompany("missing party company")

    return _open(
        db,
        buyer=buyer,
        seller=seller,
        account=account,
        offer_id=offer.id,
        amount=_total_amount(inquiry.target_price, inquiry.quantity),
        currency=inquiry.currency or offer.currency or "UZS",
    )


# ── Contract seam (T1.4) ──────────────────────────────────────────────────────

#: RFQ/offer quantity units → the units contract templates speak.
_UNIT_MAP: dict[str, str] = {"MT": "t", "T": "t", "TON": "t", "KG": "kg", "PCS": "pcs"}


def attach_contract(
    db: Session, deal: Deal, contract: Contract, account: UserAccount
) -> Deal:
    """Point the deal at a contract drawn up for it.

    The link lives here and nowhere else: the contracts context never writes to
    a deals table, it just emits events. Idempotent for the same contract; a
    second, different contract is refused, because the partial unique index on
    `contract_id` is what lets the activation consumer look a deal up by
    contract and trust the answer.
    """
    if {contract.initiator_company_id, contract.counterparty_company_id} != {
        deal.buyer_company_id,
        deal.seller_company_id,
    }:
        raise NotDealParticipant(str(contract.id))
    if deal.contract_id == contract.id:
        return deal
    if deal.contract_id is not None:
        raise DealAlreadyOpen(f"deal {deal.id} already has contract {deal.contract_id}")

    existing = (
        db.query(Deal.id)
        .filter(Deal.contract_id == contract.id, Deal.id != deal.id)
        .first()
    )
    if existing is not None:
        raise DealAlreadyOpen(f"contract {contract.id} belongs to deal {existing[0]}")

    deal.contract_id = contract.id
    db.flush()
    audit_service.write_audit(
        db, None, "deal.attach_contract", "deals", str(deal.id),
        {"account_id": account.id, "contract_id": contract.id},
    )
    return deal


def contract_prefill(
    db: Session, deal: Deal, *, schema: dict[str, object] | None = None
) -> dict[str, str]:
    """Contract variables suggested by the deal's own agreed terms.

    Best-effort: whatever the deal cannot answer (payment terms, delivery
    window) is simply absent, for the user to fill in.

    Passing the target template's `schema` drops values that would violate one
    of its enums. FOB, for instance, is a real Incoterm and a real `PriceBasis`,
    but SUPPLY_V1 does not list it — prefilling it would fail validation and
    block the whole form rather than leaving one field blank.
    """
    values: dict[str, str] = {}

    response: RfqResponse | None = None
    if deal.request_id is not None:
        response = (
            db.query(RfqResponse)
            .filter(
                RfqResponse.request_id == deal.request_id,
                RfqResponse.status == RfqResponseStatus.accepted,
            )
            .first()
        )
        request = db.get(Request, deal.request_id)
        if request is not None:
            product = request.product_text or request.grade_text
            if product:
                values["product"] = product

    if response is not None:
        values["price"] = f"{response.price:.2f}"
        values["currency"] = response.currency
        values["qty"] = format(response.qty.normalize(), "f")
        values["unit"] = _UNIT_MAP.get(response.qty_unit.upper(), response.qty_unit)
        if response.incoterms is not None:
            values["incoterms"] = response.incoterms.value
    elif deal.offer_id is not None:
        offer = db.get(SellerOffer, deal.offer_id)
        if offer is not None:
            product = offer.product_text or offer.grade_text
            if product:
                values["product"] = product
            if offer.price is not None:
                values["price"] = f"{offer.price:.2f}"
            if offer.currency:
                values["currency"] = offer.currency

    if schema is not None:
        properties = schema.get("properties")
        props = properties if isinstance(properties, dict) else {}
        for key in list(values):
            spec = props.get(key)
            if isinstance(spec, dict) and "enum" in spec:
                allowed = spec["enum"]
                if isinstance(allowed, list) and values[key] not in allowed:
                    values.pop(key)
    return values


def deal_for_contract(db: Session, contract_id: int) -> Deal | None:
    """The deal a contract was drawn up for, if any (R3 contracts have none)."""
    return db.query(Deal).filter(Deal.contract_id == contract_id).first()


# ── Transitions ───────────────────────────────────────────────────────────────


def transition(
    db: Session,
    deal: Deal,
    to_status: DealStatus,
    *,
    actor_kind: DealActorKind,
    actor_id: int | None = None,
    reason: str | None = None,
) -> Deal:
    """Move a deal to `to_status`, recording who did it and why.

    Takes a row lock first so two concurrent transitions cannot both read the
    same source status and both succeed. History + audit + domain event land in
    the caller's transaction along with the status itself.
    """
    locked = db.execute(select(Deal).where(Deal.id == deal.id).with_for_update()).scalar_one()
    frm = locked.status

    if to_status not in VALID_TRANSITIONS[frm]:
        raise InvalidDealTransition(f"{frm} → {to_status}")
    if actor_kind not in allowed_actors(frm, to_status):
        raise ActorNotAllowed(f"{actor_kind} may not drive {frm} → {to_status}")
    clean_reason = (reason or "").strip() or None
    if to_status in _REASON_REQUIRED and clean_reason is None:
        raise ReasonRequired(str(to_status))

    locked.status = to_status
    if to_status == DealStatus.cancelled:
        locked.cancelled_reason = clean_reason
    db.flush()

    db.add(
        DealStatusHistory(
            deal_id=locked.id,
            from_status=frm,
            to_status=to_status,
            actor_kind=actor_kind,
            actor_id=actor_id,
            reason=clean_reason,
        )
    )
    db.flush()

    event_service.emit(
        db, event_types.DEAL_STATUS_CHANGED, "deal", locked.id,
        {
            "from": frm.value,
            "to": to_status.value,
            "actor_kind": actor_kind.value,
            "reason": clean_reason,
            "buyer_company_id": locked.buyer_company_id,
            "seller_company_id": locked.seller_company_id,
        },
    )
    audit_service.write_audit(
        db, None, "deal.transition", "deals", str(locked.id),
        {"from": frm.value, "to": to_status.value, "actor_kind": actor_kind.value,
         "actor_id": actor_id, "reason": clean_reason},
    )

    # Tell whoever does not already know. A party that clicked the button needs no
    # bell; a system or staff move surprises both sides.
    if actor_kind == DealActorKind.buyer:
        recipients = [locked.seller_company_id]
    elif actor_kind == DealActorKind.seller:
        recipients = [locked.buyer_company_id]
    else:
        recipients = [locked.buyer_company_id, locked.seller_company_id]
    for company_id in recipients:
        _notify(
            db,
            company_id,
            notification_service.KIND_DEAL_STATUS,
            locked,
            extra={"status": to_status.value},
        )

    if locked is not deal:
        db.refresh(deal)
    return deal


def transition_by_party(
    db: Session,
    deal: Deal,
    account: UserAccount,
    to_status: DealStatus,
    reason: str | None = None,
    company_id: int | None = None,
) -> Deal:
    """`transition` driven by a party account — resolves its side for you."""
    company = acting_company(db, deal, account, company_id)
    return transition(
        db,
        deal,
        to_status,
        actor_kind=actor_kind_for(deal, company),
        actor_id=account.id,
        reason=reason,
    )


def available_transitions(deal: Deal, actor_kind: DealActorKind) -> list[DealStatus]:
    """Statuses this actor may move the deal to right now.

    The action bar is built from this, so the UI never offers a button the API
    would refuse — and never re-implements the state machine in TypeScript.
    """
    return [
        to
        for to in DealStatus
        if to in VALID_TRANSITIONS[deal.status]
        and actor_kind in allowed_actors(deal.status, to)
    ]


def needs_action(deal: Deal, actor_kind: DealActorKind) -> bool:
    """Whether this side owes the deal a move.

    Cancelling and disputing are always available and are not "progress", so
    they do not count — otherwise every live deal would demand attention.
    """
    passive = {DealStatus.cancelled, DealStatus.disputed}
    return any(to not in passive for to in available_transitions(deal, actor_kind))


# ── Chat ──────────────────────────────────────────────────────────────────────


def post_message(
    db: Session,
    deal: Deal,
    account: UserAccount,
    body: str = "",
    *,
    file_content: bytes | None = None,
    file_name: str | None = None,
    company_id: int | None = None,
) -> DealMessage:
    """Append a Trade Room message (text, a file, or both).

    The author's company is stored, not derived: membership changes over time
    and a message must keep showing the side that actually wrote it.
    """
    company = acting_company(db, deal, account, company_id)
    text = (body or "").strip()

    storage_path: str | None = None
    stored_name: str | None = None
    if file_content is not None:
        if len(file_content) > MAX_DEAL_FILE_BYTES:
            raise ValueError("file_too_large")
        storage_path, _mime, _sha = storage_service.store_deal_file(
            deal.id, "chat", file_content, file_name or "upload"
        )
        stored_name = (file_name or "upload").rsplit("/", 1)[-1]

    if not text and storage_path is None:
        raise ValueError("empty_message")

    message = DealMessage(
        deal_id=deal.id,
        author_account_id=account.id,
        author_company_id=company.id,
        body=text,
        file_storage_path=storage_path,
        file_name=stored_name,
    )
    db.add(message)
    db.flush()

    event_service.emit(
        db, event_types.DEAL_MESSAGE_POSTED, "deal", deal.id,
        {
            "message_id": message.id,
            "author_company_id": company.id,
            "buyer_company_id": deal.buyer_company_id,
            "seller_company_id": deal.seller_company_id,
        },
    )
    other = (
        deal.seller_company_id
        if company.id == deal.buyer_company_id
        else deal.buyer_company_id
    )
    _notify(
        db,
        other,
        notification_service.KIND_DEAL_MESSAGE,
        deal,
        cooldown_seconds=CHAT_NOTIFY_COOLDOWN_SECONDS,
    )
    return message


def list_messages(
    db: Session, deal: Deal, *, after_id: int | None = None, limit: int = 100
) -> list[DealMessage]:
    """Chat page in id order; `after_id` makes the client's poll incremental."""
    query = db.query(DealMessage).filter(DealMessage.deal_id == deal.id)
    if after_id is not None:
        query = query.filter(DealMessage.id > after_id)
    return query.order_by(DealMessage.id).limit(max(1, min(limit, 200))).all()


# ── Documents ─────────────────────────────────────────────────────────────────


def add_document(
    db: Session,
    deal: Deal,
    account: UserAccount,
    kind: DealDocumentKind,
    content: bytes,
    file_name: str,
    company_id: int | None = None,
) -> DealDocument:
    """Attach a document to the deal (append-only; sha256 recorded as evidence)."""
    company = acting_company(db, deal, account, company_id)
    if len(content) > MAX_DEAL_FILE_BYTES:
        raise ValueError("file_too_large")

    key, mime, sha = storage_service.store_deal_file(deal.id, "documents", content, file_name)
    document = DealDocument(
        deal_id=deal.id,
        kind=kind,
        file_name=(file_name or "upload").rsplit("/", 1)[-1],
        mime_type=mime,
        size_bytes=len(content),
        storage_path=key,
        sha256=sha,
        uploaded_by_user_account_id=account.id,
        uploaded_by_company_id=company.id,
    )
    db.add(document)
    db.flush()

    event_service.emit(
        db, event_types.DEAL_DOCUMENT_ADDED, "deal", deal.id,
        {
            "document_id": document.id,
            "kind": kind.value,
            "uploaded_by_company_id": company.id,
            "buyer_company_id": deal.buyer_company_id,
            "seller_company_id": deal.seller_company_id,
        },
    )
    audit_service.write_audit(
        db, None, "deal.add_document", "deal_documents", str(document.id),
        {"account_id": account.id, "deal_id": deal.id, "kind": kind.value, "sha256": sha},
    )
    other = (
        deal.seller_company_id
        if company.id == deal.buyer_company_id
        else deal.buyer_company_id
    )
    _notify(
        db,
        other,
        notification_service.KIND_DEAL_DOCUMENT,
        deal,
        extra={"kind": kind.value, "file_name": document.file_name},
    )
    return document


def revoke_document(
    db: Session,
    document: DealDocument,
    account: UserAccount,
    reason: str,
    company_id: int | None = None,
) -> DealDocument:
    """Mark a document withdrawn. The S3 object stays — this is an evidence trail.

    Only the company that uploaded it may withdraw it.
    """
    deal = db.get(Deal, document.deal_id)
    if deal is None:  # pragma: no cover — FK guarantees it
        raise NotDealParticipant(str(document.deal_id))
    company = acting_company(db, deal, account, company_id)
    if company.id != document.uploaded_by_company_id:
        raise NotDealParticipant(str(company.id))
    if document.revoked:
        raise DocumentAlreadyRevoked(str(document.id))

    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ReasonRequired("revoke")

    document.revoked = True
    document.revoked_reason = clean_reason
    db.flush()
    audit_service.write_audit(
        db, None, "deal.revoke_document", "deal_documents", str(document.id),
        {"account_id": account.id, "deal_id": deal.id, "reason": clean_reason},
    )
    return document


def now_utc() -> datetime.datetime:
    return utcnow()
