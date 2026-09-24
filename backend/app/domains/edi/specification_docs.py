"""Send a framework contract's specification to Didox (stage 2).

A specification is a «Произвольный документ» (000) with subtype 8
«Спецификация»: it carries our PDF — the real «Спецификация № 01» form — and a
`ContractDoc` naming the договор exactly as its ЭСФ will. It does not go to the
roaming centre, and does not need to: the goods reach the tax authority through
the ЭСФ issued against it.

Only the SELLER sends it, as with the договор and the ЭСФ; both parties sign it
at Didox, and `edi_service.apply_status` settles it (3 → active, 4 → declined).
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from app.domains.edi.contract_docs import (
    ContractGateway,
    PartyMismatch,
    _linked_deal,
    _linked_offer,
    resolve_parties,
)
from app.domains.edi.models import DOC_TYPE_ARBITRARY
from app.domains.edi.payloads import PartyRequisites, build_specification_000

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

    from app.domains.companies.models import Company
    from app.domains.contracts.models import ContractSpecification
    from app.domains.edi.models import DidoxDocument


class SpecificationNotReady(Exception):
    """Only a draft specification with a rendered PDF is sent."""


def _party(db: Session, company: Company) -> PartyRequisites:
    """Name and address — all a «Произвольный документ» asks of a party."""
    from app.domains.contracts.service import _requisites  # noqa: PLC0415

    requisites = _requisites(db, company)
    return PartyRequisites(
        tin=str(requisites["inn"]),
        name=str(requisites["legal_name"]),
        address=str(requisites["address"]) or None,
    )


def existing_document(db: Session, spec: ContractSpecification) -> DidoxDocument | None:
    from app.domains.edi.models import DidoxDocument  # noqa: PLC0415

    return (
        db.query(DidoxDocument)
        .filter(
            DidoxDocument.subject_kind == "specification",
            DidoxDocument.subject_id == spec.id,
            DidoxDocument.status.notin_([5, 55]),
        )
        .order_by(DidoxDocument.id.desc())
        .first()
    )


def create_for_specification(
    db: Session,
    spec: ContractSpecification,
    *,
    acting_company_id: int,
    account_id: int,
    user_key: str,
    client: ContractGateway,
) -> DidoxDocument:
    """Create the specification at Didox; idempotent while its document lives."""
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.contracts.models import Contract  # noqa: PLC0415
    from app.domains.edi import facture_docs  # noqa: PLC0415
    from app.domains.edi import service as edi_service  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    existing = existing_document(db, spec)
    if existing is not None:
        return existing
    if spec.status != "draft" or not spec.generated_document_path:
        raise SpecificationNotReady(spec.status)

    contract = db.get(Contract, spec.contract_id)
    if contract is None:  # pragma: no cover — FK-guaranteed
        raise SpecificationNotReady("no contract")
    deal = _linked_deal(db, contract)
    seller_id, buyer_id = resolve_parties(
        contract, deal=deal, offer=_linked_offer(db, contract, deal)
    )
    if acting_company_id != seller_id:
        raise PartyMismatch(f"company {acting_company_id} is not the seller of contract {contract.id}")
    seller = db.get(Company, seller_id)
    buyer = db.get(Company, buyer_id)
    if seller is None or buyer is None:  # pragma: no cover — FK-guaranteed
        raise PartyMismatch(f"contract {contract.id} references a missing company")

    contract_no, contract_date, _didox_contract_id = facture_docs.contract_reference(db, contract)
    body = build_specification_000(
        number=str(spec.number),
        date=spec.spec_date,
        name=f"Спецификация № {spec.number} к договору № {contract_no}",
        contract_number=contract_no,
        contract_date=contract_date,
        seller=_party(db, seller),
        buyer=_party(db, buyer),
    )
    pdf = storage_service.get_object_bytes(spec.generated_document_path)
    row = edi_service.create_document(
        db,
        doc_type=DOC_TYPE_ARBITRARY,
        subject_kind="specification",
        subject_id=int(spec.id),
        owner_company_id=seller_id,
        partner_company_id=buyer_id,
        deal_id=int(deal.id) if deal is not None else None,
        number=str(spec.number),
        doc_date=spec.spec_date,
        payload=body,
        created_by_user_account_id=account_id,
        user_key=user_key,
        tax_id=seller.tax_id,
        client=client,
        attachment_b64=base64.b64encode(pdf).decode("ascii"),
    )
    row.specification_id = int(spec.id)
    spec.status = "pending_signatures"
    db.flush()
    return row
