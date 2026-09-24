"""Turn a signed contract into an ЭСФ — Didox «счёт-фактура» 002.

`payloads.build_facture_002` existed since P7.a with nothing calling it. This is the
door, modelled on `contract_docs.create_for_contract`, and the same decisions hold:
the owner is the SELLER, the buyer's block comes from the tax registry, and nothing
is invented.

Three rules are specific to the invoice:

**The contract reference is quoted, never recomputed.** The roaming centre refuses
an ЭСФ whose `ContractNo`/`ContractDate` disagree with the договор. On the Didox rail
they are read off the stored 007; on E-IMZO they are the number our own documents
use (`numbering.contract_number`) and the day the contract became active, in
Tashkent.

**A contract may carry several invoices.** Goods ship in parts, so the unique slot
binds the 007 only (0053). What is left to invoice is the contract's quantity less
every invoice still standing — a rejected or deleted one gives its quantity back.
Over-invoicing is NOT refused: the parties may have agreed to ship more, and the
screen shows what is left rather than forbidding it.

**One unsigned draft at a time.** A second press while the first invoice is still
unsigned would mint a second number from the seller's book for the same shipment;
it is refused with the draft's id, so the screen offers to sign that one instead.

**An ЭСФ is in soum.** A contract priced in another currency gets no price prefill:
copying «1150» from a USD contract would invoice 1150 сум.
"""

from __future__ import annotations

import datetime
import decimal
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.domains.edi.contract_docs import (
    ContractGateway,
    IkpuChoice,
    PartyMismatch,
    _existing_document,
    _linked_deal,
    _linked_offer,
    party_from_company,
    party_from_registry,
    resolve_parties,
)
from app.domains.edi.models import (
    DOC_TYPE_FACTURE,
    STATUS_ANNULLED_BY_TAX,
    STATUS_DELETED,
    STATUS_DRAFT,
    STATUS_DRAFT_DELETED,
    STATUS_REJECTED,
)
from app.domains.edi.payloads import DocumentLine, build_facture_002

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

    from app.domains.contracts.models import Contract, ContractSpecification
    from app.domains.edi.models import DidoxDocument

#: Invoices that no longer stand — their quantity is free to invoice again.
_NOT_STANDING = (STATUS_REJECTED, STATUS_DELETED, STATUS_ANNULLED_BY_TAX, STATUS_DRAFT_DELETED)
_DEFAULT_VAT = 12


class ContractNotActive(Exception):
    """Only a contract both parties signed is invoiced."""


class FacturePending(Exception):
    """An earlier invoice of this contract is still an unsigned draft."""

    def __init__(self, document_id: int) -> None:
        super().__init__(f"ЭСФ {document_id} is still an unsigned draft")
        self.document_id = document_id


class SpecificationRequired(Exception):
    """A framework contract is invoiced against one of its SIGNED specifications."""


class ContractReferenceMissing(Exception):
    """A Didox contract without its 007 — nothing to quote."""


@dataclass(frozen=True)
class SuggestedLine:
    """What the form starts from. `price` is None when the contract is not in soum."""

    ord_no: int
    name: str
    count: decimal.Decimal | None
    price: decimal.Decimal | None
    vat_rate: int | None
    unit: str | None


def list_for_contract(db: Session, contract: Contract) -> list[DidoxDocument]:
    """Every invoice of this contract, newest first, deleted drafts excluded."""
    from app.domains.edi.models import DidoxDocument  # noqa: PLC0415

    return (
        db.query(DidoxDocument)
        .filter(
            DidoxDocument.subject_kind == "contract",
            DidoxDocument.subject_id == contract.id,
            DidoxDocument.doc_type == DOC_TYPE_FACTURE,
            DidoxDocument.status.notin_([STATUS_DELETED, STATUS_DRAFT_DELETED]),
        )
        .order_by(DidoxDocument.id.desc())
        .all()
    )


def pending_draft(db: Session, contract: Contract) -> DidoxDocument | None:
    return next((row for row in list_for_contract(db, contract) if row.status == STATUS_DRAFT), None)


def invoiced(
    db: Session, contract: Contract, spec: ContractSpecification | None = None
) -> dict[int, decimal.Decimal]:
    """`ord_no → quantity` across the invoices still standing — of this specification,
    if one is named, else of the contract's own goods."""
    from sqlalchemy import func  # noqa: PLC0415

    from app.domains.edi.models import DidoxDocument, DidoxDocumentLine  # noqa: PLC0415

    rows = (
        db.query(DidoxDocumentLine.ord_no, func.sum(DidoxDocumentLine.qty))
        .join(DidoxDocument, DidoxDocument.id == DidoxDocumentLine.didox_document_id)
        .filter(
            DidoxDocument.subject_kind == "contract",
            DidoxDocument.subject_id == contract.id,
            DidoxDocument.doc_type == DOC_TYPE_FACTURE,
            DidoxDocument.status.notin_(_NOT_STANDING),
            DidoxDocument.specification_id == spec.id
            if spec is not None
            else DidoxDocument.specification_id.is_(None),
        )
        .group_by(DidoxDocumentLine.ord_no)
        .all()
    )
    return {int(ord_no): decimal.Decimal(total) for ord_no, total in rows}


def suggested_lines(
    db: Session, contract: Contract, spec: ContractSpecification | None = None
) -> list[SuggestedLine]:
    """The lines to invoice — the specification's, or the contract's own — with what
    is left to invoice as the quantity."""
    from app.domains.contracts.models import ContractLine  # noqa: PLC0415

    done = invoiced(db, contract, spec)
    in_soum = spec is not None or (contract.currency or "UZS").upper() == "UZS"
    lines = (
        db.query(ContractLine)
        .filter(
            ContractLine.contract_id == contract.id,
            ContractLine.specification_id == spec.id
            if spec is not None
            else ContractLine.specification_id.is_(None),
        )
        .order_by(ContractLine.ord_no)
        .all()
    )
    out: list[SuggestedLine] = []
    for line in lines:
        left = None
        if line.qty is not None:
            left = max(line.qty - done.get(line.ord_no, decimal.Decimal(0)), decimal.Decimal(0))
        out.append(
            SuggestedLine(
                ord_no=line.ord_no,
                name=line.product_name,
                count=left,
                price=line.price if in_soum else None,
                # Stamped by the 007 when there was one; otherwise the common rate.
                vat_rate=line.vat_rate if line.ikpu_code else _DEFAULT_VAT,
                unit=line.unit,
            )
        )
    return out


def classification(
    db: Session, contract: Contract, choice: IkpuChoice | None = None
) -> object | None:
    """Where this contract's ИКПУ comes from, in order of authority — or None.

    The seller's explicit pick wins; then the offer the contract was drawn from;
    then the line of the signed 007, which already carried a code the roaming
    centre accepted. None means the screen must ask.
    """
    from app.domains.edi.models import DidoxDocumentLine  # noqa: PLC0415

    if choice is not None:
        return choice
    offer = _linked_offer(db, contract, _linked_deal(db, contract))
    if offer is not None and offer.ikpu_code:
        return offer
    document = _existing_document(db, contract)
    if document is None:
        return None
    line = (
        db.query(DidoxDocumentLine)
        .filter(DidoxDocumentLine.didox_document_id == document.id, DidoxDocumentLine.ord_no == 1)
        .one_or_none()
    )
    if line is None or line.origin is None:
        return None
    return IkpuChoice(
        ikpu_code=line.ikpu_code,
        ikpu_name=line.ikpu_name,
        ikpu_package_code=line.package_code,
        ikpu_package_name=line.package_name,
        ikpu_origin=int(line.origin),
    )


def contract_reference(db: Session, contract: Contract) -> tuple[str, datetime.date, str | None]:
    """`(ContractNo, ContractDate, didox_contract_id)` exactly as the договор states them."""
    from app.core.time import to_display_tz  # noqa: PLC0415
    from app.domains.contracts.terms import typed_date  # noqa: PLC0415
    from app.domains.edi import numbering  # noqa: PLC0415

    variables = contract.variables if isinstance(contract.variables, dict) else {}
    if contract.signing_provider == "didox":
        document = _existing_document(db, contract)
        # The stored 007 is the authority: it is what the roaming centre holds.
        if document is not None and document.number and document.doc_date is not None:
            return document.number, document.doc_date, document.didox_contract_id
        # No 007 yet — the number and date the parties typed on the contract.
        typed_no = str(variables.get("contract_number") or "").strip()
        typed_day = typed_date(variables.get("contract_date"))
        if typed_no and typed_day is not None:
            return typed_no, typed_day, None
        raise ContractReferenceMissing(str(contract.id))

    deal = _linked_deal(db, contract)
    number = numbering.contract_number(
        deal_number=deal.number if deal is not None else None,
        contract_public_id=str(contract.public_id),
        custom=str(variables.get("contract_number") or ""),
    )
    typed_day = typed_date(variables.get("contract_date"))
    if typed_day is not None:
        return number, typed_day, None
    activated = contract.activated_at or contract.created_at
    return number, to_display_tz(activated).date(), None


def create_for_contract(
    db: Session,
    contract: Contract,
    *,
    acting_company_id: int,
    account_id: int,
    lines: list[DocumentLine],
    user_key: str,
    client: ContractGateway,
    today: datetime.date,
    specification: ContractSpecification | None = None,
) -> DidoxDocument:
    """Create an ЭСФ for this contract at Didox. `lines` arrive classified.

    A framework contract is invoiced against one of its SIGNED specifications;
    the ЭСФ remembers which, so what is left to invoice is counted per
    specification.
    """
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.contracts.specifications import is_framework  # noqa: PLC0415
    from app.domains.edi import numbering  # noqa: PLC0415
    from app.domains.edi import service as edi_service  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415

    if contract.status != ContractStatus.active:
        raise ContractNotActive(str(contract.status))
    if is_framework(contract):
        if (
            specification is None
            or specification.contract_id != contract.id
            or specification.status != "active"
        ):
            raise SpecificationRequired(str(contract.id))
    elif specification is not None:
        raise SpecificationRequired(str(contract.id))
    deal = _linked_deal(db, contract)
    offer = _linked_offer(db, contract, deal)
    seller_id, buyer_id = resolve_parties(contract, deal=deal, offer=offer)
    if acting_company_id != seller_id:
        raise PartyMismatch(f"company {acting_company_id} is not the seller of contract {contract.id}")
    draft = pending_draft(db, contract)
    if draft is not None:
        raise FacturePending(int(draft.id))

    seller = db.get(Company, seller_id)
    buyer = db.get(Company, buyer_id)
    if seller is None or buyer is None:  # pragma: no cover — FK-guaranteed
        raise PartyMismatch(f"contract {contract.id} references a missing company")

    try:
        vat = client.vat_reg_status(
            seller.tax_id, document_date=today.isoformat(), is_seller=True, user_key=user_key
        )
    except Exception:  # noqa: BLE001 — their soliq gateway is routinely down
        vat = None

    contract_no, contract_date, didox_contract_id = contract_reference(db, contract)
    number = numbering.next_facture_number(db, seller_id, today)
    body = build_facture_002(
        number=number,
        date=today,
        contract_number=contract_no,
        contract_date=contract_date,
        seller=party_from_company(
            db,
            seller,
            vat_reg_code=vat.code if vat is not None else None,
            vat_reg_status=vat.status if vat is not None else None,
        ),
        buyer=party_from_registry(client, buyer.tax_id),
        lines=lines,
        didox_contract_id=didox_contract_id,
    )
    row = edi_service.create_document(
        db,
        doc_type=DOC_TYPE_FACTURE,
        subject_kind="contract",
        subject_id=int(contract.id),
        owner_company_id=seller_id,
        partner_company_id=buyer_id,
        deal_id=int(deal.id) if deal is not None else None,
        number=number,
        doc_date=today,
        payload=body,
        created_by_user_account_id=account_id,
        user_key=user_key,
        tax_id=seller.tax_id,
        client=client,
        lines=lines,
    )
    if specification is not None:
        row.specification_id = int(specification.id)
        db.flush()
    return row
